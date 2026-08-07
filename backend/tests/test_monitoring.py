import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

import app.detection as detection
from app.database import async_session_factory, engine
from app.detection import (
    DetectionRules,
    DetectionScanResult,
    detect_stalled_deal,
    run_stalled_deal_scan,
)
from app.main import app
from app.models import AgentAnalysis, AgentAuditEvent, BottleneckIncident, Deal, MonitoringRun, MonitoringSettings, User
import app.monitoring as monitoring_module
from app.monitoring import ProactiveMonitoringService
from app.security import create_access_token, hash_password


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_monitoring_status_and_history_require_authentication(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/monitoring/status").status_code == 401
    assert client.get("/api/monitoring/runs").status_code == 401

    status = client.get("/api/monitoring/status", headers=auth_headers)
    history = client.get("/api/monitoring/runs", headers=auth_headers)
    assert status.status_code == 200
    assert history.status_code == 200
    assert status.json()["enabled"] is True
    assert status.json()["active"] is True
    settings = client.get("/api/monitoring/settings", headers=auth_headers)
    assert settings.status_code == 200
    assert status.json()["interval_seconds"] == settings.json()["scan_interval_seconds"]
    assert history.json()


def test_admin_can_read_and_update_monitoring_settings(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/monitoring/settings").status_code == 401
    current = client.get("/api/monitoring/settings", headers=auth_headers)
    assert current.status_code == 200
    original = current.json()

    update = {
        "monitoring_enabled": original["monitoring_enabled"],
        "scan_interval_seconds": 5,
        "stage_sla_hours": original["stage_sla_hours"],
        "inactivity_threshold_hours": 121,
        "overdue_follow_up_enabled": original["overdue_follow_up_enabled"],
        "automatic_rca_enabled": True,
        "automatic_rca_min_risk_score": 75,
        "automatic_safe_actions_enabled": True,
        "follow_up_due_hours": 36,
        "high_impact_actions_disabled": original["high_impact_actions_disabled"],
    }
    invalid = client.put(
        "/api/monitoring/settings",
        headers=auth_headers,
        json={**update, "scan_interval_seconds": 4},
    )
    assert invalid.status_code == 422
    assert client.put(
        "/api/monitoring/settings",
        headers=auth_headers,
        json={**update, "automatic_rca_min_risk_score": 101},
    ).status_code == 422

    saved = client.put(
        "/api/monitoring/settings", headers=auth_headers, json=update
    )
    assert saved.status_code == 200
    assert saved.json()["inactivity_threshold_hours"] == 121
    assert saved.json()["automatic_safe_actions_enabled"] is True
    assert saved.json()["follow_up_due_hours"] == 36

    async def latest_audit() -> AgentAuditEvent | None:
        async with async_session_factory() as session:
            return await session.scalar(
                select(AgentAuditEvent)
                .where(AgentAuditEvent.event_type == "MONITORING_SETTINGS_UPDATED")
                .order_by(AgentAuditEvent.created_at.desc())
            )

    assert client.portal is not None
    audit = client.portal.call(latest_audit)
    assert audit is not None
    assert audit.details["old"]["inactivity_threshold_hours"] == original[
        "inactivity_threshold_hours"
    ]
    assert audit.details["new"]["inactivity_threshold_hours"] == 121

    restore = {field: original[field] for field in update}
    assert client.put(
        "/api/monitoring/settings", headers=auth_headers, json=restore
    ).status_code == 200


def test_non_admin_cannot_manage_monitoring_settings(client: TestClient) -> None:
    async def create_user() -> tuple[User, str]:
        async with async_session_factory() as session:
            user = User(
                email=f"monitoring-{uuid4()}@example.com",
                password_hash=hash_password("TemporaryPassword@2026"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            token, _ = create_access_token(user.id)
            return user, token

    async def delete_user(user_id: object) -> None:
        async with async_session_factory() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()

    assert client.portal is not None
    user, token = client.portal.call(create_user)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/monitoring/settings", headers=headers).status_code == 403
    assert client.put(
        "/api/monitoring/settings",
        headers=headers,
        json={
            "monitoring_enabled": True,
            "scan_interval_seconds": 60,
            "stage_sla_hours": 168,
            "inactivity_threshold_hours": 120,
            "overdue_follow_up_enabled": True,
            "automatic_rca_enabled": False,
            "automatic_rca_min_risk_score": 80,
            "automatic_safe_actions_enabled": False,
            "follow_up_due_hours": 24,
        },
    ).status_code == 403
    client.portal.call(delete_user, user.id)


def test_detector_uses_runtime_thresholds() -> None:
    now = datetime.now(UTC)
    deal = Deal(
        name="Runtime threshold deal",
        value=Decimal("10000.00"),
        stage="Proposal",
        owner_name="Test Owner",
        stage_entered_at=now - timedelta(hours=200),
        last_activity_at=now - timedelta(hours=130),
        next_follow_up_at=now - timedelta(days=4),
        status="active",
    )
    relaxed = detect_stalled_deal(
        deal,
        now,
        DetectionRules(200, 130, False),
    )
    strict = detect_stalled_deal(
        deal,
        now,
        DetectionRules(24, 24, True),
    )
    assert relaxed.risk_score == 0
    assert strict.risk_score >= 40
    assert strict.evidence["activity_gap"]["threshold_hours"] == 24


def test_cycle_persists_statistics_and_audit_event(client: TestClient) -> None:
    async def execute() -> tuple[MonitoringRun, list[str]]:
        service = ProactiveMonitoringService(enabled=False, interval_seconds=60)
        run = await service.run_once()
        assert run is not None
        async with async_session_factory() as session:
            event_types = list(
                await session.scalars(
                    select(AgentAuditEvent.event_type).where(
                        AgentAuditEvent.monitoring_run_id == run.id
                    )
                )
            )
        return run, event_types

    assert client.portal is not None
    run, event_types = client.portal.call(execute)
    assert run.status == "COMPLETED"
    assert run.completed_at is not None
    assert run.deals_scanned > 0
    assert run.incidents_created >= 0
    assert run.incidents_updated >= 0
    assert run.errors_encountered == 0
    assert event_types.count("MONITORING_CYCLE") == 1
    assert set(event_types) <= {
        "MONITORING_CYCLE",
        "AUTOMATIC_ANALYSIS_STARTED",
        "AUTOMATIC_ANALYSIS_COMPLETED",
        "AUTOMATIC_ANALYSIS_FAILED",
        "AUTOMATIC_ANALYSIS_SKIPPED",
        "OUTCOME_VERIFICATION_FAILED",
    }


def test_disabled_service_does_not_start(client: TestClient) -> None:
    async def execute() -> tuple[bool, bool]:
        service = ProactiveMonitoringService(enabled=False, interval_seconds=60)
        await service.start()
        active_after_start = service.active
        await service.stop()
        return active_after_start, service.active

    assert client.portal is not None
    assert client.portal.call(execute) == (False, False)


def test_scheduler_invokes_detector_and_stops_cleanly(client: TestClient) -> None:
    async def execute() -> tuple[int, bool]:
        invoked = asyncio.Event()
        calls = 0

        async def scan(_session: object) -> DetectionScanResult:
            nonlocal calls
            calls += 1
            invoked.set()
            return DetectionScanResult([], 3, 1, 2, [])

        service = ProactiveMonitoringService(
            enabled=True,
            interval_seconds=3600,
            scan=scan,
        )
        await service.start()
        await invoked.wait()
        await service.stop()
        return calls, service.active

    assert client.portal is not None
    assert client.portal.call(execute) == (1, False)


def test_overlapping_cycle_is_rejected(client: TestClient) -> None:
    async def execute() -> bool:
        invoked = asyncio.Event()
        release = asyncio.Event()

        async def scan(_session: object) -> DetectionScanResult:
            invoked.set()
            await release.wait()
            return DetectionScanResult([], 1, 0, 0, [])

        service = ProactiveMonitoringService(
            enabled=False,
            interval_seconds=60,
            scan=scan,
        )
        first = asyncio.create_task(service.run_once())
        await invoked.wait()
        overlap = await service.run_once()
        release.set()
        await first
        return overlap is None

    assert client.portal is not None
    assert client.portal.call(execute) is True


def test_one_deal_failure_does_not_abort_cycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def execute() -> tuple[int, int, bool]:
        now = datetime.now(UTC)
        failing = Deal(
            name=f"Failing monitoring deal {uuid4()}",
            value=Decimal("10000.00"),
            stage="Proposal",
            owner_name="Test Owner",
            stage_entered_at=now - timedelta(days=20),
            last_activity_at=now - timedelta(days=15),
            next_follow_up_at=now - timedelta(days=5),
            status="active",
        )
        successful = Deal(
            name=f"Successful monitoring deal {uuid4()}",
            value=Decimal("20000.00"),
            stage="Proposal",
            owner_name="Test Owner",
            stage_entered_at=now - timedelta(days=20),
            last_activity_at=now - timedelta(days=15),
            next_follow_up_at=now - timedelta(days=5),
            status="active",
        )
        async with async_session_factory() as session:
            session.add_all([failing, successful])
            await session.commit()
            failing_id = failing.id
            successful_id = successful.id

        original_detector = detection.detect_stalled_deal

        def fail_one_deal(
            deal: Deal,
            detected_at: datetime | None = None,
            rules: DetectionRules | None = None,
        ):
            if deal.id == failing_id:
                raise ValueError("controlled test failure")
            return original_detector(deal, detected_at, rules)

        monkeypatch.setattr(detection, "detect_stalled_deal", fail_one_deal)
        async with async_session_factory() as session:
            result = await run_stalled_deal_scan(session)
        successful_detected = any(
            incident.deal_id == successful_id for incident in result.incidents
        )
        async with async_session_factory() as session:
            await session.execute(delete(Deal).where(Deal.id.in_([failing_id, successful_id])))
            await session.commit()
        return result.deals_scanned, len(result.errors), successful_detected

    assert client.portal is not None
    deals_scanned, errors, successful_detected = client.portal.call(execute)
    assert deals_scanned >= 2
    assert errors == 1
    assert successful_detected is True


def test_automatic_rca_eligibility_deduplication_and_runtime_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def execute() -> tuple[list[object], object, object, tuple[int, int, int], int, int]:
        calls: list[object] = []
        now = datetime.now(UTC)
        high_deal = Deal(
            name=f"Automatic RCA high risk {uuid4()}",
            value=Decimal("50000.00"),
            stage="Proposal",
            owner_name="RCA Owner",
            stage_entered_at=now - timedelta(days=30),
            last_activity_at=now - timedelta(days=20),
            next_follow_up_at=now - timedelta(days=10),
            status="active",
        )
        low_deal = Deal(
            name=f"Automatic RCA low risk {uuid4()}",
            value=Decimal("10000.00"),
            stage="Proposal",
            owner_name="RCA Owner",
            stage_entered_at=now - timedelta(days=30),
            last_activity_at=now - timedelta(days=6),
            next_follow_up_at=now + timedelta(days=1),
            status="active",
        )
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.stage_sla_hours = 168
            settings.inactivity_threshold_hours = 120
            settings.overdue_follow_up_enabled = True
            settings.automatic_rca_enabled = True
            settings.automatic_rca_min_risk_score = 80
            session.add_all([high_deal, low_deal])
            await session.commit()
            deal_ids = [high_deal.id, low_deal.id]

        async def fake_analyze(session, incident_id, **kwargs):
            calls.append(incident_id)
            incident = await session.get(BottleneckIncident, incident_id)
            assert incident is not None
            incident.analysis_state = "ANALYZED"
            incident.analysis_fingerprint = f"fingerprint-{incident_id}"
            await session.commit()
            return None

        monkeypatch.setattr(monitoring_module, "analyze_incident", fake_analyze)
        service = ProactiveMonitoringService(enabled=True, interval_seconds=60)
        first = await service.run_once()
        calls_after_first = len(calls)
        second = await service.run_once()
        calls_after_second = len(calls)
        assert first is not None and second is not None

        async with async_session_factory() as session:
            high_incident_id = await session.scalar(
                select(BottleneckIncident.id).where(BottleneckIncident.deal_id == high_deal.id)
            )
            low_incident_id = await session.scalar(
                select(BottleneckIncident.id).where(BottleneckIncident.deal_id == low_deal.id)
            )
            assert high_incident_id is not None and low_incident_id is not None
            skipped = await session.scalar(
                select(func.count(AgentAuditEvent.id)).where(
                    AgentAuditEvent.monitoring_run_id == first.id,
                    AgentAuditEvent.event_type == "AUTOMATIC_ANALYSIS_SKIPPED",
                )
            )
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.automatic_rca_enabled = False
            await session.commit()

        third = await service.run_once()
        calls_after_third = len(calls)
        assert third is not None
        async with async_session_factory() as session:
            await session.execute(delete(Deal).where(Deal.id.in_(deal_ids)))
            await session.commit()
        return (
            calls,
            high_incident_id,
            low_incident_id,
            (calls_after_first, calls_after_second, calls_after_third),
            skipped or 0,
            first.errors_encountered,
        )

    assert client.portal is not None
    calls, high_incident_id, low_incident_id, call_counts, skipped, errors = client.portal.call(execute)
    assert calls.count(high_incident_id) == 1
    assert low_incident_id not in calls
    assert call_counts[0] == call_counts[1] == call_counts[2]
    assert skipped >= 1
    assert errors == 0


def test_automatic_rca_failure_does_not_fail_monitoring_cycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def execute() -> tuple[str, int]:
        now = datetime.now(UTC)
        deal = Deal(
            name=f"Automatic RCA failure {uuid4()}",
            value=Decimal("60000.00"),
            stage="Proposal",
            owner_name="RCA Owner",
            stage_entered_at=now - timedelta(days=30),
            last_activity_at=now - timedelta(days=20),
            next_follow_up_at=now - timedelta(days=10),
            status="active",
        )
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.automatic_rca_enabled = True
            settings.automatic_rca_min_risk_score = 80
            session.add(deal)
            await session.commit()
            deal_id = deal.id

        async def fail_analysis(*args, **kwargs):
            raise monitoring_module.AnalysisWorkflowError(
                "GEMINI_TIMEOUT", "Provider timed out", status_code=503
            )

        monkeypatch.setattr(monitoring_module, "analyze_incident", fail_analysis)
        service = ProactiveMonitoringService(enabled=True, interval_seconds=60)
        run = await service.run_once()
        assert run is not None
        async with async_session_factory() as session:
            incident_count = await session.scalar(
                select(func.count(BottleneckIncident.id)).where(
                    BottleneckIncident.deal_id == deal_id
                )
            )
            await session.execute(delete(Deal).where(Deal.id == deal_id))
            await session.commit()
        return run.status, incident_count or 0

    assert client.portal is not None
    status, incident_count = client.portal.call(execute)
    assert status == "COMPLETED"
    assert incident_count == 1


@pytest.mark.parametrize(
    ("safe_actions_enabled", "action_type", "approval_required", "confidence", "expected"),
    [
        (True, "CREATE_FOLLOW_UP", False, 0.90, 1),
        (False, "CREATE_FOLLOW_UP", False, 0.90, 0),
        (True, "CREATE_FOLLOW_UP", True, 0.90, 0),
        (True, "CREATE_FOLLOW_UP", False, 0.79, 0),
        (True, "SEND_MANAGER_ALERT", False, 0.90, 0),
    ],
)
def test_automatic_safe_action_gates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    safe_actions_enabled: bool,
    action_type: str,
    approval_required: bool,
    confidence: float,
    expected: int,
) -> None:
    async def execute() -> int:
        now = datetime.now(UTC)
        deal = Deal(
            name=f"Automatic action gate {uuid4()}",
            value=Decimal("50000.00"),
            stage="Proposal",
            owner_name="Action Owner",
            stage_entered_at=now - timedelta(days=30),
            last_activity_at=now - timedelta(days=20),
            next_follow_up_at=now - timedelta(days=10),
            status="active",
        )
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.automatic_rca_enabled = True
            settings.automatic_rca_min_risk_score = 80
            settings.automatic_safe_actions_enabled = safe_actions_enabled
            settings.follow_up_due_hours = 36
            session.add(deal)
            await session.flush()
            incident = BottleneckIncident(
                deal_id=deal.id,
                incident_type="STALLED_DEAL",
                title="Automatic action gate",
                severity="high",
                risk_score=90,
                evidence={"stage_age": {"triggered": True}},
                status="open",
            )
            session.add(incident)
            run = MonitoringRun(
                started_at=now,
                completed_at=now,
                deals_scanned=1,
                incidents_created=1,
                incidents_updated=0,
                errors_encountered=0,
                status="COMPLETED",
            )
            session.add(run)
            await session.commit()
            incident_id = incident.id
            deal_id = deal.id
            run_id = run.id

        action_calls: list[dict[str, object]] = []

        async def fake_analyze(*args, **kwargs):
            return SimpleNamespace(
                id=uuid4(),
                status="COMPLETED",
                action_type=action_type,
                approval_required=approval_required,
                confidence=confidence,
            )

        async def fake_create(*args, **kwargs):
            action_calls.append(kwargs)

        monkeypatch.setattr(monitoring_module, "analyze_incident", fake_analyze)
        monkeypatch.setattr(monitoring_module, "create_follow_up_task", fake_create)
        service = ProactiveMonitoringService(enabled=True, interval_seconds=60)
        result = DetectionScanResult(
            incidents=[],
            deals_scanned=1,
            incidents_created=1,
            incidents_updated=0,
            errors=[],
            analysis_candidate_ids=(incident_id,),
        )
        await service._run_automatic_rca(result, settings, run_id)
        if action_calls:
            assert action_calls[0]["execution_source"] == "AUTOMATIC"
            assert action_calls[0]["due_hours"] == 36
        async with async_session_factory() as session:
            await session.execute(delete(Deal).where(Deal.id == deal_id))
            await session.commit()
        return len(action_calls)

    assert client.portal is not None
    assert client.portal.call(execute) == expected


def test_automatic_action_failure_is_audited_without_raising(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def execute() -> int:
        now = datetime.now(UTC)
        deal = Deal(
            name=f"Automatic action failure {uuid4()}",
            value=Decimal("50000.00"),
            stage="Proposal",
            owner_name="Action Owner",
            stage_entered_at=now - timedelta(days=30),
            last_activity_at=now - timedelta(days=20),
            next_follow_up_at=None,
            status="active",
        )
        async with async_session_factory() as session:
            settings = await session.scalar(select(MonitoringSettings).limit(1))
            assert settings is not None
            settings.automatic_rca_enabled = True
            settings.automatic_rca_min_risk_score = 80
            settings.automatic_safe_actions_enabled = True
            session.add(deal)
            await session.flush()
            incident = BottleneckIncident(
                deal_id=deal.id,
                incident_type="STALLED_DEAL",
                title="Automatic action failure",
                severity="high",
                risk_score=90,
                evidence={},
                status="open",
            )
            session.add(incident)
            await session.flush()
            analysis = AgentAnalysis(
                incident_id=incident.id,
                model_name="test",
                trigger="AUTOMATIC",
                input_fingerprint=str(uuid4()),
                action_type="CREATE_FOLLOW_UP",
                confidence=0.9,
                approval_required=False,
                status="COMPLETED",
            )
            run = MonitoringRun(
                started_at=now,
                completed_at=now,
                deals_scanned=1,
                incidents_created=1,
                incidents_updated=0,
                errors_encountered=0,
                status="COMPLETED",
            )
            session.add_all([analysis, run])
            await session.commit()
            incident_id = incident.id
            deal_id = deal.id
            run_id = run.id

        async def fake_analyze(*args, **kwargs):
            return analysis

        async def fail_action(*args, **kwargs):
            raise monitoring_module.ActionExecutionError("CRM unavailable", status_code=502)

        monkeypatch.setattr(monitoring_module, "analyze_incident", fake_analyze)
        monkeypatch.setattr(monitoring_module, "create_follow_up_task", fail_action)
        service = ProactiveMonitoringService(enabled=True, interval_seconds=60)
        result = DetectionScanResult([], 1, 1, 0, [], (incident_id,))
        await service._run_automatic_rca(result, settings, run_id)
        async with async_session_factory() as session:
            failures = await session.scalar(
                select(func.count(AgentAuditEvent.id)).where(
                    AgentAuditEvent.incident_id == incident_id,
                    AgentAuditEvent.event_type == "AUTOMATIC_ACTION_FAILED",
                    AgentAuditEvent.status == "FAILED",
                )
            )
            await session.execute(delete(Deal).where(Deal.id == deal_id))
            await session.commit()
            return failures or 0

    assert client.portal is not None
    assert client.portal.call(execute) == 1