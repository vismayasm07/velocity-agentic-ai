from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection import run_stalled_deal_scan
from app.models import AgentAuditEvent, Deal
from app.zoho import ZohoDeal, ZohoOAuthError, fetch_deals


@dataclass(frozen=True)
class ZohoDealSyncResult:
    fetched: int
    created: int
    updated: int
    unchanged: int
    failed: int
    errors: list[dict[str, str]]
    started_at: datetime
    completed_at: datetime


def _closing_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
    except ValueError:
        return None


def _mapped_values(deal: ZohoDeal, synced_at: datetime) -> dict[str, object]:
    if not deal.deal_name:
        raise ValueError("Deal name is required")
    modified_at = deal.modified_time
    return {
        "name": deal.deal_name,
        "value": deal.amount if deal.amount is not None else Decimal("0.00"),
        "stage": deal.stage or "Unknown",
        "owner_name": deal.owner or "Unassigned",
        "last_activity_at": modified_at or synced_at,
        "next_follow_up_at": _closing_datetime(deal.closing_date),
        "status": (
            "closed" if (deal.stage or "").casefold() in {"closed won", "closed lost"} else "active"
        ),
        "zoho_modified_at": modified_at,
    }


def _is_unchanged(local_deal: Deal, zoho_deal: ZohoDeal, values: dict[str, object]) -> bool:
    if zoho_deal.modified_time is not None and local_deal.zoho_modified_at is not None:
        return zoho_deal.modified_time <= local_deal.zoho_modified_at
    return all(
        getattr(local_deal, field) == value
        for field, value in values.items()
        if field != "last_activity_at"
    )


async def synchronize_zoho_deals(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
) -> ZohoDealSyncResult:
    started_at = datetime.now(UTC)
    session.add(
        AgentAuditEvent(
            event_type="ZOHO_DEAL_SYNC_STARTED",
            status="STARTED",
            details={"started_at": started_at.isoformat()},
        )
    )
    await session.commit()

    try:
        zoho_deals = await fetch_deals(session, client=client)
    except ZohoOAuthError:
        completed_at = datetime.now(UTC)
        session.add(
            AgentAuditEvent(
                event_type="ZOHO_DEAL_SYNC_COMPLETED",
                status="FAILED",
                details={
                    "error": "Zoho deal fetch failed",
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                },
            )
        )
        await session.commit()
        raise
    created = 0
    updated = 0
    unchanged = 0
    errors: list[dict[str, str]] = []
    synchronized_ids: set[UUID] = set()

    for zoho_deal in zoho_deals:
        try:
            async with session.begin_nested():
                synced_at = datetime.now(UTC)
                values = _mapped_values(zoho_deal, synced_at)
                local_deal = await session.scalar(
                    select(Deal).where(Deal.zoho_record_id == zoho_deal.zoho_record_id)
                )
                if local_deal is None:
                    created_at = zoho_deal.created_time or zoho_deal.modified_time or synced_at
                    local_deal = Deal(
                        zoho_record_id=zoho_deal.zoho_record_id,
                        source="zoho",
                        stage_entered_at=created_at,
                        created_at=created_at,
                        last_synced_at=synced_at,
                        **values,
                    )
                    session.add(local_deal)
                    await session.flush()
                    created += 1
                elif _is_unchanged(local_deal, zoho_deal, values):
                    unchanged += 1
                else:
                    if local_deal.stage != values["stage"]:
                        local_deal.stage_entered_at = synced_at
                    for field, value in values.items():
                        setattr(local_deal, field, value)
                    local_deal.source = "zoho"
                    local_deal.last_synced_at = synced_at
                    await session.flush()
                    updated += 1
                synchronized_ids.add(local_deal.id)
        except Exception:
            errors.append(
                {
                    "zoho_record_id": zoho_deal.zoho_record_id,
                    "error": "Deal record could not be synchronized",
                }
            )

    await session.commit()
    detection_result = await run_stalled_deal_scan(session, deal_ids=synchronized_ids)
    for error in detection_result.errors:
        errors.append(
            {
                "deal_id": error.get("deal_id", "unknown"),
                "error": "Post-sync detection failed for deal",
            }
        )

    completed_at = datetime.now(UTC)
    result = ZohoDealSyncResult(
        fetched=len(zoho_deals),
        created=created,
        updated=updated,
        unchanged=unchanged,
        failed=len(errors),
        errors=errors,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(
        AgentAuditEvent(
            event_type="ZOHO_DEAL_SYNC_COMPLETED",
            status="PARTIAL" if errors else "COMPLETED",
            details={
                "fetched": result.fetched,
                "created": result.created,
                "updated": result.updated,
                "unchanged": result.unchanged,
                "failed": result.failed,
                "errors": result.errors,
                "started_at": result.started_at.isoformat(),
                "completed_at": result.completed_at.isoformat(),
            },
        )
    )
    await session.commit()
    return result