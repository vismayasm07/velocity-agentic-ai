from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import CRMAdapter, configured_crm_adapter
from app.detection import DetectionRules, detect_stalled_deal, severity_for_score
from app.models import (
    AgentAuditEvent,
    ApprovalRequest,
    BottleneckIncident,
    Deal,
    FollowUpTask,
    IncidentOutcome,
    MonitoringSettings,
)


class OutcomeVerificationError(Exception):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def list_incident_outcomes(
    session: AsyncSession, incident_id: UUID
) -> list[IncidentOutcome]:
    return list(
        await session.scalars(
            select(IncidentOutcome)
            .where(IncidentOutcome.incident_id == incident_id)
            .order_by(IncidentOutcome.created_at.desc())
        )
    )


async def schedule_outcome_check(
    session: AsyncSession,
    incident: BottleneckIncident,
    deal: Deal,
    *,
    action_type: str,
    action_id: UUID,
    now: datetime | None = None,
) -> IncidentOutcome | None:
    settings = await session.scalar(select(MonitoringSettings).limit(1))
    if settings is None or not settings.outcome_verification_enabled:
        return None
    existing = await session.scalar(
        select(IncidentOutcome).where(
            IncidentOutcome.incident_id == incident.id,
            IncidentOutcome.verification_status.in_(("PENDING", "RUNNING")),
        )
    )
    if existing is not None:
        return existing
    scheduled_at = now or datetime.now(UTC)
    outcome = IncidentOutcome(
        incident_id=incident.id,
        action_type=action_type,
        action_id=action_id,
        verification_status="PENDING",
        previous_risk_score=incident.risk_score,
        current_risk_score=None,
        verification_evidence={
            "baseline": {
                "stage": deal.stage,
                "owner_name": deal.owner_name,
                "last_activity_at": deal.last_activity_at.isoformat(),
                "next_follow_up_at": (
                    deal.next_follow_up_at.isoformat() if deal.next_follow_up_at else None
                ),
                "incident_evidence": incident.evidence,
            },
            "checks_completed": 0,
        },
        outcome="AWAITING_EVIDENCE",
        next_check_at=scheduled_at + timedelta(minutes=settings.outcome_check_delay_minutes),
    )
    session.add(outcome)
    session.add(
        AgentAuditEvent(
            incident_id=incident.id,
            event_type="OBSERVATION_STARTED",
            status="PENDING",
            details={
                "action_type": action_type,
                "action_id": str(action_id),
                "previous_risk_score": incident.risk_score,
                "next_check_at": outcome.next_check_at.isoformat(),
            },
        )
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return await session.scalar(
            select(IncidentOutcome).where(
                IncidentOutcome.incident_id == incident.id,
                IncidentOutcome.verification_status.in_(("PENDING", "RUNNING")),
            )
        )
    return outcome


def _rules(settings: MonitoringSettings) -> DetectionRules:
    return DetectionRules(
        stage_sla_hours=settings.stage_sla_hours,
        inactivity_threshold_hours=settings.inactivity_threshold_hours,
        overdue_follow_up_enabled=settings.overdue_follow_up_enabled,
    )


async def verify_incident_outcome(
    session: AsyncSession,
    incident_id: UUID,
    *,
    force: bool = False,
    crm_adapter: CRMAdapter | None = None,
    monitoring_run_id: UUID | None = None,
) -> IncidentOutcome:
    incident = await session.scalar(
        select(BottleneckIncident)
        .where(BottleneckIncident.id == incident_id)
        .with_for_update()
    )
    if incident is None:
        raise OutcomeVerificationError("Incident not found", status_code=404)
    pending = await session.scalar(
        select(IncidentOutcome)
        .where(
            IncidentOutcome.incident_id == incident_id,
            IncidentOutcome.verification_status == "PENDING",
        )
        .order_by(IncidentOutcome.created_at.desc())
        .with_for_update()
    )
    if pending is None:
        latest = await session.scalar(
            select(IncidentOutcome)
            .where(IncidentOutcome.incident_id == incident_id)
            .order_by(IncidentOutcome.created_at.desc())
            .limit(1)
        )
        if latest is not None and latest.verification_status == "COMPLETED":
            return latest
        raise OutcomeVerificationError("No outcome check is scheduled", status_code=409)
    now = datetime.now(UTC)
    if not force and pending.next_check_at is not None and pending.next_check_at > now:
        raise OutcomeVerificationError("The outcome check is not due yet", status_code=409)
    settings = await session.scalar(select(MonitoringSettings).limit(1))
    if settings is None:
        raise OutcomeVerificationError("Monitoring settings are unavailable", status_code=503)
    if incident.deal_id is None:
        raise OutcomeVerificationError(
            "Owner incidents are verified by fresh workload detection.", status_code=409
        )
    deal = await session.get(Deal, incident.deal_id)
    if deal is None:
        raise OutcomeVerificationError("Affected deal not found", status_code=404)

    pending.verification_status = "RUNNING"
    session.add(
        AgentAuditEvent(
            incident_id=incident.id,
            monitoring_run_id=monitoring_run_id,
            event_type="OUTCOME_CHECK_STARTED",
            status="RUNNING",
            details={"outcome_id": str(pending.id), "action_type": pending.action_type},
        )
    )
    await session.flush()

    snapshot = await (crm_adapter or configured_crm_adapter(session)).get_deal_snapshot(deal)
    evidence = dict(pending.verification_evidence)
    baseline = evidence.get("baseline", {})
    if not isinstance(baseline, dict):
        baseline = {}
    deal.stage = snapshot.stage
    deal.owner_name = snapshot.owner_name
    deal.last_activity_at = snapshot.last_activity_at
    deal.next_follow_up_at = snapshot.next_follow_up_at
    deal.status = snapshot.status
    result = detect_stalled_deal(deal, now, _rules(settings))
    checks_completed = int(evidence.get("checks_completed", 0)) + 1
    activity_resumed = snapshot.last_activity_at > datetime.fromisoformat(
        str(baseline.get("last_activity_at"))
    )
    stage_moved = snapshot.stage != baseline.get("stage")
    owner_reassigned = snapshot.owner_name != baseline.get("owner_name")
    overdue_addressed = not bool(result.evidence["overdue_follow_up"]["triggered"])
    risk_decreased = result.risk_score < pending.previous_risk_score
    original_conditions_exist = result.is_stalled
    action_completed = await _action_completed(session, pending)
    fresh_evidence: dict[str, object] = {
        "activity_resumed": activity_resumed,
        "overdue_follow_up_addressed": overdue_addressed,
        "pipeline_stage_moved": stage_moved,
        "owner_reassignment_completed": owner_reassigned,
        "action_completed": action_completed,
        "risk_decreased": risk_decreased,
        "original_bottleneck_conditions_exist": original_conditions_exist,
        "detector_evidence": result.evidence,
        "current": {
            "stage": snapshot.stage,
            "owner_name": snapshot.owner_name,
            "last_activity_at": snapshot.last_activity_at.isoformat(),
            "next_follow_up_at": (
                snapshot.next_follow_up_at.isoformat() if snapshot.next_follow_up_at else None
            ),
        },
        "checks_completed": checks_completed,
    }
    pending.verification_evidence = {**evidence, **fresh_evidence}
    pending.current_risk_score = result.risk_score
    pending.verified_at = now
    pending.next_check_at = None
    pending.verification_status = "COMPLETED"
    incident.risk_score = result.risk_score
    incident.severity = severity_for_score(result.risk_score)
    incident.evidence = result.evidence
    incident.updated_at = now

    if not action_completed:
        pending.outcome = "FAILED"
        incident.status = "escalated"
        reason = "The corrective action did not complete successfully."
        terminal_event = "INCIDENT_ESCALATED"
    elif result.risk_score <= settings.resolution_risk_threshold and not original_conditions_exist:
        pending.outcome = "SUCCESSFUL"
        incident.status = "resolved"
        reason = "The deterministic risk score and original bottleneck conditions cleared."
        terminal_event = "INCIDENT_RESOLVED"
    elif checks_completed >= settings.maximum_outcome_checks:
        pending.outcome = "FAILED" if not risk_decreased else "PARTIALLY_SUCCESSFUL"
        incident.status = "escalated"
        reason = "Risk remained above the resolution threshold after the maximum checks."
        terminal_event = "INCIDENT_ESCALATED"
    else:
        pending.outcome = "PARTIALLY_SUCCESSFUL" if risk_decreased else "AWAITING_EVIDENCE"
        incident.status = "observing"
        reason = (
            "Risk decreased, but more evidence is required."
            if risk_decreased
            else "The bottleneck evidence is unchanged; observation will continue."
        )
        await _schedule_retry(session, incident, pending, settings, now)
        terminal_event = None

    pending.verification_evidence = {**pending.verification_evidence, "reason": reason}
    session.add_all(
        [
            AgentAuditEvent(
                incident_id=incident.id,
                monitoring_run_id=monitoring_run_id,
                event_type="OUTCOME_EVIDENCE_COLLECTED",
                status="COMPLETED",
                details={"outcome_id": str(pending.id), **fresh_evidence},
            ),
            AgentAuditEvent(
                incident_id=incident.id,
                monitoring_run_id=monitoring_run_id,
                event_type="RISK_SCORE_CHANGED",
                status="COMPLETED",
                details={
                    "outcome_id": str(pending.id),
                    "previous": pending.previous_risk_score,
                    "current": result.risk_score,
                },
            ),
        ]
    )
    if terminal_event is not None:
        session.add(
            AgentAuditEvent(
                incident_id=incident.id,
                monitoring_run_id=monitoring_run_id,
                event_type=terminal_event,
                status="COMPLETED",
                details={"outcome_id": str(pending.id), "reason": reason},
            )
        )
    await session.commit()
    await session.refresh(pending)
    return pending


async def _action_completed(session: AsyncSession, outcome: IncidentOutcome) -> bool:
    if outcome.action_type == "CREATE_FOLLOW_UP":
        task = await session.get(FollowUpTask, outcome.action_id)
        return task is not None and task.status not in ("FAILED", "CANCELLED")
    if outcome.action_type == "REQUEST_REASSIGNMENT":
        approval = await session.get(ApprovalRequest, outcome.action_id)
        return approval is not None and approval.status == "EXECUTED"
    return False


async def _schedule_retry(
    session: AsyncSession,
    incident: BottleneckIncident,
    completed: IncidentOutcome,
    settings: MonitoringSettings,
    now: datetime,
) -> None:
    retry = IncidentOutcome(
        incident_id=incident.id,
        action_type=completed.action_type,
        action_id=completed.action_id,
        verification_status="PENDING",
        previous_risk_score=completed.previous_risk_score,
        current_risk_score=None,
        verification_evidence=completed.verification_evidence,
        outcome="AWAITING_EVIDENCE",
        next_check_at=now + timedelta(minutes=settings.outcome_check_delay_minutes),
    )
    session.add(retry)


async def verify_due_outcomes(
    session: AsyncSession, *, monitoring_run_id: UUID | None = None
) -> list[IncidentOutcome]:
    settings = await session.scalar(select(MonitoringSettings).limit(1))
    if settings is None or not settings.outcome_verification_enabled:
        return []
    now = datetime.now(UTC)
    incident_ids = list(
        await session.scalars(
            select(IncidentOutcome.incident_id).where(
                IncidentOutcome.verification_status == "PENDING",
                IncidentOutcome.next_check_at <= now,
            )
        )
    )
    verified = []
    for incident_id in incident_ids:
        try:
            verified.append(
                await verify_incident_outcome(
                    session, incident_id, monitoring_run_id=monitoring_run_id
                )
            )
        except OutcomeVerificationError:
            continue
    return verified


async def reopen_recurred_incidents(session: AsyncSession) -> list[BottleneckIncident]:
    settings = await session.scalar(select(MonitoringSettings).limit(1))
    if settings is None:
        return []
    incidents = list(
        await session.scalars(
            select(BottleneckIncident)
            .where(BottleneckIncident.status == "resolved")
            .with_for_update()
        )
    )
    reopened = []
    now = datetime.now(UTC)
    for incident in incidents:
        if incident.deal_id is None:
            continue
        deal = await session.get(Deal, incident.deal_id)
        if deal is None:
            continue
        result = detect_stalled_deal(deal, now, _rules(settings))
        if not result.is_stalled:
            continue
        active_incident_id = await session.scalar(
            select(BottleneckIncident.id).where(
                BottleneckIncident.deal_id == incident.deal_id,
                BottleneckIncident.incident_type == incident.incident_type,
                BottleneckIncident.status == "open",
                BottleneckIncident.id != incident.id,
            )
        )
        if active_incident_id is not None:
            continue
        incident.status = "open"
        incident.risk_score = result.risk_score
        incident.severity = result.severity
        incident.evidence = result.evidence
        incident.analysis_state = "PENDING_ANALYSIS"
        latest = await session.scalar(
            select(IncidentOutcome)
            .where(IncidentOutcome.incident_id == incident.id)
            .order_by(IncidentOutcome.created_at.desc())
            .limit(1)
        )
        if latest is not None:
            latest.outcome = "RECURRED"
        session.add(
            AgentAuditEvent(
                incident_id=incident.id,
                event_type="INCIDENT_RECURRED",
                status="COMPLETED",
                details={"current_risk_score": result.risk_score},
            )
        )
        reopened.append(incident)
    if reopened:
        await session.commit()
    return reopened