import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, ZohoConnection, ZohoOAuthState


class ZohoOAuthError(Exception):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ZohoDeal:
    zoho_record_id: str
    deal_name: str | None
    stage: str | None
    amount: Decimal | None
    owner: str | None
    closing_date: str | None
    created_time: datetime | None
    modified_time: datetime | None


ZOHO_DEAL_FIELDS = (
    "id",
    "Deal_Name",
    "Stage",
    "Amount",
    "Owner",
    "Closing_Date",
    "Created_Time",
    "Modified_Time",
    "$approval_state",
)


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _cipher() -> Fernet:
    secret = get_settings().jwt_secret.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def _validated_api_domain(value: object) -> str:
    if not isinstance(value, str):
        raise ZohoOAuthError("Zoho token response was incomplete", status_code=502)
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or parsed.path not in {"", "/"} or not (
        hostname == "zohoapis.in" or hostname.endswith(".zohoapis.in")
    ):
        raise ZohoOAuthError("Zoho token response was invalid", status_code=502)
    return f"https://{parsed.netloc}".rstrip("/")


def _validated_accounts_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "accounts.zoho.in"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ZohoOAuthError("Zoho OAuth configuration is invalid", status_code=503)
    return "https://accounts.zoho.in"


async def create_authorization_url(session: AsyncSession, admin: User) -> str:
    settings = get_settings()
    if not settings.zoho_client_id or not settings.zoho_client_secret:
        raise ZohoOAuthError("Zoho OAuth is not configured", status_code=503)
    state = secrets.token_urlsafe(32)
    session.add(
        ZohoOAuthState(
            state_hash=_state_hash(state),
            created_by=admin.id,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await session.commit()
    query = urlencode(
        {
            "scope": settings.zoho_scopes,
            "client_id": settings.zoho_client_id,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "redirect_uri": settings.zoho_redirect_uri,
            "state": state,
        }
    )
    return f"{_validated_accounts_url(settings.zoho_accounts_url)}/oauth/v2/auth?{query}"


async def complete_authorization(
    session: AsyncSession,
    *,
    state: str,
    code: str,
    client: httpx.AsyncClient | None = None,
) -> ZohoConnection:
    now = datetime.now(UTC)
    oauth_state = await session.scalar(
        select(ZohoOAuthState)
        .where(ZohoOAuthState.state_hash == _state_hash(state))
        .with_for_update()
    )
    if oauth_state is None or oauth_state.used_at is not None or oauth_state.expires_at <= now:
        raise ZohoOAuthError("Invalid or expired OAuth state", status_code=400)
    oauth_state.used_at = now
    await session.commit()

    settings = get_settings()
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15)
    try:
        response = await http_client.post(
            f"{_validated_accounts_url(settings.zoho_accounts_url)}/oauth/v2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.zoho_client_id,
                "client_secret": settings.zoho_client_secret,
                "redirect_uri": settings.zoho_redirect_uri,
                "code": code,
            },
        )
    except httpx.HTTPError as error:
        raise ZohoOAuthError("Zoho token exchange failed", status_code=502) from error
    finally:
        if owns_client:
            await http_client.aclose()
    if response.status_code != 200:
        raise ZohoOAuthError("Zoho token exchange failed", status_code=502)
    payload = response.json()
    try:
        access_token = str(payload["access_token"])
        refresh_token = str(payload["refresh_token"])
        api_domain = _validated_api_domain(payload["api_domain"])
        expires_in = int(payload["expires_in"])
    except (KeyError, TypeError, ValueError) as error:
        raise ZohoOAuthError("Zoho token response was incomplete", status_code=502) from error

    connection = await session.scalar(select(ZohoConnection).limit(1).with_for_update())
    encrypted_access = _cipher().encrypt(access_token.encode("utf-8")).decode("ascii")
    encrypted_refresh = _cipher().encrypt(refresh_token.encode("utf-8")).decode("ascii")
    if connection is None:
        connection = ZohoConnection(
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            api_domain=api_domain,
            authorized_scopes=settings.zoho_scopes,
            access_token_expires_at=now + timedelta(seconds=expires_in),
            connected_by=oauth_state.created_by,
            connected_at=now,
        )
        session.add(connection)
    else:
        connection.access_token_encrypted = encrypted_access
        connection.refresh_token_encrypted = encrypted_refresh
        connection.api_domain = api_domain
        connection.authorized_scopes = settings.zoho_scopes
        connection.access_token_expires_at = now + timedelta(seconds=expires_in)
        connection.connected_by = oauth_state.created_by
        connection.connected_at = now
    await session.commit()
    await session.refresh(connection)
    return connection


