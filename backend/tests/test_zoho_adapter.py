import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.actions import CRMFollowUpRequest, CRMReassignmentRequest
from app.models import Deal
from app.zoho import ZohoOAuthError
from app.zoho_adapter import ZohoCRMAdapter


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, deal: Deal) -> None:
        self.deal = deal

    async def scalar(self, _: object) -> object:
        return self.deal


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def zoho_deal() -> Deal:
    now = datetime(2026, 8, 6, 10, tzinfo=UTC)
    return Deal(
        id=uuid4(),
        zoho_record_id="5725767000000524001",
        source="zoho",
        name="Northwind Renewal",
        value=Decimal("12500"),
        stage="Proposal/Price Quote",
        owner_name="Anita Rao",
        stage_entered_at=now,
        last_activity_at=now,
        next_follow_up_at=None,
        status="active",
    )


def patch_connection(monkeypatch: pytest.MonkeyPatch, scopes: str) -> None:
    connection = SimpleNamespace(
        api_domain="https://www.zohoapis.in", authorized_scopes=scopes
    )

    async def get_connection(_: object) -> object:
        return connection

    async def get_access_token(*_: object, **__: object) -> str:
        return "secret-access-token"

    monkeypatch.setattr("app.zoho_adapter.get_connection", get_connection)
    monkeypatch.setattr("app.zoho_adapter._get_access_token", get_access_token)


def test_create_follow_up_uses_related_deal_and_active_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_connection(
        monkeypatch, "ZohoCRM.users.READ,ZohoCRM.modules.tasks.CREATE"
    )
    deal = zoho_deal()
    client = FakeClient(
        [
            FakeResponse({"users": [{"id": "owner-1", "full_name": "Anita Rao"}]}),
            FakeResponse(
                {"data": [{"status": "success", "details": {"id": "task-1"}}]},
                status_code=201,
            ),
        ]
    )
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    result = asyncio.run(
        adapter.create_follow_up(
            CRMFollowUpRequest(
                deal_id=deal.id,
                incident_id=uuid4(),
                title="Follow up on Northwind Renewal",
                description="Confirm next steps.",
                assigned_to="Anita Rao",
                due_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
            )
        )
    )
    assert result.external_task_id == "task-1"
    payload = client.calls[1]["json"]
    assert isinstance(payload, dict)
    assert payload["data"] == [
        {
            "Subject": "Follow up on Northwind Renewal",
            "Description": "Confirm next steps.",
            "Due_Date": "2026-08-07",
            "What_Id": {"id": "5725767000000524001"},
            "$se_module": "Deals",
            "Owner": {"id": "owner-1"},
        }
    ]
    assert "secret-access-token" not in str(payload)


def test_reassignment_updates_only_the_approved_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_connection(
        monkeypatch, "ZohoCRM.users.READ,ZohoCRM.modules.deals.UPDATE"
    )
    deal = zoho_deal()
    client = FakeClient(
        [
            FakeResponse({"users": [{"id": "owner-2", "full_name": "Priya Shah"}]}),
            FakeResponse({"data": [{"status": "success"}]}),
        ]
    )
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    result = asyncio.run(
        adapter.reassign_deal(
            CRMReassignmentRequest(
                deal_id=deal.id,
                incident_id=uuid4(),
                approval_id=uuid4(),
                current_owner="Anita Rao",
                proposed_owner="Priya Shah",
            )
        )
    )
    assert result.status == "REASSIGNED"
    assert client.calls[1]["method"] == "PUT"
    assert str(client.calls[1]["url"]).endswith("/crm/v8/Deals/5725767000000524001")
    assert client.calls[1]["json"] == {
        "data": [{"Owner": {"id": "owner-2"}}],
        "trigger": [],
    }


def test_reassignment_resolves_owner_from_later_user_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_connection(
        monkeypatch, "ZohoCRM.users.READ,ZohoCRM.modules.deals.UPDATE"
    )
    deal = zoho_deal()
    client = FakeClient(
        [
            FakeResponse(
                {
                    "users": [{"id": "owner-1", "full_name": "Anita Rao"}],
                    "info": {"more_records": True},
                }
            ),
            FakeResponse(
                {
                    "users": [{"id": "owner-2", "full_name": "Priya Shah"}],
                    "info": {"more_records": False},
                }
            ),
            FakeResponse({"data": [{"status": "success"}]}),
        ]
    )
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    result = asyncio.run(
        adapter.reassign_deal(
            CRMReassignmentRequest(
                deal_id=deal.id,
                incident_id=uuid4(),
                approval_id=uuid4(),
                current_owner="Anita Rao",
                proposed_owner="Priya Shah",
            )
        )
    )
    assert result.status == "REASSIGNED"
    assert client.calls[0]["params"] == {
        "type": "ActiveUsers",
        "per_page": 200,
        "page": 1,
    }
    assert client.calls[1]["params"] == {
        "type": "ActiveUsers",
        "per_page": 200,
        "page": 2,
    }


def test_reassignment_rejects_record_level_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_connection(
        monkeypatch, "ZohoCRM.users.READ,ZohoCRM.modules.deals.UPDATE"
    )
    deal = zoho_deal()
    client = FakeClient(
        [
            FakeResponse({"users": [{"id": "owner-2", "full_name": "Priya Shah"}]}),
            FakeResponse(
                {
                    "data": [
                        {
                            "status": "error",
                            "code": "INVALID_DATA",
                            "message": "provider detail must remain hidden",
                        }
                    ]
                }
            ),
        ]
    )
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    with pytest.raises(ZohoOAuthError, match="Zoho CRM deal update failed") as error:
        asyncio.run(
            adapter.reassign_deal(
                CRMReassignmentRequest(
                    deal_id=deal.id,
                    incident_id=uuid4(),
                    approval_id=uuid4(),
                    current_owner="Anita Rao",
                    proposed_owner="Priya Shah",
                )
            )
        )
    assert error.value.status_code == 502
    assert "provider detail" not in str(error.value)


def test_snapshot_maps_fresh_zoho_state(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_connection(monkeypatch, "ZohoCRM.modules.deals.READ")
    deal = zoho_deal()
    client = FakeClient(
        [
            FakeResponse(
                {
                    "data": [
                        {
                            "Stage": "Closed Won",
                            "Owner": {"name": "Priya Shah"},
                            "Closing_Date": "2026-08-30",
                            "Modified_Time": "2026-08-08T09:30:00+05:30",
                        }
                    ]
                }
            )
        ]
    )
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    snapshot = asyncio.run(adapter.get_deal_snapshot(deal))
    assert snapshot.stage == "Closed Won"
    assert snapshot.owner_name == "Priya Shah"
    assert snapshot.status == "closed"
    assert snapshot.next_follow_up_at == datetime(2026, 8, 30, tzinfo=UTC)


def test_missing_write_scope_fails_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_connection(monkeypatch, "ZohoCRM.modules.deals.READ")
    deal = zoho_deal()
    client = FakeClient([])
    adapter = ZohoCRMAdapter(FakeSession(deal), client=client)  # type: ignore[arg-type]
    with pytest.raises(ZohoOAuthError, match="Reconnect Zoho CRM"):
        asyncio.run(
            adapter.reassign_deal(
                CRMReassignmentRequest(
                    deal_id=deal.id,
                    incident_id=uuid4(),
                    approval_id=uuid4(),
                    current_owner="Anita Rao",
                    proposed_owner="Priya Shah",
                )
            )
        )
    assert client.calls == []