from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import get_latest_analysis
from app.models import (
    AgentAuditEvent,
    ApprovalRequest,
    BottleneckIncident,
    Deal,
    FollowUpTask,
    MonitoringSettings,
    SalesOwnerCapacity,
)


class ActionExecutionError(Exception):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class CRMFollowUpRequest:
    deal_id: UUID
    incident_id: UUID
    title: str
    description: str
    assigned_to: str
    due_at: datetime


@dataclass(frozen=True)
class CRMReassignmentRequest:
    deal_id: UUID
    incident_id: UUID
    approval_id: UUID
    current_owner: str
    proposed_owner: str


@dataclass(frozen=True)
class CRMDealSnapshot:
    deal_id: UUID
    stage: str
    owner_name: str
    last_activity_at: datetime
    next_follow_up_at: datetime | None
    status: str


@dataclass(frozen=True)
class CRMActionResult:
    status: str
    external_task_id: str | None = None


class CRMAdapter(Protocol):
    async def create_follow_up(self, request: CRMFollowUpRequest) -> CRMActionResult: ...

    async def reassign_deal(self, request: CRMReassignmentRequest) -> CRMActionResult: ...

    async def get_deal_snapshot(self, deal: Deal) -> CRMDealSnapshot: ...


class LocalCRMAdapter:
    async def create_follow_up(self, request: CRMFollowUpRequest) -> CRMActionResult:
        return CRMActionResult(status="CREATED")

    async def reassign_deal(self, request: CRMReassignmentRequest) -> CRMActionResult:
        return CRMActionResult(status="REASSIGNED")

    async def get_deal_snapshot(self, deal: Deal) -> CRMDealSnapshot:
        return CRMDealSnapshot(
            deal_id=deal.id,
            stage=deal.stage,
            owner_name=deal.owner_name,
            last_activity_at=deal.last_activity_at,
            next_follow_up_at=deal.next_follow_up_at,
            status=deal.status,
        )


def configured_crm_adapter(session: AsyncSession) -> CRMAdapter:
    from app.config import get_settings

    if get_settings().crm_adapter.casefold() == "zoho":
        from app.zoho_adapter import ZohoCRMAdapter

        return ZohoCRMAdapter(session)
    return LocalCRMAdapter()


async def list_owner_capacities(session: AsyncSession) -> list[SalesOwnerCapacity]:
    return list(
        await session.scalars(
            select(SalesOwnerCapacity).order_by(SalesOwnerCapacity.owner_name)
        )
    )


async def list_approval_requests(
    session: AsyncSession,
    *,
    status: str | None = None,
) -> list[ApprovalRequest]:
    if await _expire_pending_approvals(session):
        await session.commit()
    statement = select(ApprovalRequest)
    if status is not None:
        statement = statement.where(ApprovalRequest.status == status)
    return list(await session.scalars(statement.order_by(ApprovalRequest.created_at.desc())))


async def get_approval_request(
    session: AsyncSession,
    approval_id: UUID,
) -> ApprovalRequest | None:
    if await _expire_pending_approvals(session, approval_id=approval_id):
        await session.commit()
    return await session.get(ApprovalRequest, approval_id)


async def _expire_pending_approvals(
    session: AsyncSession,
    *,
    approval_id: UUID | None = None,
    incident_id: UUID | None = None,
) -> bool:
    now = datetime.now(UTC)
    statement = select(ApprovalRequest).where(
        ApprovalRequest.status == "PENDING",
        ApprovalRequest.expires_at <= now,
    )
    if approval_id is not None:
        statement = statement.where(ApprovalRequest.id == approval_id)
    if incident_id is not None:
        statement = statement.where(ApprovalRequest.incident_id == incident_id)
    approvals = list(await session.scalars(statement.with_for_update()))
    for approval in approvals:
        approval.status = "EXPIRED"
        approval.reviewed_at = now
        session.add(
            AgentAuditEvent(
                incident_id=approval.incident_id,
                analysis_id=approval.agent_analysis_id,
                event_type="REASSIGNMENT_EXPIRED",
                status="COMPLETED",
                details={"approval_id": str(approval.id), "expired_at": now.isoformat()},
            )
        )
    if approvals:
        await session.flush()
    return bool(approvals)


