from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BottleneckIncident, Deal, MonitoringSettings, SalesOwnerCapacity

INCIDENT_TYPE = "stalled_deal"
OWNER_OVERLOAD_INCIDENT_TYPE = "owner_overload"
INCIDENT_THRESHOLD = 40


@dataclass(frozen=True)
class DetectionResult:
    risk_score: int
    severity: str
    evidence: dict[str, object]

    @property
    def is_stalled(self) -> bool:
        return self.risk_score >= INCIDENT_THRESHOLD


@dataclass(frozen=True)
class DetectionScanResult:
    incidents: list[BottleneckIncident]
    deals_scanned: int
    incidents_created: int
    incidents_updated: int
    errors: list[dict[str, str]]
    analysis_candidate_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class DetectionRules:
    stage_sla_hours: int = 168
    inactivity_threshold_hours: int = 120
    overdue_follow_up_enabled: bool = True


@dataclass(frozen=True)
class OwnerWorkload:
    owner_name: str
    active_deals: int
    pipeline_value: Decimal
    high_risk_deals: int
    overdue_follow_ups: int
    open_incidents: int
    affected_deal_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class OwnerOverloadRules:
    max_active_deals: int
    max_high_risk_deals: int
    max_overdue_follow_ups: int
    max_pipeline_value: Decimal | None = None


@dataclass(frozen=True)
class OwnerOverloadResult:
    risk_score: int
    severity: str
    evidence: dict[str, object]
    is_overloaded: bool


def severity_for_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def detect_owner_overload(
    workload: OwnerWorkload,
    rules: OwnerOverloadRules,
) -> OwnerOverloadResult:
    factors = (
        ("active_deals", workload.active_deals, rules.max_active_deals, 35),
        ("high_risk_deals", workload.high_risk_deals, rules.max_high_risk_deals, 25),
        ("overdue_follow_ups", workload.overdue_follow_ups, rules.max_overdue_follow_ups, 20),
        ("pipeline_value", workload.pipeline_value, rules.max_pipeline_value, 10),
    )
    evidence: dict[str, object] = {}
    risk_score = 0
    overloaded = False
    for name, value, threshold, weight in factors:
        enabled = threshold is not None
        triggered = enabled and value > threshold
        overloaded = overloaded or triggered
        points = (
            min(weight, int((Decimal(value) / Decimal(threshold)) * weight))
            if enabled and threshold > 0
            else 0
        )
        risk_score += points
        evidence[name] = {
            "value": str(value) if isinstance(value, Decimal) else value,
            "threshold": (
                str(threshold) if isinstance(threshold, Decimal) else threshold
            ),
            "enabled": enabled,
            "points": points,
            "triggered": triggered,
        }

    incident_points = min(10, workload.open_incidents * 2)
    risk_score = min(100, risk_score + incident_points)
    evidence["open_incidents"] = {
        "value": workload.open_incidents,
        "points": incident_points,
        "triggered": workload.open_incidents > 0,
    }
    evidence["owner_name"] = workload.owner_name
    evidence["affected_deal_ids"] = [str(deal_id) for deal_id in workload.affected_deal_ids]
    evidence["total"] = risk_score
    return OwnerOverloadResult(
        risk_score=risk_score,
        severity=severity_for_score(risk_score),
        evidence=evidence,
        is_overloaded=overloaded,
    )


