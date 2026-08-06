from datetime import UTC, date, datetime, time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import (
    CRMActionResult,
    CRMDealSnapshot,
    CRMFollowUpRequest,
    CRMReassignmentRequest,
)
from app.models import Deal
from app.zoho import ZohoOAuthError, _get_access_token, get_connection


class ZohoCRMAdapter:
    def __init__(self, session: AsyncSession, *, client: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.client = client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        required_scope: str,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        connection = await get_connection(self.session)
        if connection is None:
            raise ZohoOAuthError("Zoho CRM is not connected", status_code=503)
        granted = {scope.strip().casefold() for scope in connection.authorized_scopes.split(",")}
        if required_scope.casefold() not in granted:
            raise ZohoOAuthError("Reconnect Zoho CRM to grant the required permission", status_code=403)
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            access_token = await _get_access_token(self.session, connection, client)
            response = await client.request(
                method,
                f"{connection.api_domain.rstrip('/')}/crm/v8/{path.lstrip('/')}",
                params=params,
                json=json,
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            )
            if response.status_code == 401:
                access_token = await _get_access_token(
                    self.session, connection, client, force_refresh=True
                )
                response = await client.request(
                    method,
                    f"{connection.api_domain.rstrip('/')}/crm/v8/{path.lstrip('/')}",
                    params=params,
                    json=json,
                    headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                )
        except httpx.TimeoutException as error:
            raise ZohoOAuthError("Zoho CRM request timed out", status_code=504) from error
        except httpx.HTTPError as error:
            raise ZohoOAuthError("Zoho CRM request failed", status_code=502) from error
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code == 429:
            raise ZohoOAuthError("Zoho CRM rate limit exceeded", status_code=429)
        if response.status_code in {401, 403}:
            raise ZohoOAuthError("Zoho CRM permission is required", status_code=403)
        if response.status_code not in {200, 201, 202, 204}:
            raise ZohoOAuthError("Zoho CRM request failed", status_code=502)
        return response

    async def _zoho_deal(self, deal_id: object) -> Deal:
        deal = await self.session.scalar(select(Deal).where(Deal.id == deal_id))
        if deal is None or deal.source != "zoho" or not deal.zoho_record_id:
            raise ZohoOAuthError("This action requires a synchronized Zoho deal", status_code=409)
        return deal

    async def _owner_id(self, owner_name: str) -> str:
        matches: list[dict[str, object]] = []
        for page in range(1, 11):
            response = await self._request(
                "GET",
                "users",
                required_scope="ZohoCRM.users.READ",
                params={"type": "ActiveUsers", "per_page": 200, "page": page},
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
            users = payload.get("users", [])
            if not isinstance(users, list):
                raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
            matches.extend(
                user
                for user in users
                if isinstance(user, dict)
                and isinstance(user.get("id"), str)
                and str(user.get("full_name", "")).casefold() == owner_name.casefold()
            )
            info = payload.get("info")
            if not isinstance(info, dict) or not info.get("more_records"):
                break
        if len(matches) != 1:
            raise ZohoOAuthError("The selected Zoho owner could not be resolved", status_code=409)
        return str(matches[0]["id"])

    async def create_follow_up(self, request: CRMFollowUpRequest) -> CRMActionResult:
        deal = await self._zoho_deal(request.deal_id)
        owner_id = await self._owner_id(request.assigned_to)
        response = await self._request(
            "POST",
            "Tasks",
            required_scope="ZohoCRM.modules.tasks.CREATE",
            json={
                "data": [
                    {
                        "Subject": request.title[:255],
                        "Description": request.description[:2000],
                        "Due_Date": request.due_at.date().isoformat(),
                        "What_Id": {"id": deal.zoho_record_id},
                        "$se_module": "Deals",
                        "Owner": {"id": owner_id},
                    }
                ],
                "trigger": [],
            },
        )
        return CRMActionResult(status="CREATED", external_task_id=_created_record_id(response))

    async def reassign_deal(self, request: CRMReassignmentRequest) -> CRMActionResult:
        deal = await self._zoho_deal(request.deal_id)
        owner_id = await self._owner_id(request.proposed_owner)
        response = await self._request(
            "PUT",
            f"Deals/{deal.zoho_record_id}",
            required_scope="ZohoCRM.modules.deals.UPDATE",
            json={"data": [{"Owner": {"id": owner_id}}], "trigger": []},
        )
        _validate_record_update(response)
        return CRMActionResult(status="REASSIGNED")

    async def get_deal_snapshot(self, deal: Deal) -> CRMDealSnapshot:
        synchronized = await self._zoho_deal(deal.id)
        response = await self._request(
            "GET",
            f"Deals/{synchronized.zoho_record_id}",
            required_scope="ZohoCRM.modules.deals.READ",
            params={"fields": "Stage,Owner,Closing_Date,Modified_Time"},
        )
        payload = response.json()
        records = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
        record: dict[str, Any] = records[0]
        owner = record.get("Owner")
        closing_date = record.get("Closing_Date")
        next_follow_up_at = None
        if isinstance(closing_date, str):
            try:
                next_follow_up_at = datetime.combine(
                    date.fromisoformat(closing_date), time.min, tzinfo=UTC
                )
            except ValueError:
                pass
        modified = record.get("Modified_Time")
        try:
            last_activity_at = datetime.fromisoformat(str(modified).replace("Z", "+00:00"))
        except ValueError:
            last_activity_at = synchronized.last_activity_at
        stage = record.get("Stage") if isinstance(record.get("Stage"), str) else synchronized.stage
        owner_name = (
            owner.get("name")
            if isinstance(owner, dict) and isinstance(owner.get("name"), str)
            else synchronized.owner_name
        )
        status = "closed" if stage.casefold() in {"closed won", "closed lost"} else "active"
        return CRMDealSnapshot(
            deal_id=deal.id,
            stage=stage,
            owner_name=owner_name,
            last_activity_at=last_activity_at,
            next_follow_up_at=next_follow_up_at,
            status=status,
        )


def _created_record_id(response: httpx.Response) -> str:
    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
    details = data[0].get("details")
    if data[0].get("status") != "success" or not isinstance(details, dict):
        raise ZohoOAuthError("Zoho CRM task creation failed", status_code=502)
    record_id = details.get("id")
    if not isinstance(record_id, str) or not record_id:
        raise ZohoOAuthError("Zoho CRM response was invalid", status_code=502)
    return record_id


def _validate_record_update(response: httpx.Response) -> None:
    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if (
        not isinstance(data, list)
        or len(data) != 1
        or not isinstance(data[0], dict)
        or data[0].get("status") != "success"
    ):
        raise ZohoOAuthError("Zoho CRM deal update failed", status_code=502)