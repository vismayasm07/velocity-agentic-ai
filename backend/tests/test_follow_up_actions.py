import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.actions import ActionExecutionError, CRMFollowUpRequest, create_follow_up_task
from app.database import async_session_factory, engine
from app.main import app
from app.models import AgentAnalysis, AgentAuditEvent, BottleneckIncident, Deal, FollowUpTask, MonitoringSettings, User


created_deal_ids: list[UUID] = []


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
        async def cleanup() -> None:
            async with async_session_factory() as session:
                await session.execute(delete(Deal).where(Deal.id.in_(created_deal_ids)))
                await session.commit()

        assert test_client.portal is not None
        test_client.portal.call(cleanup)
    asyncio.run(engine.dispose())


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_action_context(
    client: TestClient,
    *,
    action_type: str = "CREATE_FOLLOW_UP",
    approval_required: bool = False,
) -> tuple[UUID, UUID]:
    async def create() -> tuple[UUID, UUID]:
        async with async_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == "admin@velocitycrm.com"))
            assert user is not None
            now = datetime.now(UTC)
            deal = Deal(
                name=f"Follow-up test {uuid4()}",
                value=Decimal("25000.00"),
                stage="Proposal",
                owner_name="Jordan Lee",
                stage_entered_at=now - timedelta(days=10),
                last_activity_at=now - timedelta(days=8),
                next_follow_up_at=None,
                status="ACTIVE",
            )
            session.add(deal)
            await session.flush()
            incident = BottleneckIncident(
                deal_id=deal.id,
                incident_type="STALLED_DEAL",
                title="Test stalled deal",
                severity="high",
                risk_score=85,
                evidence={"stage_age": {"triggered": True}},
                status="OPEN",
            )
            session.add(incident)
            await session.flush()
            session.add(
                AgentAnalysis(
                    incident_id=incident.id,
                    model_name="gemini-test",
                    trigger="MANUAL",
                    input_fingerprint="follow-up-test",
                    summary="The deal is stalled.",
                    root_cause="No recent follow-up.",
                    supporting_evidence=["Stage SLA exceeded."],
                    risk_explanation="The opportunity may be lost.",
                    recommended_action="Contact the buyer and confirm next steps.",
                    action_type=action_type,
                    confidence=0.9,
                    approval_required=approval_required,
                    policy_references=["Stalled-Deal Handling"],
                    expected_outcome="The deal returns to active motion.",
                    status="COMPLETED",
                )
            )
            await session.commit()
            created_deal_ids.append(deal.id)
            return incident.id, deal.id

    assert client.portal is not None
    return client.portal.call(create)


def execute(client: TestClient, headers: dict[str, str], incident_id: UUID):
    return client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=headers,
    )


def test_successful_execution(client: TestClient, auth_headers: dict[str, str]) -> None:
    incident_id, deal_id = create_action_context(client)
    response = execute(client, auth_headers, incident_id)
    assert response.status_code == 200
    task = response.json()
    assert UUID(task["deal_id"]) == deal_id
    assert task["assigned_to"] == "Jordan Lee"
    assert task["description"] == "Contact the buyer and confirm next steps."
    assert task["status"] == "PENDING"
    due_at = datetime.fromisoformat(task["due_at"])

    async def due_hours() -> int:
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            return settings.follow_up_due_hours

    assert client.portal is not None
    expected_hours = client.portal.call(due_hours)
    remaining = due_at - datetime.now(UTC)
    assert timedelta(hours=expected_hours) - timedelta(minutes=1) < remaining
    assert remaining <= timedelta(hours=expected_hours)


def test_invalid_recommendation(client: TestClient, auth_headers: dict[str, str]) -> None:
    incident_id, _ = create_action_context(client, action_type="SEND_MANAGER_ALERT")
    response = execute(client, auth_headers, incident_id)
    assert response.status_code == 409
    assert "does not recommend CREATE_FOLLOW_UP" in response.json()["detail"]


