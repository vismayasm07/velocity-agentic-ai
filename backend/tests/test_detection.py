from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.detection import (
    OwnerOverloadRules,
    OwnerWorkload,
    detect_owner_overload,
    detect_stalled_deal,
    run_owner_overload_scan,
)
from app.main import app
from app.models import BottleneckIncident, Deal, MonitoringSettings, SalesOwnerCapacity


def make_deal(
    *,
    stage_days: int,
    inactive_days: int,
    follow_up_days_ago: int | None = None,
) -> tuple[Deal, datetime]:
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    return Deal(
        name="Detection Test Deal",
        value=Decimal("50000.00"),
        stage="Proposal",
        owner_name="Test Owner",
        stage_entered_at=now - timedelta(days=stage_days),
        last_activity_at=now - timedelta(days=inactive_days),
        next_follow_up_at=(
            now - timedelta(days=follow_up_days_ago)
            if follow_up_days_ago is not None
            else None
        ),
        status="active",
    ), now


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_healthy_deal_produces_no_incident() -> None:
    deal, now = make_deal(stage_days=2, inactive_days=1)
    assert not detect_stalled_deal(deal, now).is_stalled


def test_inactive_deal_produces_incident() -> None:
    deal, now = make_deal(stage_days=16, inactive_days=12)
    result = detect_stalled_deal(deal, now)
    assert result.is_stalled
    assert result.evidence["activity_gap"] == {
        "days": 12,
        "threshold_days": 5,
        "points": 45,
        "triggered": True,
    }


def test_overdue_follow_up_increases_risk() -> None:
    current, now = make_deal(stage_days=7, inactive_days=4)
    overdue, _ = make_deal(stage_days=7, inactive_days=4, follow_up_days_ago=2)
    assert detect_stalled_deal(overdue, now).risk_score > detect_stalled_deal(current, now).risk_score


def test_risk_score_remains_between_zero_and_one_hundred() -> None:
    deal, now = make_deal(stage_days=500, inactive_days=500, follow_up_days_ago=500)
    assert 0 <= detect_stalled_deal(deal, now).risk_score <= 100


def test_owner_below_thresholds_produces_no_overload() -> None:
    result = detect_owner_overload(
        OwnerWorkload("Owner", 4, Decimal("40000"), 1, 0, 0),
        OwnerOverloadRules(5, 2, 1, Decimal("50000")),
    )
    assert result.is_overloaded is False


def test_owner_workload_factors_increase_bounded_risk() -> None:
    rules = OwnerOverloadRules(5, 1, 1, Decimal("50000"))
    active_only = detect_owner_overload(
        OwnerWorkload("Owner", 6, Decimal("10000"), 0, 0, 0), rules
    )
    combined = detect_owner_overload(
        OwnerWorkload("Owner", 6, Decimal("100000"), 3, 4, 12), rules
    )
    assert active_only.is_overloaded is True
    assert combined.risk_score > active_only.risk_score
    assert 0 <= combined.risk_score <= 100
    assert combined.evidence["high_risk_deals"]["triggered"] is True
    assert combined.evidence["overdue_follow_ups"]["triggered"] is True


