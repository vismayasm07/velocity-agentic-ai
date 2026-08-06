import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.actions import (
    ActionExecutionError,
    CRMActionResult,
    CRMReassignmentRequest,
    review_deal_reassignment,
)
from app.database import async_session_factory, engine
from app.detection import run_stalled_deal_scan
from app.main import app
from app.models import (
    AgentAnalysis,
    AgentAuditEvent,
    ApprovalRequest,
    BottleneckIncident,
    Deal,
    SalesOwnerCapacity,
    User,
)
from app.security import hash_password


created_deal_ids: list[UUID] = []
created_owner_names: list[str] = []
regular_email = "reviewer-test@velocitycrm.com"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        async def setup() -> None:
            async with async_session_factory() as session:
                session.add(
                    User(
                        email=regular_email,
                        password_hash=hash_password("RegularUser@2026"),
                        is_admin=False,
                        is_active=True,
                    )
                )
                await session.commit()

        assert test_client.portal is not None
        test_client.portal.call(setup)
        yield test_client

        async def cleanup() -> None:
            async with async_session_factory() as session:
                await session.execute(delete(Deal).where(Deal.id.in_(created_deal_ids)))
                await session.execute(
                    delete(SalesOwnerCapacity).where(
                        SalesOwnerCapacity.owner_name.in_(created_owner_names)
                    )
                )
                await session.execute(delete(User).where(User.email == regular_email))
                await session.commit()

        test_client.portal.call(cleanup)
    asyncio.run(engine.dispose())


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers(client: TestClient) -> dict[str, str]:
    return login(client, "admin@velocitycrm.com", "VelocityAdmin@2026")


@pytest.fixture(scope="module")
def regular_headers(client: TestClient) -> dict[str, str]:
    return login(client, regular_email, "RegularUser@2026")


def create_context(
    client: TestClient,
    *,
    current_owner: str | None = None,
    target_active: bool = True,
    active_deals: int = 3,
    max_active_deals: int = 10,
    deal_status: str = "ACTIVE",
    incident_status: str = "open",
) -> tuple[UUID, UUID, str]:
    target_name = f"Target {uuid4()}"
    owner_name = current_owner or f"Current {uuid4()}"

    async def create() -> tuple[UUID, UUID, str]:
        async with async_session_factory() as session:
            now = datetime.now(UTC)
            deal = Deal(
                name=f"Reassignment test {uuid4()}",
                value=Decimal("75000.00"),
                stage="Proposal",
                owner_name=owner_name,
                stage_entered_at=now - timedelta(days=14),
                last_activity_at=now - timedelta(days=10),
                next_follow_up_at=None,
                status=deal_status,
            )
            session.add(deal)
            await session.flush()
            incident = BottleneckIncident(
                deal_id=deal.id,
                incident_type="stalled_deal",
                title="Owner intervention required",
                severity="high",
                risk_score=88,
                evidence={"owner_capacity": {"triggered": True}},
                status=incident_status,
            )
            session.add(incident)
            await session.flush()
            session.add_all(
                [
                    AgentAnalysis(
                        incident_id=incident.id,
                        model_name="gemini-test",
                        trigger="MANUAL",
                        input_fingerprint=str(uuid4()),
                        summary="The deal needs a new owner.",
                        root_cause="Current ownership is blocking progress.",
                        supporting_evidence=["The deal exceeded its SLA."],
                        risk_explanation="The deal is at risk.",
                        recommended_action="Reassign to an owner with capacity.",
                        action_type="REQUEST_REASSIGNMENT",
                        confidence=0.92,
                        approval_required=True,
                        policy_references=["Stalled-Deal Handling"],
                        expected_outcome="Restore deal progression.",
                        status="COMPLETED",
                    ),
                    SalesOwnerCapacity(
                        owner_name=target_name,
                        active_deals=active_deals,
                        max_active_deals=max_active_deals,
                        is_active=target_active,
                    ),
                ]
            )
            await session.commit()
            created_deal_ids.append(deal.id)
            created_owner_names.append(target_name)
            return incident.id, deal.id, target_name

    assert client.portal is not None
    return client.portal.call(create)


def request_approval(
    client: TestClient, headers: dict[str, str], incident_id: UUID, owner: str
):
    return client.post(
        f"/api/incidents/{incident_id}/actions/request-reassignment",
        headers=headers,
        json={"proposed_owner": owner},
    )