async def consume_denied_authorization(session: AsyncSession, *, state: str) -> None:
    now = datetime.now(UTC)
    oauth_state = await session.scalar(
        select(ZohoOAuthState)
        .where(ZohoOAuthState.state_hash == _state_hash(state))
        .with_for_update()
    )
    if oauth_state is None or oauth_state.used_at is not None or oauth_state.expires_at <= now:
        raise ZohoOAuthError("Invalid or expired OAuth state", status_code=400)
    oauth_state.used_at = now
    await session.commit()


async def get_connection(session: AsyncSession) -> ZohoConnection | None:
    return await session.scalar(select(ZohoConnection).limit(1))


def _decrypt_token(encrypted_token: str) -> str:
    try:
        return _cipher().decrypt(encrypted_token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        raise ZohoOAuthError("Stored Zoho credentials are unavailable", status_code=503) from error


async def _refresh_access_token(
    session: AsyncSession,
    connection: ZohoConnection,
    http_client: httpx.AsyncClient,
) -> str:
    settings = get_settings()
    refresh_token = _decrypt_token(connection.refresh_token_encrypted)
    try:
        response = await http_client.post(
            f"{_validated_accounts_url(settings.zoho_accounts_url)}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.zoho_client_id,
                "client_secret": settings.zoho_client_secret,
                "refresh_token": refresh_token,
            },
        )
    except httpx.TimeoutException as error:
        raise ZohoOAuthError("Zoho token refresh timed out", status_code=504) from error
    except httpx.HTTPError as error:
        raise ZohoOAuthError("Zoho token refresh failed", status_code=502) from error
    if response.status_code != 200:
        raise ZohoOAuthError("Zoho token refresh failed", status_code=502)
    try:
        payload = response.json()
        access_token = str(payload["access_token"])
        expires_in = int(payload["expires_in"])
    except (KeyError, TypeError, ValueError) as error:
        raise ZohoOAuthError("Zoho token refresh failed", status_code=502) from error
    if not access_token or expires_in <= 0:
        raise ZohoOAuthError("Zoho token refresh failed", status_code=502)

    api_domain = payload.get("api_domain")
    if api_domain is not None:
        connection.api_domain = _validated_api_domain(api_domain)
    connection.access_token_encrypted = _cipher().encrypt(
        access_token.encode("utf-8")
    ).decode("ascii")
    connection.access_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    await session.commit()
    return access_token


async def _get_access_token(
    session: AsyncSession,
    connection: ZohoConnection,
    http_client: httpx.AsyncClient,
    *,
    force_refresh: bool = False,
) -> str:
    if not force_refresh and connection.access_token_expires_at > datetime.now(UTC) + timedelta(seconds=60):
        return _decrypt_token(connection.access_token_encrypted)
    locked_connection = await session.scalar(
        select(ZohoConnection).where(ZohoConnection.id == connection.id).with_for_update()
    )
    if locked_connection is None:
        raise ZohoOAuthError("Zoho CRM is not connected", status_code=503)
    if not force_refresh and locked_connection.access_token_expires_at > datetime.now(UTC) + timedelta(seconds=60):
        return _decrypt_token(locked_connection.access_token_encrypted)
    return await _refresh_access_token(session, locked_connection, http_client)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _map_deal(record: dict[str, Any]) -> ZohoDeal | None:
    record_id = record.get("id")
    if not isinstance(record_id, str) or not record_id:
        return None
    amount: Decimal | None = None
    raw_amount = record.get("Amount")
    if raw_amount is not None:
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError):
            amount = None
    owner_value = record.get("Owner")
    owner = owner_value.get("name") if isinstance(owner_value, dict) else None
    return ZohoDeal(
        zoho_record_id=record_id,
        deal_name=record.get("Deal_Name") if isinstance(record.get("Deal_Name"), str) else None,
        stage=record.get("Stage") if isinstance(record.get("Stage"), str) else None,
        amount=amount,
        owner=owner if isinstance(owner, str) else None,
        closing_date=(
            record.get("Closing_Date") if isinstance(record.get("Closing_Date"), str) else None
        ),
        created_time=_parse_datetime(record.get("Created_Time")),
        modified_time=_parse_datetime(record.get("Modified_Time")),
    )