def test_repeated_scans_do_not_create_duplicates() -> None:
    with TestClient(app) as client:
        headers = login(client)
        first = client.post("/api/detection/scan", headers=headers)
        second = client.post("/api/detection/scan", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        first_ids = {incident["id"] for incident in first.json()}
        second_ids = {incident["id"] for incident in second.json()}
        assert first_ids
        assert first_ids == second_ids


def test_owner_overload_lifecycle_uses_current_deals() -> None:
    owner_name = f"Owner {uuid4()}"

    original_settings: dict[str, object] = {}
    owner_id = None

    async def exercise_lifecycle() -> tuple[str, int, str]:
        nonlocal owner_id
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            original_settings.update({
                "owner_overload_enabled": settings.owner_overload_enabled,
                "owner_max_active_deals": settings.owner_max_active_deals,
                "owner_max_high_risk_deals": settings.owner_max_high_risk_deals,
                "owner_max_overdue_follow_ups": settings.owner_max_overdue_follow_ups,
                "owner_max_pipeline_value": settings.owner_max_pipeline_value,
            })
            owner = SalesOwnerCapacity(
                owner_name=owner_name,
                active_deals=99,
                max_active_deals=99,
                is_active=True,
            )
            now = datetime.now(UTC)
            deals = [
                Deal(
                    name=f"Owner overload test {index}",
                    value=Decimal("1000"),
                    stage="Qualification",
                    owner_name=owner_name,
                    stage_entered_at=now,
                    last_activity_at=now,
                    next_follow_up_at=None,
                    status="active",
                )
                for index in range(2)
            ]
            session.add_all([owner, *deals])
            settings.owner_overload_enabled = True
            settings.owner_max_active_deals = 1
            settings.owner_max_high_risk_deals = 100
            settings.owner_max_overdue_follow_ups = 100
            settings.owner_max_pipeline_value = None
            await session.commit()
            owner_id = owner.id
            owner_filter = {owner.id}
            first = await run_owner_overload_scan(
                session, settings, owner_capacity_ids=owner_filter
            )
            second = await run_owner_overload_scan(
                session, settings, owner_capacity_ids=owner_filter
            )
            incident = next(
                item for item in first.incidents if item.owner_capacity_id == owner.id
            )
            assert incident.evidence["active_deals"]["value"] == 2
            assert incident.evidence["active_deals"]["triggered"] is True
            for deal in deals:
                deal.status = "closed"
            await session.commit()
            await run_owner_overload_scan(
                session, settings, owner_capacity_ids=owner_filter
            )
            await session.refresh(incident)
            owner_incidents_second = [
                item for item in second.incidents if item.owner_capacity_id == owner.id
            ]
            return str(incident.id), len(owner_incidents_second), incident.status

    async def cleanup() -> None:
        assert owner_id is not None
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            for field, value in original_settings.items():
                setattr(settings, field, value)
            await session.execute(
                delete(BottleneckIncident).where(
                    BottleneckIncident.owner_capacity_id == owner_id
                )
            )
            await session.execute(delete(Deal).where(Deal.owner_name == owner_name))
            await session.execute(
                delete(SalesOwnerCapacity).where(SalesOwnerCapacity.id == owner_id)
            )
            await session.commit()

    with TestClient(app) as client:
        assert client.portal is not None
        try:
            incident_id, second_count, final_status = client.portal.call(exercise_lifecycle)
            assert second_count == 1
            assert final_status == "resolved"

            response = client.get(f"/api/incidents/{incident_id}", headers=login(client))
            assert response.status_code == 200
            detail = response.json()
            assert detail["deal_id"] is None
            assert detail["affected_deal"] is None
            assert detail["affected_owner"]["owner_name"] == owner_name

            follow_up = client.post(
                f"/api/incidents/{incident_id}/actions/create-follow-up",
                headers=login(client),
            )
            assert follow_up.status_code == 409
            assert follow_up.json()["detail"] == "Follow-up creation requires a deal-level incident."

            reassignment = client.post(
                f"/api/incidents/{incident_id}/actions/request-reassignment",
                headers=login(client),
                json={"proposed_owner": None},
            )
            assert reassignment.status_code == 409
            assert "Select an affected deal" in reassignment.json()["detail"]
        finally:
            client.portal.call(cleanup)


def test_incident_listing_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/incidents").status_code == 401
        response = client.get("/api/incidents", headers=login(client))
        assert response.status_code == 200
        assert all(0 <= incident["risk_score"] <= 100 for incident in response.json())


def test_incident_detail_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.get(f"/api/incidents/{uuid4()}").status_code == 401


def test_incident_detail_returns_evidence_and_affected_deal() -> None:
    with TestClient(app) as client:
        headers = login(client)
        incidents = client.post("/api/detection/scan", headers=headers).json()
        response = client.get(f"/api/incidents/{incidents[0]['id']}", headers=headers)
        assert response.status_code == 200
        detail = response.json()
        assert detail["id"] == incidents[0]["id"]
        assert detail["evidence"]["total"] == detail["risk_score"]
        assert detail["affected_deal"]["id"] == detail["deal_id"]
        assert {
            "stage",
            "value",
            "owner_name",
            "stage_entered_at",
            "last_activity_at",
            "next_follow_up_at",
        } <= detail["affected_deal"].keys()


def test_unknown_incident_detail_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/incidents/{uuid4()}", headers=login(client))
        assert response.status_code == 404
        assert response.json() == {"detail": "Incident not found"}