def test_request_is_unique_and_does_not_change_deal(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id, deal_id, owner = create_context(client)
    first = request_approval(client, admin_headers, incident_id, owner)
    second = request_approval(client, admin_headers, incident_id, owner)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "PENDING"

    async def state() -> tuple[str, int]:
        async with async_session_factory() as session:
            deal = await session.get(Deal, deal_id)
            approvals = list(
                await session.scalars(
                    select(ApprovalRequest).where(ApprovalRequest.incident_id == incident_id)
                )
            )
            assert deal is not None
            return deal.owner_name, len(approvals)

    assert client.portal is not None
    original_owner, count = client.portal.call(state)
    assert original_owner != owner
    assert count == 1


def test_non_admin_cannot_review(
    client: TestClient,
    admin_headers: dict[str, str],
    regular_headers: dict[str, str],
) -> None:
    incident_id, _, owner = create_context(client)
    approval = request_approval(client, admin_headers, incident_id, owner).json()
    for action in ("approve", "reject"):
        response = client.post(
            f"/api/approvals/{approval['id']}/{action}",
            headers=regular_headers,
            json={"comment": "Not authorized"},
        )
        assert response.status_code == 403


def test_approval_executes_once_and_audits_snapshot(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id, deal_id, owner = create_context(client, incident_status="escalated")
    approval = request_approval(client, admin_headers, incident_id, owner).json()
    first = client.post(
        f"/api/approvals/{approval['id']}/approve",
        headers=admin_headers,
        json={"comment": "Capacity verified"},
    )
    second = client.post(
        f"/api/approvals/{approval['id']}/approve",
        headers=admin_headers,
        json={"comment": "Repeated request"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "EXECUTED"

    async def state() -> tuple[str, str, AgentAuditEvent, int]:
        async with async_session_factory() as session:
            await run_stalled_deal_scan(session)
            deal = await session.get(Deal, deal_id)
            incident = await session.get(BottleneckIncident, incident_id)
            event = await session.scalar(
                select(AgentAuditEvent).where(
                    AgentAuditEvent.incident_id == incident_id,
                    AgentAuditEvent.event_type == "DEAL_OWNER_REASSIGNED",
                )
            )
            assert deal is not None and incident is not None and event is not None
            incident_count = len(
                list(
                    await session.scalars(
                        select(BottleneckIncident).where(BottleneckIncident.deal_id == deal_id)
                    )
                )
            )
            return deal.owner_name, incident.status, event, incident_count

    assert client.portal is not None
    deal_owner, incident_status, event, incident_count = client.portal.call(state)
    assert deal_owner == owner
    assert incident_status == "observing"
    assert incident_count == 1
    assert event.details["before"]["deal_owner"] != owner
    assert event.details["before"]["incident_status"] == "escalated"
    assert event.details["after"]["deal_owner"] == owner
    assert "verification_due_at" in event.details


def test_rejection_keeps_owner(client: TestClient, admin_headers: dict[str, str]) -> None:
    incident_id, deal_id, owner = create_context(client)
    approval = request_approval(client, admin_headers, incident_id, owner).json()
    response = client.post(
        f"/api/approvals/{approval['id']}/reject",
        headers=admin_headers,
        json={"comment": "Keep current ownership"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"

    async def owner_name() -> str:
        async with async_session_factory() as session:
            deal = await session.get(Deal, deal_id)
            assert deal is not None
            return deal.owner_name

    assert client.portal is not None
    assert client.portal.call(owner_name) != owner


@pytest.mark.parametrize(
    ("case", "active", "active_deals", "maximum", "message"),
    [
        ("inactive", False, 1, 10, "not active"),
        ("overloaded", True, 10, 10, "at capacity"),
    ],
)
def test_invalid_target_rejected(
    client: TestClient,
    admin_headers: dict[str, str],
    case: str,
    active: bool,
    active_deals: int,
    maximum: int,
    message: str,
) -> None:
    incident_id, _, owner = create_context(
        client, target_active=active, active_deals=active_deals, max_active_deals=maximum
    )
    response = request_approval(client, admin_headers, incident_id, owner)
    assert response.status_code == 409, case
    assert message in response.json()["detail"]


def test_current_owner_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    incident_id, deal_id, target = create_context(client)

    async def make_current() -> None:
        async with async_session_factory() as session:
            deal = await session.get(Deal, deal_id)
            assert deal is not None
            deal.owner_name = target
            await session.commit()

    assert client.portal is not None
    client.portal.call(make_current)
    response = request_approval(client, admin_headers, incident_id, target)
    assert response.status_code == 409
    assert "already owns" in response.json()["detail"]


def test_expired_approval_cannot_execute(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id, _, owner = create_context(client)
    approval = request_approval(client, admin_headers, incident_id, owner).json()

    async def expire() -> None:
        async with async_session_factory() as session:
            item = await session.get(ApprovalRequest, UUID(approval["id"]))
            assert item is not None
            item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    assert client.portal is not None
    client.portal.call(expire)
    response = client.post(
        f"/api/approvals/{approval['id']}/approve",
        headers=admin_headers,
        json={"comment": "Too late"},
    )
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]


def test_expired_approval_is_replaced_and_audited(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id, _, owner = create_context(client)
    first = request_approval(client, admin_headers, incident_id, owner).json()

    async def expire() -> None:
        async with async_session_factory() as session:
            item = await session.get(ApprovalRequest, UUID(first["id"]))
            assert item is not None
            item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    assert client.portal is not None
    client.portal.call(expire)
    second = request_approval(client, admin_headers, incident_id, owner)
    assert second.status_code == 200
    assert second.json()["id"] != first["id"]

    async def state() -> tuple[str, int]:
        async with async_session_factory() as session:
            expired = await session.get(ApprovalRequest, UUID(first["id"]))
            events = list(
                await session.scalars(
                    select(AgentAuditEvent).where(
                        AgentAuditEvent.incident_id == incident_id,
                        AgentAuditEvent.event_type == "REASSIGNMENT_EXPIRED",
                    )
                )
            )
            assert expired is not None
            return expired.status, len(events)

    status, event_count = client.portal.call(state)
    assert status == "EXPIRED"
    assert event_count == 1


def test_adapter_failure_is_persisted(client: TestClient, admin_headers: dict[str, str]) -> None:
    incident_id, deal_id, owner = create_context(client)
    approval = request_approval(client, admin_headers, incident_id, owner).json()

    class FailingAdapter:
        async def create_follow_up(self, request):
            raise AssertionError("not used")

        async def reassign_deal(self, request: CRMReassignmentRequest):
            raise RuntimeError("CRM unavailable")

    async def execute() -> tuple[str, str]:
        async with async_session_factory() as session:
            admin = await session.scalar(select(User).where(User.is_admin.is_(True)))
            assert admin is not None
            with pytest.raises(ActionExecutionError) as error:
                await review_deal_reassignment(
                    session,
                    UUID(approval["id"]),
                    admin.id,
                    decision="APPROVE",
                    crm_adapter=FailingAdapter(),
                )
            assert error.value.status_code == 502
        async with async_session_factory() as session:
            item = await session.get(ApprovalRequest, UUID(approval["id"]))
            deal = await session.get(Deal, deal_id)
            assert item is not None and deal is not None
            return item.status, deal.owner_name

    assert client.portal is not None
    status, unchanged_owner = client.portal.call(execute)
    assert status == "EXECUTION_FAILED"
    assert unchanged_owner != owner


def test_adapter_failure_status_is_not_executed(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id, deal_id, owner = create_context(client)
    approval = request_approval(client, admin_headers, incident_id, owner).json()

    class FailureResultAdapter:
        async def create_follow_up(self, request):
            raise AssertionError("not used")

        async def reassign_deal(self, request: CRMReassignmentRequest):
            return CRMActionResult(status="FAILED")

    async def execute() -> tuple[str, str]:
        async with async_session_factory() as session:
            admin = await session.scalar(select(User).where(User.is_admin.is_(True)))
            assert admin is not None
            with pytest.raises(ActionExecutionError) as error:
                await review_deal_reassignment(
                    session,
                    UUID(approval["id"]),
                    admin.id,
                    decision="APPROVE",
                    crm_adapter=FailureResultAdapter(),
                )
            assert error.value.status_code == 502
        async with async_session_factory() as session:
            item = await session.get(ApprovalRequest, UUID(approval["id"]))
            deal = await session.get(Deal, deal_id)
            assert item is not None and deal is not None
            return item.status, deal.owner_name

    assert client.portal is not None
    status, unchanged_owner = client.portal.call(execute)
    assert status == "EXECUTION_FAILED"
    assert unchanged_owner != owner