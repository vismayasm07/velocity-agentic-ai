import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.database import async_session_factory, engine
from app.main import app
from app.models import (
    AgentAnalysis,
    AgentAuditEvent,
    BottleneckIncident,
    Deal,
    IncidentOutcome,
    MonitoringSettings,
    User,
)
from app.outcomes import reopen_recurred_incidents, verify_incident_outcome
from app.security import create_access_token, hash_password


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
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_context(client: TestClient) -> UUID:
    async def create() -> UUID:
        async with async_session_factory() as session:
            now = datetime.now(UTC)
            deal = Deal(
                name=f"Outcome test {uuid4()}",
                value=Decimal("48000.00"),
                stage="Proposal",
                owner_name="Jordan Lee",
                stage_entered_at=now - timedelta(days=14),
                last_activity_at=now - timedelta(days=10),
                next_follow_up_at=now - timedelta(days=3),
                status="active",
            )
            session.add(deal)
            await session.flush()
            incident = BottleneckIncident(
                deal_id=deal.id,
                incident_type="STALLED_DEAL",
                title="Outcome verification test",
                severity="critical",
                risk_score=100,
                evidence={"total": 100},
                status="open",
            )
            session.add(incident)
            await session.flush()
            session.add(
                AgentAnalysis(
                    incident_id=incident.id,
                    model_name="gemini-test",
                    trigger="MANUAL",
                    input_fingerprint=str(uuid4()),
                    summary="Stalled deal",
                    root_cause="No activity",
                    supporting_evidence=["No activity"],
                    risk_explanation="High risk",
                    recommended_action="Contact the buyer.",
                    action_type="CREATE_FOLLOW_UP",
                    confidence=0.95,
                    approval_required=False,
                    policy_references=[],
                    expected_outcome="Activity resumes",
                    status="COMPLETED",
                )
            )
            await session.commit()
            created_deal_ids.append(deal.id)
            return incident.id

    assert client.portal is not None
    return client.portal.call(create)


def test_action_schedules_one_outcome_check(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id = create_context(client)
    first = client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=admin_headers,
    )
    second = client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=admin_headers,
    )
    assert first.status_code == second.status_code == 200
    outcomes = client.get(
        f"/api/incidents/{incident_id}/outcomes", headers=admin_headers
    )
    assert outcomes.status_code == 200
    assert len(outcomes.json()) == 1
    assert outcomes.json()[0]["outcome"] == "AWAITING_EVIDENCE"
    assert outcomes.json()[0]["next_check_at"] is not None


def test_verify_outcome_requires_admin(client: TestClient, admin_headers: dict[str, str]) -> None:
    incident_id = create_context(client)
    assert client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=admin_headers,
    ).status_code == 200

    async def user_token() -> str:
        async with async_session_factory() as session:
            user = User(
                email=f"outcome-{uuid4()}@example.com",
                password_hash=hash_password("TemporaryPassword@2026"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            token, _ = create_access_token(user.id)
            return token

    assert client.portal is not None
    token = client.portal.call(user_token)
    assert client.post(
        f"/api/incidents/{incident_id}/verify-outcome",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 403


def test_fresh_healthy_evidence_resolves_without_new_analysis(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id = create_context(client)
    assert client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=admin_headers,
    ).status_code == 200

    async def make_healthy() -> int:
        async with async_session_factory() as session:
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            deal = await session.get(Deal, incident.deal_id)
            assert deal is not None
            now = datetime.now(UTC)
            deal.stage = "Negotiation"
            deal.stage_entered_at = now
            deal.last_activity_at = now
            deal.next_follow_up_at = now + timedelta(days=2)
            count = await session.scalar(
                select(func.count())
                .select_from(AgentAnalysis)
                .where(AgentAnalysis.incident_id == incident_id)
            )
            await session.commit()
            return int(count or 0)

    before = client.portal.call(make_healthy)
    response = client.post(
        f"/api/incidents/{incident_id}/verify-outcome", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "SUCCESSFUL"
    assert response.json()["current_risk_score"] == 0
    detail = client.get(f"/api/incidents/{incident_id}", headers=admin_headers).json()
    assert detail["status"] == "resolved"
    assert detail["outcomes"][0]["verification_evidence"]["activity_resumed"] is True

    async def counts() -> tuple[int, set[str]]:
        async with async_session_factory() as session:
            analyses = await session.scalar(
                select(func.count())
                .select_from(AgentAnalysis)
                .where(AgentAnalysis.incident_id == incident_id)
            )
            events = set(
                await session.scalars(
                    select(AgentAuditEvent.event_type).where(
                        AgentAuditEvent.incident_id == incident_id
                    )
                )
            )
            return int(analyses or 0), events

    after, events = client.portal.call(counts)
    assert after == before
    assert {"OBSERVATION_STARTED", "OUTCOME_CHECK_STARTED", "OUTCOME_EVIDENCE_COLLECTED", "RISK_SCORE_CHANGED", "INCIDENT_RESOLVED"} <= events


def test_unchanged_evidence_retries_then_escalates_at_maximum(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    incident_id = create_context(client)
    assert client.post(
        f"/api/incidents/{incident_id}/actions/create-follow-up",
        headers=admin_headers,
    ).status_code == 200

    async def verify_twice() -> tuple[str, str, int]:
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            original_maximum = settings.maximum_outcome_checks
            settings.maximum_outcome_checks = 2
            await session.commit()
        async with async_session_factory() as session:
            first = await verify_incident_outcome(session, incident_id, force=True)
            first_outcome = first.outcome
        async with async_session_factory() as session:
            second = await verify_incident_outcome(session, incident_id, force=True)
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            second_outcome = second.outcome
            status = incident.status
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.maximum_outcome_checks = original_maximum
            await session.commit()
        return first_outcome, second_outcome, 1 if status == "escalated" else 0

    assert client.portal is not None
    first, second, escalated = client.portal.call(verify_twice)
    assert first == "AWAITING_EVIDENCE"
    assert second == "FAILED"
    assert escalated == 1


def test_resolved_incident_reopens_on_recurrence(client: TestClient) -> None:
    incident_id = create_context(client)

    async def recur() -> tuple[str, str, set[str]]:
        async with async_session_factory() as session:
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            incident.status = "resolved"
            incident.analysis_state = "ANALYZED"
            session.add(
                IncidentOutcome(
                    incident_id=incident.id,
                    action_type="CREATE_FOLLOW_UP",
                    action_id=uuid4(),
                    verification_status="COMPLETED",
                    previous_risk_score=100,
                    current_risk_score=0,
                    verification_evidence={},
                    outcome="SUCCESSFUL",
                    verified_at=datetime.now(UTC),
                )
            )
            await session.commit()
        async with async_session_factory() as session:
            reopened = await reopen_recurred_incidents(session)
            assert any(item.id == incident_id for item in reopened)
        async with async_session_factory() as session:
            incident = await session.get(BottleneckIncident, incident_id)
            latest = await session.scalar(
                select(IncidentOutcome)
                .where(IncidentOutcome.incident_id == incident_id)
                .order_by(IncidentOutcome.created_at.desc())
            )
            events = set(
                await session.scalars(
                    select(AgentAuditEvent.event_type).where(
                        AgentAuditEvent.incident_id == incident_id
                    )
                )
            )
            assert incident is not None and latest is not None
            return incident.status, latest.outcome, events

    assert client.portal is not None
    status, outcome, events = client.portal.call(recur)
    assert status == "open"
    assert outcome == "RECURRED"
    assert "INCIDENT_RECURRED" in events