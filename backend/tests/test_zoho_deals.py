import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import async_session_factory, engine
from app.main import app
from app.models import User, ZohoConnection
import app.zoho as zoho_service


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeZohoClient:
    get_responses: list[FakeResponse] = []
    post_response = FakeResponse(
        200,
        {
            "access_token": "refreshed-access-secret",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        },
    )
    get_calls: list[dict[str, object]] = []
    post_calls: list[dict[str, object]] = []

    def __init__(self, **_: object) -> None:
        pass

    async def get(
        self, url: str, *, params: dict[str, str | int], headers: dict[str, str]
    ) -> FakeResponse:
        type(self).get_calls.append({"url": url, "params": params, "headers": headers})
        return type(self).get_responses.pop(0)

    async def post(self, url: str, *, data: dict[str, str]) -> FakeResponse:
        type(self).post_calls.append({"url": url, "data": data})
        return type(self).post_response

    async def aclose(self) -> None:
        pass


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client

        async def cleanup() -> None:
            async with async_session_factory() as session:
                await session.execute(delete(ZohoConnection))
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


@pytest.fixture(scope="module")
def non_admin_headers(client: TestClient) -> dict[str, str]:
    async def create_user() -> None:
        from app.security import hash_password

        async with async_session_factory() as session:
            existing = await session.scalar(
                select(User).where(User.email == "zoho-reader@example.com")
            )
            if existing is None:
                session.add(
                    User(
                        email="zoho-reader@example.com",
                        password_hash=hash_password("ReaderPassword@2026"),
                        is_admin=False,
                        is_active=True,
                    )
                )
                await session.commit()

    assert client.portal is not None
    client.portal.call(create_user)
    response = client.post(
        "/auth/login",
        json={"email": "zoho-reader@example.com", "password": "ReaderPassword@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(autouse=True)
def fake_zoho(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeZohoClient.get_responses = []
    FakeZohoClient.get_calls = []
    FakeZohoClient.post_calls = []
    FakeZohoClient.post_response = FakeResponse(
        200,
        {
            "access_token": "refreshed-access-secret",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        },
    )
    monkeypatch.setattr(zoho_service.httpx, "AsyncClient", FakeZohoClient)


def seed_connection(client: TestClient, *, expired: bool = False) -> None:
    async def seed() -> None:
        async with async_session_factory() as session:
            await session.execute(delete(ZohoConnection))
            admin_id = await session.scalar(
                select(User.id).where(User.email == "admin@velocitycrm.com")
            )
            assert isinstance(admin_id, UUID)
            session.add(
                ZohoConnection(
                    access_token_encrypted=zoho_service._cipher()
                    .encrypt(b"stored-access-secret")
                    .decode("ascii"),
                    refresh_token_encrypted=zoho_service._cipher()
                    .encrypt(b"stored-refresh-secret")
                    .decode("ascii"),
                    api_domain="https://www.zohoapis.in",
                    authorized_scopes="ZohoCRM.modules.deals.READ",
                    access_token_expires_at=datetime.now(UTC)
                    + (timedelta(seconds=-1) if expired else timedelta(hours=1)),
                    connected_by=admin_id,
                )
            )
            await session.commit()

    assert client.portal is not None
    client.portal.call(seed)


def test_successful_deal_retrieval_and_field_mapping(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    seed_connection(client)
    FakeZohoClient.get_responses = [
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "5725767000000524001",
                        "Deal_Name": "Northwind Renewal",
                        "Stage": "Proposal/Price Quote",
                        "Amount": 12500.5,
                        "Owner": {"name": "Anita Rao", "id": "private-owner-id"},
                        "Closing_Date": "2026-09-30",
                        "Created_Time": "2026-08-01T10:15:00+05:30",
                        "Modified_Time": "2026-08-05T12:45:00+05:30",
                        "Description": "must not be returned",
                    }
                ]
            },
        )
    ]
    response = client.get("/api/integrations/zoho/deals", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == [
        {
            "zoho_record_id": "5725767000000524001",
            "deal_name": "Northwind Renewal",
            "stage": "Proposal/Price Quote",
            "amount": "12500.5",
            "owner": "Anita Rao",
            "closing_date": "2026-09-30",
            "created_time": "2026-08-01T10:15:00+05:30",
            "modified_time": "2026-08-05T12:45:00+05:30",
        }
    ]
    assert FakeZohoClient.get_calls[0]["url"] == "https://www.zohoapis.in/crm/v8/Deals"
    assert FakeZohoClient.get_calls[0]["params"] == {
        "fields": "id,Deal_Name,Stage,Amount,Owner,Closing_Date,Created_Time,Modified_Time,$approval_state",
        "per_page": 200,
        "page": 1,
    }


def test_page_and_page_token_pagination(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    seed_connection(client)
    FakeZohoClient.get_responses = [
        FakeResponse(
            200,
            {
                "data": [{"id": "page-1", "Deal_Name": "First"}],
                "info": {"more_records": True},
            },
        ),
        FakeResponse(
            200,
            {
                "data": [{"id": "page-2", "Deal_Name": "Second"}],
                "info": {"more_records": True, "next_page_token": "safe-page-token"},
            },
        ),
        FakeResponse(
            200,
            {
                "data": [{"id": "page-3", "Deal_Name": "Third"}],
                "info": {"more_records": False},
            },
        ),
    ]
    response = client.get("/api/integrations/zoho/deals", headers=admin_headers)
    assert response.status_code == 200
    assert [deal["zoho_record_id"] for deal in response.json()] == [
        "page-1",
        "page-2",
        "page-3",
    ]
    assert FakeZohoClient.get_calls[0]["params"]["page"] == 1
    assert FakeZohoClient.get_calls[1]["params"]["page"] == 2
    assert FakeZohoClient.get_calls[2]["params"]["page_token"] == "safe-page-token"
    assert "page" not in FakeZohoClient.get_calls[2]["params"]


def test_empty_deals_module(client: TestClient, admin_headers: dict[str, str]) -> None:
    seed_connection(client)
    FakeZohoClient.get_responses = [FakeResponse(204)]
    response = client.get("/api/integrations/zoho/deals", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_expired_access_token_is_refreshed(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    seed_connection(client, expired=True)
    FakeZohoClient.get_responses = [FakeResponse(200, {"data": []})]
    response = client.get("/api/integrations/zoho/deals", headers=admin_headers)
    assert response.status_code == 200
    assert len(FakeZohoClient.post_calls) == 1
    assert FakeZohoClient.post_calls[0]["url"] == "https://accounts.zoho.in/oauth/v2/token"
    assert FakeZohoClient.post_calls[0]["data"]["grant_type"] == "refresh_token"
    assert FakeZohoClient.get_calls[0]["headers"] == {
        "Authorization": "Zoho-oauthtoken refreshed-access-secret"
    }

    async def verify_refresh() -> None:
        async with async_session_factory() as session:
            connection = await session.scalar(select(ZohoConnection).limit(1))
            assert connection is not None
            assert connection.access_token_encrypted != "refreshed-access-secret"
            assert "refreshed-access-secret" not in connection.access_token_encrypted

    assert client.portal is not None
    client.portal.call(verify_refresh)


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "detail"),
    [
        (403, 403, "Zoho CRM Deals read permission is required"),
        (429, 429, "Zoho CRM rate limit exceeded"),
        (500, 502, "Zoho CRM request failed"),
    ],
)
def test_provider_failures_are_safe(
    client: TestClient,
    admin_headers: dict[str, str],
    provider_status: int,
    expected_status: int,
    detail: str,
) -> None:
    seed_connection(client)
    FakeZohoClient.get_responses = [
        FakeResponse(provider_status, {"access_token": "provider-must-not-leak"})
    ]
    response = client.get("/api/integrations/zoho/deals", headers=admin_headers)
    assert response.status_code == expected_status
    assert response.json() == {"detail": detail}
    assert "provider-must-not-leak" not in response.text
    assert "stored-access-secret" not in response.text
    assert "stored-refresh-secret" not in response.text


def test_administrator_authorization(
    client: TestClient,
    non_admin_headers: dict[str, str],
) -> None:
    assert client.get("/api/integrations/zoho/deals").status_code == 401
    response = client.get("/api/integrations/zoho/deals", headers=non_admin_headers)
    assert response.status_code == 403
    assert FakeZohoClient.get_calls == []