async def request_deal_reassignment(
    session: AsyncSession,
    incident_id: UUID,
    user_id: UUID,
    *,
    proposed_owner: str | None = None,
    expires_hours: int = 24,
) -> ApprovalRequest:
    incident = await session.scalar(
        select(BottleneckIncident)
        .where(BottleneckIncident.id == incident_id)
        .with_for_update()
    )
    if incident is None:
        raise ActionExecutionError("Incident not found", status_code=404)
    if incident.deal_id is None:
        raise ActionExecutionError(
            "Select an affected deal before requesting reassignment for an owner incident.",
            status_code=409,
        )

    await _expire_pending_approvals(session, incident_id=incident_id)
    existing = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.incident_id == incident_id,
            ApprovalRequest.action_type == "REQUEST_REASSIGNMENT",
            ApprovalRequest.status == "PENDING",
        )
    )
    if existing is not None:
        return existing

    analysis = await get_latest_analysis(session, incident_id)
    if (
        analysis is None
        or analysis.status != "COMPLETED"
        or analysis.action_type != "REQUEST_REASSIGNMENT"
        or not analysis.approval_required
    ):
        raise ActionExecutionError(
            "The latest completed analysis does not recommend an approval-controlled reassignment.",
            status_code=409,
        )

    deal = await session.get(Deal, incident.deal_id)
    if deal is None:
        raise ActionExecutionError("Affected deal not found", status_code=404)
    if proposed_owner is None:
        target = await session.scalar(
            select(SalesOwnerCapacity)
            .where(
                SalesOwnerCapacity.is_active.is_(True),
                SalesOwnerCapacity.active_deals < SalesOwnerCapacity.max_active_deals,
                SalesOwnerCapacity.owner_name != deal.owner_name,
            )
            .order_by(
                SalesOwnerCapacity.active_deals * 1.0
                / SalesOwnerCapacity.max_active_deals,
                SalesOwnerCapacity.owner_name,
            )
            .limit(1)
        )
        if target is None:
            raise ActionExecutionError("No eligible owner has available capacity.", status_code=409)
        proposed_owner = target.owner_name
    else:
        target = await session.scalar(
            select(SalesOwnerCapacity).where(
                SalesOwnerCapacity.owner_name == proposed_owner
            )
        )
    _validate_reassignment_target(deal, target, proposed_owner)

    approval = ApprovalRequest(
        incident_id=incident.id,
        agent_analysis_id=analysis.id,
        action_type="REQUEST_REASSIGNMENT",
        requested_by=user_id,
        current_owner=deal.owner_name,
        proposed_owner=proposed_owner,
        reason=analysis.recommended_action or "Reassign the affected deal.",
        expected_outcome=analysis.expected_outcome or "Restore deal progression.",
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=expires_hours),
    )
    session.add(approval)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.incident_id == incident_id,
                ApprovalRequest.action_type == "REQUEST_REASSIGNMENT",
                ApprovalRequest.status == "PENDING",
            )
        )
        if existing is not None:
            return existing
        raise
    session.add(
        AgentAuditEvent(
            incident_id=incident.id,
            analysis_id=analysis.id,
            event_type="REASSIGNMENT_REQUESTED",
            status="PENDING",
            details={
                "approval_id": str(approval.id),
                "requested_by": str(user_id),
                "current_owner": deal.owner_name,
                "proposed_owner": proposed_owner,
                "expires_at": approval.expires_at.isoformat(),
            },
        )
    )
    await session.commit()
    await session.refresh(approval)
    return approval


def _validate_reassignment_target(
    deal: Deal,
    target: SalesOwnerCapacity | None,
    proposed_owner: str,
) -> None:
    if deal.status.casefold() != "active":
        raise ActionExecutionError("Only active deals can be reassigned.", status_code=409)
    if deal.owner_name == proposed_owner:
        raise ActionExecutionError("The proposed owner already owns this deal.", status_code=409)
    if target is None or not target.is_active:
        raise ActionExecutionError("The proposed owner is not active.", status_code=409)
    if target.active_deals >= target.max_active_deals:
        raise ActionExecutionError("The proposed owner is at capacity.", status_code=409)