def test_approval_required_recommendation_is_not_executed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    incident_id, _ = create_action_context(client, approval_required=True)

    response = execute(client, auth_headers, incident_id)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The recommended follow-up requires human approval before execution."
    )


def test_duplicate_execution(client: TestClient, auth_headers: dict[str, str]) -> None:
    incident_id, _ = create_action_context(client)
    first = execute(client, auth_headers, incident_id)
    second = execute(client, auth_headers, incident_id)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    async def count_tasks() -> int:
        async with async_session_factory() as session:
            return cast(
                int,
                await session.scalar(
                    select(func.count())
                    .select_from(FollowUpTask)
                    .where(FollowUpTask.incident_id == incident_id)
                ),
            )

    assert client.portal is not None
    assert client.portal.call(count_tasks) == 1


def test_unknown_incident(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert execute(client, auth_headers, uuid4()).status_code == 404


def test_authentication(client: TestClient) -> None:
    response = client.post(f"/api/incidents/{uuid4()}/actions/create-follow-up")
    assert response.status_code == 401


def test_incident_status_update(client: TestClient, auth_headers: dict[str, str]) -> None:
    incident_id, _ = create_action_context(client)
    assert execute(client, auth_headers, incident_id).status_code == 200

    async def get_status() -> str:
        async with async_session_factory() as session:
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            return incident.status

    assert client.portal is not None
    assert client.portal.call(get_status) == "observing"


def test_audit_creation(client: TestClient, auth_headers: dict[str, str]) -> None:
    incident_id, _ = create_action_context(client)
    response = execute(client, auth_headers, incident_id)
    assert response.status_code == 200

    async def get_event() -> AgentAuditEvent:
        async with async_session_factory() as session:
            event = await session.scalar(
                select(AgentAuditEvent).where(
                    AgentAuditEvent.incident_id == incident_id,
                    AgentAuditEvent.event_type == "CREATE_FOLLOW_UP",
                )
            )
            assert event is not None
            return event

    assert client.portal is not None
    event = client.portal.call(get_event)
    assert event.status == "COMPLETED"
    assert event.details["task_id"] == response.json()["id"]
    assert event.details["result_status"] == "PENDING"
    assert event.details["before"]["incident_status"] == "OPEN"
    assert event.details["after"]["incident_status"] == "observing"


def test_adapter_failure_rolls_back_task_and_incident(client: TestClient) -> None:
    incident_id, _ = create_action_context(client)

    class FailingAdapter:
        async def create_follow_up(self, request: CRMFollowUpRequest):
            raise RuntimeError("CRM unavailable")

    async def execute_failure() -> tuple[int, str]:
        async with async_session_factory() as session:
            with pytest.raises(ActionExecutionError) as error:
                await create_follow_up_task(
                    session,
                    incident_id,
                    None,
                    crm_adapter=FailingAdapter(),
                )
            assert error.value.status_code == 502
        async with async_session_factory() as session:
            task_count = await session.scalar(
                select(func.count())
                .select_from(FollowUpTask)
                .where(FollowUpTask.incident_id == incident_id)
            )
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            return task_count or 0, incident.status

    assert client.portal is not None
    task_count, incident_status = client.portal.call(execute_failure)
    assert task_count == 0
    assert incident_status == "OPEN"


def test_completed_task_allows_new_active_task_and_history(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    incident_id, _ = create_action_context(client)
    first = execute(client, auth_headers, incident_id)
    assert first.status_code == 200

    async def complete_first() -> None:
        async with async_session_factory() as session:
            task = await session.get(FollowUpTask, UUID(first.json()["id"]))
            assert task is not None
            task.status = "COMPLETED"
            task.completed_at = datetime.now(UTC)
            await session.commit()

    assert client.portal is not None
    client.portal.call(complete_first)
    second = execute(client, auth_headers, incident_id)
    assert second.status_code == 200
    assert second.json()["id"] != first.json()["id"]

    history = client.get(
        f"/api/incidents/{incident_id}/actions", headers=auth_headers
    )
    assert history.status_code == 200
    assert [item["status"] for item in history.json()] == ["PENDING", "COMPLETED"]