async def fetch_deals(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[ZohoDeal]:
    connection = await get_connection(session)
    if connection is None:
        raise ZohoOAuthError("Zoho CRM is not connected", status_code=503)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15)
    try:
        access_token = await _get_access_token(session, connection, http_client)
        records: list[dict[str, Any]] = []
        page = 1
        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {
                "fields": ",".join(ZOHO_DEAL_FIELDS),
                "per_page": 200,
            }
            if page_token is not None:
                params["page_token"] = page_token
            else:
                params["page"] = page
            response = await http_client.get(
                f"{connection.api_domain.rstrip('/')}/crm/v8/Deals",
                params=params,
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            )
            if response.status_code == 401:
                access_token = await _get_access_token(
                    session, connection, http_client, force_refresh=True
                )
                response = await http_client.get(
                    f"{connection.api_domain.rstrip('/')}/crm/v8/Deals",
                    params=params,
                    headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                )
            if response.status_code == 204:
                break
            _raise_for_deal_response(response.status_code)
            try:
                payload = response.json()
                page_records = payload.get("data", [])
                info = payload.get("info", {})
            except (AttributeError, TypeError, ValueError) as error:
                raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502) from error
            if not isinstance(page_records, list) or not isinstance(info, dict):
                raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
            records.extend(record for record in page_records if isinstance(record, dict))
            if not info.get("more_records"):
                break
            next_page_token = info.get("next_page_token")
            if isinstance(next_page_token, str) and next_page_token:
                page_token = next_page_token
            else:
                page += 1
    except httpx.TimeoutException as error:
        raise ZohoOAuthError("Zoho CRM request timed out", status_code=504) from error
    except httpx.HTTPError as error:
        raise ZohoOAuthError("Zoho CRM request failed", status_code=502) from error
    finally:
        if owns_client:
            await http_client.aclose()

    return [mapped for record in records if isinstance(record, dict) and (mapped := _map_deal(record))]


def _raise_for_deal_response(status_code: int) -> None:
    if status_code == 403:
        raise ZohoOAuthError("Zoho CRM Deals read permission is required", status_code=403)
    if status_code == 429:
        raise ZohoOAuthError("Zoho CRM rate limit exceeded", status_code=429)
    if status_code != 200:
        raise ZohoOAuthError("Zoho CRM request failed", status_code=502)


async def test_connection(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    connection = await get_connection(session)
    if connection is None:
        raise ZohoOAuthError("Zoho CRM is not connected", status_code=503)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15)
    try:
        access_token = await _get_access_token(session, connection, http_client)
        response = await http_client.get(
            f"{connection.api_domain.rstrip('/')}/crm/v8/Deals",
            params={"fields": "id", "per_page": 1},
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if response.status_code == 401:
            access_token = await _get_access_token(
                session, connection, http_client, force_refresh=True
            )
            response = await http_client.get(
                f"{connection.api_domain.rstrip('/')}/crm/v8/Deals",
                params={"fields": "id", "per_page": 1},
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            )
    except httpx.TimeoutException as error:
        raise ZohoOAuthError("Zoho CRM connection test timed out", status_code=504) from error
    except httpx.HTTPError as error:
        raise ZohoOAuthError("Zoho CRM connection test failed", status_code=502) from error
    finally:
        if owns_client:
            await http_client.aclose()
    if response.status_code == 403:
        raise ZohoOAuthError("Zoho CRM Deals read permission is required", status_code=403)
    if response.status_code == 429:
        raise ZohoOAuthError("Zoho CRM rate limit exceeded", status_code=429)
    if response.status_code not in {200, 204}:
        raise ZohoOAuthError("Zoho CRM connection test failed", status_code=502)


async def disconnect(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    connection = await get_connection(session)
    if connection is None:
        return False
    refresh_token = _decrypt_token(connection.refresh_token_encrypted)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15)
    revoked = False
    try:
        response = await http_client.post(
            f"{_validated_accounts_url(get_settings().zoho_accounts_url)}/oauth/v2/token/revoke",
            params={"token": refresh_token},
        )
        revoked = response.status_code == 200
    except httpx.HTTPError:
        revoked = False
    finally:
        if owns_client:
            await http_client.aclose()
    await session.execute(delete(ZohoConnection).where(ZohoConnection.id == connection.id))
    await session.commit()
    return revoked