async def review_deal_reassignment(
    session: AsyncSession,
    approval_id: UUID,
    reviewer_id: UUID,
    *,
    decision: str,
    comment: str | None = None,
    crm_adapter: CRMAdapter | None = None,
) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .with_for_update()
    )
    if approval is None:
        raise ActionExecutionError("Approval request not found", status_code=404)
    if approval.status == "EXECUTED" and decision == "APPROVE":
        return approval
    if approval.status != "PENDING":
        raise ActionExecutionError("This approval request is no longer pending.", status_code=409)

    now = datetime.now(UTC)
    if approval.expires_at <= now:
        approval.status = "EXPIRED"
        approval.reviewed_at = now
        session.add(
            AgentAuditEvent(
                incident_id=approval.incident_id,
                analysis_id=approval.agent_analysis_id,
                event_type="REASSIGNMENT_EXPIRED",
                status="COMPLETED",
                details={"approval_id": str(approval.id), "expired_at": now.isoformat()},
            )
        )
        await session.commit()
        raise ActionExecutionError("This approval request has expired.", status_code=409)
    if decision == "REJECT":
        approval.status = "REJECTED"
        approval.reviewed_by = reviewer_id
        approval.review_comment = comment
        approval.reviewed_at = now
        session.add(
            AgentAuditEvent(
                incident_id=approval.incident_id,
                analysis_id=approval.agent_analysis_id,
                event_type="REASSIGNMENT_REJECTED",
                status="COMPLETED",
                details={
                    "approval_id": str(approval.id),
                    "reviewed_by": str(reviewer_id),
                    "comment": comment,
                },
            )
        )
        await session.commit()
        await session.refresh(approval)
        return approval
    if decision != "APPROVE":
        raise ActionExecutionError("Decision must be APPROVE or REJECT.", status_code=422)

    incident = await session.scalar(
        select(BottleneckIncident)
        .where(BottleneckIncident.id == approval.incident_id)
        .with_for_update()
    )
    if incident is None:
        raise ActionExecutionError("Incident not found", status_code=404)
    deal = await session.scalar(
        select(Deal).where(Deal.id == incident.deal_id).with_for_update()
    )
    if deal is None:
        raise ActionExecutionError("Affected deal not found", status_code=404)
    if deal.owner_name != approval.current_owner:
        raise ActionExecutionError(
            "The deal owner changed after this request was created.", status_code=409
        )
    analysis = await get_latest_analysis(session, approval.incident_id)
    if analysis is None or analysis.id != approval.agent_analysis_id:
        raise ActionExecutionError("The supporting analysis is no longer current.", status_code=409)
    settings = await session.scalar(select(MonitoringSettings).limit(1).with_for_update())
    if settings is None or settings.high_impact_actions_disabled:
        raise ActionExecutionError("High-impact actions are currently disabled.", status_code=409)
    target = await session.scalar(
        select(SalesOwnerCapacity)
        .where(SalesOwnerCapacity.owner_name == approval.proposed_owner)
        .with_for_update()
    )
    _validate_reassignment_target(deal, target, approval.proposed_owner)
    assert target is not None

    request = CRMReassignmentRequest(
        deal_id=deal.id,
        incident_id=incident.id,
        approval_id=approval.id,
        current_owner=approval.current_owner,
        proposed_owner=approval.proposed_owner,
    )
    try:
        adapter_result = await (crm_adapter or configured_crm_adapter(session)).reassign_deal(request)
        if adapter_result.status != "REASSIGNED":
            raise RuntimeError(f"Unexpected CRM reassignment status: {adapter_result.status}")
    except Exception as error:
        approval.status = "EXECUTION_FAILED"
        approval.reviewed_by = reviewer_id
        approval.review_comment = comment
        approval.reviewed_at = now
        session.add(
            AgentAuditEvent(
                incident_id=approval.incident_id,
                analysis_id=approval.agent_analysis_id,
                event_type="DEAL_OWNER_REASSIGNMENT_FAILED",
                status="FAILED",
                details={
                    "approval_id": str(approval.id),
                    "reviewed_by": str(reviewer_id),
                    "before": {"deal_owner": deal.owner_name},
                    "after": {"deal_owner": deal.owner_name},
                    "error": str(error),
                },
            )
        )
        await session.commit()
        raise ActionExecutionError(
            "The CRM deal reassignment could not be completed.", status_code=502
        ) from error

    previous_owner = deal.owner_name
    previous_incident_status = incident.status
    deal.owner_name = approval.proposed_owner
    target.active_deals += 1
    previous_capacity = await session.scalar(
        select(SalesOwnerCapacity)
        .where(SalesOwnerCapacity.owner_name == previous_owner)
        .with_for_update()
    )
    if previous_capacity is not None and previous_capacity.active_deals > 0:
        previous_capacity.active_deals -= 1
    approval.status = "EXECUTED"
    approval.reviewed_by = reviewer_id
    approval.review_comment = comment
    approval.reviewed_at = now
    incident.status = "observing"
    verification_due_at = now + timedelta(hours=24)
    session.add(
        AgentAuditEvent(
            incident_id=incident.id,
            analysis_id=approval.agent_analysis_id,
            event_type="DEAL_OWNER_REASSIGNED",
            status="COMPLETED",
            details={
                "approval_id": str(approval.id),
                "reviewed_by": str(reviewer_id),
                "comment": comment,
                "crm_status": adapter_result.status,
                "verification_due_at": verification_due_at.isoformat(),
                "before": {
                    "deal_owner": previous_owner,
                    "incident_status": previous_incident_status,
                    "target_active_deals": target.active_deals - 1,
                },
                "after": {
                    "deal_owner": deal.owner_name,
                    "incident_status": incident.status,
                    "target_active_deals": target.active_deals,
                },
            },
        )
    )
    from app.outcomes import schedule_outcome_check

    await schedule_outcome_check(
        session,
        incident,
        deal,
        action_type="REQUEST_REASSIGNMENT",
        action_id=approval.id,
        now=now,
    )
    await session.commit()
    await session.refresh(approval)
    return approval


