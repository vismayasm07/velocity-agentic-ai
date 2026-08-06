import asyncio
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import async_session_factory, engine
from app.main import app
from app.models import ZohoConnection, ZohoOAuthState
import app.zoho as zoho_service


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class FakeZohoClient:
    response = FakeResponse(
        200,
        {
            "access_token": "access-secret-value",
            "refresh_token": "refresh-secret-value",
            "api_domain": "https://www.zohoapis.in",
            "expires_in": 3600,
        },
    )
    last_url = ""
    last_data: dict[str, str] = {}

    def __init__(self, **_: object) -> None:
        pass

    async def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> FakeResponse:
        type(self).last_url = url
        type(self).last_data = data or params or {}
        return type(self).response

    async def get(self, _: str, **__: object) -> FakeResponse:
        return type(self).response

    async def aclose(self) -> None:
        pass


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client

        async def cleanup() -> None:
            async with async_session_factory() as session:
                await session.execute(delete(ZohoConnection))
                await session.execute(delete(ZohoOAuthState))
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


@pytest.fixture(autouse=True)
def fake_zoho(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeZohoClient.response = FakeResponse(
        200,
        {
            "access_token": "access-secret-value",
            "refresh_token": "refresh-secret-value",
            "api_domain": "https://www.zohoapis.in",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(zoho_service.httpx, "AsyncClient", FakeZohoClient)


def authorize(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    response = client.get(
        "/api/integrations/zoho/authorize",
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers["location"]
    return location, parse_qs(urlparse(location).query)["state"][0]


def test_authorization_url_and_hashed_state(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    location, state = authorize(client, admin_headers)
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.zoho.in/oauth/v2/auth"
    assert query["scope"] == ["ZohoCRM.modules.deals.READ"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/integrations/zoho/callback"]

    async def verify_state() -> None:
        async with async_session_factory() as session:
            stored = await session.scalar(
                select(ZohoOAuthState).where(
                    ZohoOAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest()
                )
            )
            assert stored is not None
            assert stored.state_hash != state

    assert client.portal is not None
    client.portal.call(verify_state)


def test_authorization_rejects_non_india_accounts_host(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zoho_service.get_settings(), "zoho_accounts_url", "https://attacker.example")

    response = client.post("/api/integrations/zoho/authorize", headers=admin_headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "Zoho OAuth configuration is invalid"}


def test_authenticated_post_returns_authorization_url(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert client.post("/api/integrations/zoho/authorize").status_code == 401
    response = client.post("/api/integrations/zoho/authorize", headers=admin_headers)
    assert response.status_code == 200
    location = response.json()["authorization_url"]
    assert location.startswith("https://accounts.zoho.in/oauth/v2/auth?")
    assert "access_token" not in response.text


def test_valid_callback_encrypts_tokens_and_redacts_response(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _, state = authorize(client, admin_headers)
    response = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "valid-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        "http://localhost:3000/settings/integrations/zoho?zoho=connected"
    )
    assert "secret" not in response.text
    assert FakeZohoClient.last_url == "https://accounts.zoho.in/oauth/v2/token"
    assert FakeZohoClient.last_data["code"] == "valid-code"

    async def verify_connection() -> None:
        async with async_session_factory() as session:
            connection = await session.scalar(select(ZohoConnection).limit(1))
            assert connection is not None
            assert connection.access_token_encrypted != "access-secret-value"
            assert connection.refresh_token_encrypted != "refresh-secret-value"
            assert "access-secret-value" not in connection.access_token_encrypted
            assert "refresh-secret-value" not in connection.refresh_token_encrypted

    assert client.portal is not None
    client.portal.call(verify_connection)

    replay = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "valid-code"},
        follow_redirects=False,
    )
    assert replay.status_code == 303
    assert "zoho=error" in replay.headers["location"]


def test_invalid_state_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/integrations/zoho/callback",
        params={"state": "invalid-state-value", "code": "code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Invalid+or+expired+OAuth+state" in response.headers["location"]


def test_expired_state_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _, state = authorize(client, admin_headers)

    async def expire_state() -> None:
        async with async_session_factory() as session:
            stored = await session.scalar(
                select(ZohoOAuthState).where(
                    ZohoOAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest()
                )
            )
            assert stored is not None
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    assert client.portal is not None
    client.portal.call(expire_state)
    response = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Invalid+or+expired+OAuth+state" in response.headers["location"]


def test_token_exchange_failure_is_redacted_and_consumes_state(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _, state = authorize(client, admin_headers)
    FakeZohoClient.response = FakeResponse(
        400,
        {"error": "invalid_code", "access_token": "must-not-leak"},
    )
    response = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "bad-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Zoho+token+exchange+failed" in response.headers["location"]
    assert "must-not-leak" not in response.text
    replay = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "bad-code"},
        follow_redirects=False,
    )
    assert replay.status_code == 303


def test_denied_callback_consumes_state(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _, state = authorize(client, admin_headers)
    denied = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert denied.status_code == 303
    assert "Authorization+was+not+approved" in denied.headers["location"]
    replay = client.get(
        "/api/integrations/zoho/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "Invalid+or+expired+OAuth+state" in replay.headers["location"]


def test_status_is_admin_protected_and_secret_free(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert client.get("/api/integrations/zoho/status").status_code == 401
    response = client.get("/api/integrations/zoho/status", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["adapter"] == "local"
    assert payload["api_domain"] == "https://www.zohoapis.in"
    assert payload["authorized_scopes"] == "ZohoCRM.modules.deals.READ"
    assert payload["connected_at"] is not None
    assert isinstance(payload["synchronized_deals"], int)
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text
    serialized = response.text.lower()
    assert "token" not in serialized
    assert "client_secret" not in serialized


def test_connection_test_and_disconnect_are_admin_protected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert client.post("/api/integrations/zoho/test").status_code == 401
    tested = client.post("/api/integrations/zoho/test", headers=admin_headers)
    assert tested.status_code == 200
    assert tested.json() == {
        "healthy": True,
        "message": "Zoho CRM connection is healthy",
    }
    assert client.delete("/api/integrations/zoho").status_code == 401
    disconnected = client.delete("/api/integrations/zoho", headers=admin_headers)
    assert disconnected.status_code == 200
    assert disconnected.json()["disconnected"] is True
    status_response = client.get("/api/integrations/zoho/status", headers=admin_headers)
    payload = status_response.json()
    assert payload["connected"] is False
    assert payload["adapter"] == "local"
    assert payload["api_domain"] is None
    assert payload["authorized_scopes"] is None
    assert payload["connected_at"] is None