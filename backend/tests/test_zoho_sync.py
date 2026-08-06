import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.database import async_session_factory, engine
from app.detection import DetectionScanResult
from app.main import app
from app.models import AgentAuditEvent, Deal
from app.zoho import ZohoDeal, ZohoOAuthError
import app.zoho_sync as sync_service


def zoho_deal(
    record_id: str,
    *,
    name: str | None = "Zoho Expansion",
    stage: str = "Proposal",
    amount: Decimal = Decimal("75000.00"),
    modified_at: datetime | None = None,
) -> ZohoDeal:
    timestamp = modified_at or datetime(2026, 8, 6, 10, tzinfo=UTC)
    return ZohoDeal(
        zoho_record_id=record_id,
        deal_name=name,
        stage=stage,
        amount=amount,
        owner="Zoho Owner",
        closing_date="2026-09-30",
        created_time=datetime(2026, 8, 1, 9, tzinfo=UTC),
        modified_time=timestamp,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())


@pytest.fixture(scope="module")
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(autouse=True)
def isolate_sync_records(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def clean() -> None:
        async with async_session_factory() as session:
            await session.execute(delete(Deal).where(Deal.source == "zoho"))
            await session.execute(
                delete(AgentAuditEvent).where(
                    AgentAuditEvent.event_type.like("ZOHO_DEAL_SYNC_%")
                )
            )
            await session.commit()

    async def no_incidents(session: object, *, deal_ids: set[object]) -> DetectionScanResult:
        return DetectionScanResult([], len(deal_ids), 0, 0, [])

    assert client.portal is not None
    client.portal.call(clean)
    monkeypatch.setattr(sync_service, "run_stalled_deal_scan", no_incidents)
    yield
    client.portal.call(clean)


def run_sync(client: TestClient, deals: list[ZohoDeal]) -> sync_service.ZohoDealSyncResult:
    async def execute() -> sync_service.ZohoDealSyncResult:
        async def fetch(session: object, *, client: object = None) -> list[ZohoDeal]:
            return deals

        original = sync_service.fetch_deals
        sync_service.fetch_deals = fetch
        try:
            async with async_session_factory() as session:
                return await sync_service.synchronize_zoho_deals(session)
        finally:
            sync_service.fetch_deals = original

    assert client.portal is not None
    return client.portal.call(execute)


def get_zoho_deals(client: TestClient) -> list[Deal]:
    async def load() -> list[Deal]:
        async with async_session_factory() as session:
            return list(await session.scalars(select(Deal).where(Deal.source == "zoho")))

    assert client.portal is not None
    return client.portal.call(load)


def test_new_zoho_deal_creates_local_record(client: TestClient) -> None:
    result = run_sync(client, [zoho_deal("zoho-new")])
    deals = get_zoho_deals(client)
    assert (result.fetched, result.created, result.failed) == (1, 1, 0)
    assert len(deals) == 1
    assert deals[0].zoho_record_id == "zoho-new"
    assert deals[0].source == "zoho"
    assert deals[0].name == "Zoho Expansion"
    assert deals[0].value == Decimal("75000.00")
    assert deals[0].last_synced_at is not None


def test_existing_zoho_deal_updates_correctly(client: TestClient) -> None:
    original = zoho_deal("zoho-update")
    run_sync(client, [original])
    changed = zoho_deal(
        "zoho-update",
        name="Updated Zoho Expansion",
        stage="Negotiation",
        amount=Decimal("91000.00"),
        modified_at=original.modified_time + timedelta(hours=1),
    )
    result = run_sync(client, [changed])
    deal = get_zoho_deals(client)[0]
    assert (result.created, result.updated) == (0, 1)
    assert (deal.name, deal.stage, deal.value) == (
        "Updated Zoho Expansion",
        "Negotiation",
        Decimal("91000.00"),
    )
    assert deal.zoho_modified_at == changed.modified_time


def test_repeated_sync_creates_no_duplicates_and_skips_unchanged(
    client: TestClient,
) -> None:
    provider_deal = zoho_deal("zoho-repeat")
    first = run_sync(client, [provider_deal])
    first_synced_at = get_zoho_deals(client)[0].last_synced_at
    second = run_sync(client, [provider_deal])
    second_synced_at = get_zoho_deals(client)[0].last_synced_at
    assert first.created == 1
    assert (second.created, second.updated, second.unchanged) == (0, 0, 1)
    assert len(get_zoho_deals(client)) == 1
    assert second_synced_at == first_synced_at


def test_local_deals_remain_untouched(client: TestClient) -> None:
    async def local_snapshot() -> tuple[int, dict[object, tuple[str, Decimal]]]:
        async with async_session_factory() as session:
            local_deals = list(await session.scalars(select(Deal).where(Deal.source == "local")))
            return len(local_deals), {deal.id: (deal.name, deal.value) for deal in local_deals}

    assert client.portal is not None
    before = client.portal.call(local_snapshot)
    run_sync(client, [zoho_deal("zoho-local-proof")])
    after = client.portal.call(local_snapshot)
    assert before == after


def test_malformed_record_does_not_stop_other_records(client: TestClient) -> None:
    result = run_sync(
        client,
        [zoho_deal("zoho-malformed", name=None), zoho_deal("zoho-valid")],
    )
    assert (result.fetched, result.created, result.failed) == (2, 1, 1)
    assert [deal.zoho_record_id for deal in get_zoho_deals(client)] == ["zoho-valid"]
    assert result.errors == [
        {
            "zoho_record_id": "zoho-malformed",
            "error": "Deal record could not be synchronized",
        }
    ]


def test_detection_runs_only_for_synchronized_deals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_ids: set[object] = set()

    async def capture(session: object, *, deal_ids: set[object]) -> DetectionScanResult:
        captured_ids.update(deal_ids)
        return DetectionScanResult([], len(deal_ids), 0, 0, [])

    monkeypatch.setattr(sync_service, "run_stalled_deal_scan", capture)
    run_sync(client, [zoho_deal("zoho-detect-a"), zoho_deal("zoho-detect-b")])
    stored_ids = {deal.id for deal in get_zoho_deals(client)}
    assert captured_ids == stored_ids
    assert len(captured_ids) == 2


def test_sync_endpoint_requires_administrator(client: TestClient) -> None:
    assert client.post("/api/integrations/zoho/sync/deals").status_code == 401

    async def create_non_admin() -> None:
        from app.models import User
        from app.security import hash_password

        async with async_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == "sync-reader@example.com"))
            if user is None:
                session.add(
                    User(
                        email="sync-reader@example.com",
                        password_hash=hash_password("SyncReader@2026"),
                        is_admin=False,
                        is_active=True,
                    )
                )
                await session.commit()

    assert client.portal is not None
    client.portal.call(create_non_admin)
    login = client.post(
        "/auth/login",
        json={"email": "sync-reader@example.com", "password": "SyncReader@2026"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/integrations/zoho/sync/deals", headers=headers).status_code == 403


def test_sync_endpoint_returns_safe_statistics(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(session: object, *, client: object = None) -> list[ZohoDeal]:
        return [zoho_deal("zoho-api", name=None), zoho_deal("zoho-secret-safe")]

    monkeypatch.setattr(sync_service, "fetch_deals", fetch)
    response = client.post("/api/integrations/zoho/sync/deals", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["fetched"] == 2
    assert response.json()["created"] == 1
    assert response.json()["failed"] == 1
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text
    assert "client_secret" not in response.text


def test_sync_audit_events_are_recorded(client: TestClient) -> None:
    run_sync(client, [zoho_deal("zoho-audit")])

    async def audit_types() -> list[str]:
        async with async_session_factory() as session:
            return list(
                await session.scalars(
                    select(AgentAuditEvent.event_type)
                    .where(AgentAuditEvent.event_type.like("ZOHO_DEAL_SYNC_%"))
                    .order_by(AgentAuditEvent.created_at)
                )
            )

    assert client.portal is not None
    assert client.portal.call(audit_types) == [
        "ZOHO_DEAL_SYNC_STARTED",
        "ZOHO_DEAL_SYNC_COMPLETED",
    ]


def test_provider_failure_is_redacted_and_audited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(session: object, *, client: object = None) -> list[ZohoDeal]:
        raise ZohoOAuthError("Zoho CRM request failed", status_code=502)

    monkeypatch.setattr(sync_service, "fetch_deals", fail)

    async def execute() -> None:
        async with async_session_factory() as session:
            await sync_service.synchronize_zoho_deals(session)

    assert client.portal is not None
    with pytest.raises(ZohoOAuthError):
        client.portal.call(execute)

    async def completion_details() -> tuple[str, dict[str, object]]:
        async with async_session_factory() as session:
            event = await session.scalar(
                select(AgentAuditEvent)
                .where(AgentAuditEvent.event_type == "ZOHO_DEAL_SYNC_COMPLETED")
                .order_by(AgentAuditEvent.created_at.desc())
            )
            assert event is not None
            return event.status, event.details

    status, details = client.portal.call(completion_details)
    assert status == "FAILED"
    assert details["error"] == "Zoho deal fetch failed"
    assert "token" not in str(details).casefold()