def detect_stalled_deal(
    deal: Deal,
    now: datetime | None = None,
    rules: DetectionRules | None = None,
) -> DetectionResult:
    detected_at = now or datetime.now(UTC)
    active_rules = rules or DetectionRules()
    stage_hours = max(0, int((detected_at - deal.stage_entered_at).total_seconds() // 3600))
    inactive_hours = max(0, int((detected_at - deal.last_activity_at).total_seconds() // 3600))
    stage_days = max(0, (detected_at - deal.stage_entered_at).days)
    inactive_days = max(0, (detected_at - deal.last_activity_at).days)
    overdue_days = (
        max(0, (detected_at - deal.next_follow_up_at).days)
        if active_rules.overdue_follow_up_enabled
        and deal.next_follow_up_at is not None
        and deal.next_follow_up_at < detected_at
        else 0
    )

    stage_points = min(
        35, max(0, (stage_hours - active_rules.stage_sla_hours) // 24) * 5
    )
    activity_points = min(
        45,
        max(0, (inactive_hours - active_rules.inactivity_threshold_hours) // 24) * 7,
    )
    follow_up_points = min(50, 40 + overdue_days * 5) if overdue_days > 0 else 0
    risk_score = min(100, stage_points + activity_points + follow_up_points)
    evidence: dict[str, object] = {
        "stage_duration": {
            "days": stage_days,
            "threshold_days": active_rules.stage_sla_hours // 24,
            "points": stage_points,
            "triggered": stage_points > 0,
        },
        "activity_gap": {
            "days": inactive_days,
            "threshold_days": active_rules.inactivity_threshold_hours // 24,
            "points": activity_points,
            "triggered": activity_points > 0,
        },
        "overdue_follow_up": {
            "days": overdue_days,
            "enabled": active_rules.overdue_follow_up_enabled,
            "points": follow_up_points,
            "triggered": follow_up_points > 0,
        },
        "total": risk_score,
    }
    if rules is not None:
        for name, hours, threshold in (
            ("stage_duration", stage_hours, active_rules.stage_sla_hours),
            ("activity_gap", inactive_hours, active_rules.inactivity_threshold_hours),
        ):
            evidence_item = evidence[name]
            if isinstance(evidence_item, dict):
                evidence_item["hours"] = hours
                evidence_item["threshold_hours"] = threshold
    return DetectionResult(
        risk_score=risk_score,
        severity=severity_for_score(risk_score),
        evidence=evidence,
    )


async def run_stalled_deal_scan(
    session: AsyncSession,
    monitoring_settings: MonitoringSettings | None = None,
    deal_ids: set[UUID] | None = None,
) -> DetectionScanResult:
    now = datetime.now(UTC)
    active_settings = monitoring_settings or await session.scalar(
        select(MonitoringSettings).limit(1)
    )
    rules = (
        DetectionRules(
            stage_sla_hours=active_settings.stage_sla_hours,
            inactivity_threshold_hours=active_settings.inactivity_threshold_hours,
            overdue_follow_up_enabled=active_settings.overdue_follow_up_enabled,
        )
        if active_settings is not None
        else DetectionRules()
    )
    deal_query = select(Deal)
    if deal_ids is not None:
        deal_query = deal_query.where(Deal.id.in_(deal_ids))
    deals = list(await session.scalars(deal_query))
    incident_query = select(BottleneckIncident).where(
        BottleneckIncident.incident_type == INCIDENT_TYPE,
        BottleneckIncident.status.in_(("open", "observing", "OBSERVING", "escalated")),
    )
    if deal_ids is not None:
        incident_query = incident_query.where(BottleneckIncident.deal_id.in_(deal_ids))
    active_incidents = {
        incident.deal_id: incident
        for incident in await session.scalars(incident_query)
    }
    detected: list[BottleneckIncident] = []
    incidents_created = 0
    incidents_updated = 0
    errors: list[dict[str, str]] = []
    analysis_candidate_ids: list[UUID] = []

    for deal in deals:
        try:
            async with session.begin_nested():
                result = detect_stalled_deal(deal, now, rules)
                incident = active_incidents.get(deal.id)
                if not result.is_stalled:
                    if incident is not None and incident.status == "open":
                        incident.status = "resolved"
                        incident.updated_at = now
                        incidents_updated += 1
                    continue

                if incident is None:
                    incident = BottleneckIncident(
                        deal_id=deal.id,
                        incident_type=INCIDENT_TYPE,
                        title=f"Stalled deal: {deal.name}",
                        severity=result.severity,
                        risk_score=result.risk_score,
                        evidence=result.evidence,
                        status="open",
                        analysis_state="PENDING_ANALYSIS",
                        detected_at=now,
                        updated_at=now,
                    )
                    session.add(incident)
                    await session.flush()
                    incidents_created += 1
                    analysis_candidate_ids.append(incident.id)
                else:
                    if incident.status == "OBSERVING":
                        incident.status = "observing"
                    materially_changed = (
                        incident.risk_score != result.risk_score
                        or incident.evidence != result.evidence
                    )
                    incident.title = f"Stalled deal: {deal.name}"
                    incident.severity = result.severity
                    incident.risk_score = result.risk_score
                    incident.evidence = result.evidence
                    incident.updated_at = now
                    incidents_updated += 1
                    if materially_changed:
                        incident.analysis_state = "PENDING_ANALYSIS"
                        analysis_candidate_ids.append(incident.id)
                detected.append(incident)
        except Exception as error:
            errors.append({"deal_id": str(deal.id), "error": str(error)})

    await session.commit()
    for incident in detected:
        await session.refresh(incident)
    return DetectionScanResult(
        incidents=detected,
        deals_scanned=len(deals),
        incidents_created=incidents_created,
        incidents_updated=incidents_updated,
        errors=errors,
        analysis_candidate_ids=tuple(analysis_candidate_ids),
    )


async def run_owner_overload_scan(
    session: AsyncSession,
    monitoring_settings: MonitoringSettings | None = None,
    *,
    owner_capacity_ids: set[UUID] | None = None,
) -> DetectionScanResult:
    now = datetime.now(UTC)
    settings = monitoring_settings or await session.scalar(
        select(MonitoringSettings).limit(1)
    )
    if settings is None or not settings.owner_overload_enabled:
        return DetectionScanResult([], 0, 0, 0, [])

    deal_rules = DetectionRules(
        stage_sla_hours=settings.stage_sla_hours,
        inactivity_threshold_hours=settings.inactivity_threshold_hours,
        overdue_follow_up_enabled=settings.overdue_follow_up_enabled,
    )
    overload_rules = OwnerOverloadRules(
        max_active_deals=settings.owner_max_active_deals,
        max_high_risk_deals=settings.owner_max_high_risk_deals,
        max_overdue_follow_ups=settings.owner_max_overdue_follow_ups,
        max_pipeline_value=settings.owner_max_pipeline_value,
    )
    owner_statement = select(SalesOwnerCapacity).where(SalesOwnerCapacity.is_active.is_(True))
    if owner_capacity_ids is not None:
        owner_statement = owner_statement.where(SalesOwnerCapacity.id.in_(owner_capacity_ids))
    owners = list(await session.scalars(owner_statement))
    active_deals = list(
        await session.scalars(select(Deal).where(Deal.status.ilike("active")))
    )
    open_deal_incidents = list(
        await session.scalars(
            select(BottleneckIncident).where(
                BottleneckIncident.deal_id.is_not(None),
                BottleneckIncident.status.in_(
                    ("open", "observing", "OBSERVING", "escalated")
                ),
            )
        )
    )
    owner_incidents = {
        incident.owner_capacity_id: incident
        for incident in await session.scalars(
            select(BottleneckIncident).where(
                BottleneckIncident.incident_type == OWNER_OVERLOAD_INCIDENT_TYPE,
                BottleneckIncident.status.in_(("open", "observing", "OBSERVING")),
            )
        )
    }
    deal_owner_by_id = {deal.id: deal.owner_name for deal in active_deals}
    open_incident_counts: dict[str, int] = {}
    for incident in open_deal_incidents:
        owner_name = deal_owner_by_id.get(incident.deal_id)
        if owner_name is not None:
            open_incident_counts[owner_name] = open_incident_counts.get(owner_name, 0) + 1

    detected: list[BottleneckIncident] = []
    created = 0
    updated = 0
    errors: list[dict[str, str]] = []
    candidate_ids: list[UUID] = []
    for owner in owners:
        try:
            async with session.begin_nested():
                owner_deals = [deal for deal in active_deals if deal.owner_name == owner.owner_name]
                high_risk = [
                    deal
                    for deal in owner_deals
                    if detect_stalled_deal(deal, now, deal_rules).is_stalled
                ]
                overdue = [
                    deal
                    for deal in owner_deals
                    if deal.next_follow_up_at is not None and deal.next_follow_up_at < now
                ]
                workload = OwnerWorkload(
                    owner_name=owner.owner_name,
                    active_deals=len(owner_deals),
                    pipeline_value=sum((deal.value for deal in owner_deals), Decimal("0")),
                    high_risk_deals=len(high_risk),
                    overdue_follow_ups=len(overdue),
                    open_incidents=open_incident_counts.get(owner.owner_name, 0),
                    affected_deal_ids=tuple(deal.id for deal in owner_deals),
                )
                result = detect_owner_overload(workload, overload_rules)
                incident = owner_incidents.get(owner.id)
                if not result.is_overloaded:
                    if incident is not None and incident.status == "open":
                        incident.status = "resolved"
                        incident.updated_at = now
                        updated += 1
                    continue

                title = f"Owner workload overload: {owner.owner_name}"
                if incident is None:
                    incident = BottleneckIncident(
                        deal_id=None,
                        owner_capacity_id=owner.id,
                        incident_type=OWNER_OVERLOAD_INCIDENT_TYPE,
                        title=title,
                        severity=result.severity,
                        risk_score=result.risk_score,
                        evidence=result.evidence,
                        status="open",
                        analysis_state="PENDING_ANALYSIS",
                        detected_at=now,
                        updated_at=now,
                    )
                    session.add(incident)
                    await session.flush()
                    created += 1
                    candidate_ids.append(incident.id)
                else:
                    materially_changed = (
                        incident.risk_score != result.risk_score
                        or incident.evidence != result.evidence
                    )
                    incident.status = "observing" if incident.status == "OBSERVING" else incident.status
                    incident.title = title
                    incident.severity = result.severity
                    incident.risk_score = result.risk_score
                    incident.evidence = result.evidence
                    incident.updated_at = now
                    updated += 1
                    if materially_changed:
                        incident.analysis_state = "PENDING_ANALYSIS"
                        candidate_ids.append(incident.id)
                detected.append(incident)
        except Exception as error:
            errors.append({"owner_capacity_id": str(owner.id), "error": str(error)})

    await session.commit()
    for incident in detected:
        await session.refresh(incident)
    return DetectionScanResult(
        incidents=detected,
        deals_scanned=0,
        incidents_created=created,
        incidents_updated=updated,
        errors=errors,
        analysis_candidate_ids=tuple(candidate_ids),
    )


async def run_detection_scan(session: AsyncSession) -> DetectionScanResult:
    settings = await session.scalar(select(MonitoringSettings).limit(1))
    deal_result = await run_stalled_deal_scan(session, settings)
    owner_result = await run_owner_overload_scan(session, settings)
    return DetectionScanResult(
        incidents=[*deal_result.incidents, *owner_result.incidents],
        deals_scanned=deal_result.deals_scanned,
        incidents_created=deal_result.incidents_created + owner_result.incidents_created,
        incidents_updated=deal_result.incidents_updated + owner_result.incidents_updated,
        errors=[*deal_result.errors, *owner_result.errors],
        analysis_candidate_ids=(
            *deal_result.analysis_candidate_ids,
            *owner_result.analysis_candidate_ids,
        ),
    )


async def scan_stalled_deals(session: AsyncSession) -> list[BottleneckIncident]:
    return (await run_stalled_deal_scan(session)).incidents