import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import async_session_factory, engine
from app.main import app
from app.models import Deal


def run(coroutine):
    return asyncio.run(coroutine)


async def persist_deal() -> None:
    deal = Deal(
        name="Test Enterprise Deal",
        value=Decimal("125000.00"),
        stage="Discovery",
        owner_name="Test Owner",
        stage_entered_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        next_follow_up_at=None,
        status="active",
    )
    async with async_session_factory() as session:
        session.add(deal)
        await session.commit()
        deal_id = deal.id

    async with async_session_factory() as session:
        persisted = await session.get(Deal, deal_id)
        assert persisted is not None
        assert persisted.name == "Test Enterprise Deal"
        assert persisted.value == Decimal("125000.00")
        assert persisted.next_follow_up_at is None
        await session.execute(delete(Deal).where(Deal.id == deal_id))
        await session.commit()
    await engine.dispose()


def test_deal_creation_and_persistence() -> None:
    run(persist_deal())


def login(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_authenticated_deal_listing() -> None:
    with TestClient(app) as client:
        response = client.get("/api/deals", headers=login(client))

        assert response.status_code == 200
        assert len(response.json()) >= 5
        assert client.get("/api/deals").status_code == 401


def test_deal_response_structure() -> None:
    expected_fields = {
        "id",
        "zoho_record_id",
        "source",
        "zoho_modified_at",
        "last_synced_at",
        "name",
        "value",
        "stage",
        "owner_name",
        "stage_entered_at",
        "last_activity_at",
        "next_follow_up_at",
        "status",
        "created_at",
    }

    with TestClient(app) as client:
        response = client.get("/api/deals", headers=login(client))

        assert response.status_code == 200
        assert expected_fields == set(response.json()[0])
        assert any(deal["next_follow_up_at"] is None for deal in response.json())
        assert all(deal["value"] for deal in response.json())