async def get_follow_up_task(
    session: AsyncSession,
    incident_id: UUID,
) -> FollowUpTask | None:
    return await session.scalar(
        select(FollowUpTask)
        .where(
            FollowUpTask.incident_id == incident_id,
            FollowUpTask.status.in_(("PENDING", "IN_PROGRESS")),
        )
        .order_by(FollowUpTask.created_at.desc())
        .limit(1)
    )


async def list_incident_actions(
    session: AsyncSession,
    incident_id: UUID,
) -> list[FollowUpTask]:
    return list(
        await session.scalars(
            select(FollowUpTask)
            .where(FollowUpTask.incident_id == incident_id)
            .order_by(FollowUpTask.created_at.desc())
        )
    )


async def create_follow_up_task(
    session: AsyncSession,
    incident_id: UUID,
    user_id: UUID | None,
    *,
    execution_source: str = "MANUAL",
    due_hours: int = 24,
    monitoring_run_id: UUID | None = None,
    crm_adapter: CRMAdapter | None = None,
) -> FollowUpTask:
    incident = await session.scalar(
        select(BottleneckIncident)
        .where(BottleneckIncident.id == incident_id)
        .with_for_update()
    )
    if incident is None:
        raise ActionExecutionError("Incident not found", status_code=404)
    if incident.deal_id is None:
        raise ActionExecutionError(
            "Follow-up creation requires a deal-level incident.", status_code=409
        )

    existing = await get_follow_up_task(session, incident_id)
    if existing is not None:
        return existing

    analysis = await get_latest_analysis(session, incident_id)
    if (
        analysis is None
        or analysis.status != "COMPLETED"
        or analysis.action_type != "CREATE_FOLLOW_UP"
    ):
        raise ActionExecutionError(
            "The latest completed analysis does not recommend CREATE_FOLLOW_UP.",
            status_code=409,
        )
    if analysis.approval_required:
        raise ActionExecutionError(
            "The recommended follow-up requires human approval before execution.",
            status_code=409,
        )

    deal = await session.get(Deal, incident.deal_id)
    if deal is None:
        raise ActionExecutionError("Affected deal not found", status_code=404)

    now = datetime.now(UTC)
    due_at = now + timedelta(hours=due_hours)
    request = CRMFollowUpRequest(
        deal_id=deal.id,
        incident_id=incident.id,
        title=f"Follow up on {deal.name}",
        description=analysis.recommended_action or "Follow up on the affected deal.",
        assigned_to=deal.owner_name,
        due_at=due_at,
    )
    before_status = incident.status
    task = FollowUpTask(
        deal_id=request.deal_id,
        incident_id=request.incident_id,
        agent_analysis_id=analysis.id,
        title=request.title,
        description=request.description,
        assigned_to=request.assigned_to,
        due_at=request.due_at,
        status="PENDING",
        execution_source=execution_source,
        execution_result={
            "status": "CLAIMED",
            "external_task_id": None,
            "verification_due_at": due_at.isoformat(),
        },
        created_by=user_id,
    )
    session.add(task)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await get_follow_up_task(session, incident_id)
        if existing is not None:
            return existing
        raise

    try:
        adapter_result = await (crm_adapter or configured_crm_adapter(session)).create_follow_up(request)
    except Exception as error:
        await session.rollback()
        raise ActionExecutionError(
            "The CRM follow-up could not be created.", status_code=502
        ) from error
    task.execution_result = {
        **task.execution_result,
        "status": adapter_result.status,
        "external_task_id": adapter_result.external_task_id,
        "task_id": str(task.id),
    }
    incident.status = "observing"
    session.add(
        AgentAuditEvent(
            incident_id=incident.id,
            analysis_id=analysis.id,
            monitoring_run_id=monitoring_run_id,
            event_type="CREATE_FOLLOW_UP",
            status="COMPLETED",
            details={
                "task_id": str(task.id),
                "deal_id": str(deal.id),
                "execution_source": execution_source,
                "assigned_to": task.assigned_to,
                "due_at": task.due_at.isoformat(),
                "result_status": task.status,
                "result": task.execution_result,
                "before": {"incident_status": before_status},
                "after": {
                    "incident_status": incident.status,
                    "task_status": task.status,
                },
            },
        )
    )
    from app.outcomes import schedule_outcome_check

    await schedule_outcome_check(
        session,
        incident,
        deal,
        action_type="CREATE_FOLLOW_UP",
        action_id=task.id,
        now=now,
    )
    await session.commit()
    await session.refresh(task)
    return task