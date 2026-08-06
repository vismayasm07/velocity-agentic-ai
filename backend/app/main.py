from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import (
    ActionExecutionError,
    create_follow_up_task,
    get_approval_request,
    get_follow_up_task,
    list_approval_requests,
    list_incident_actions,
    list_owner_capacities,
    request_deal_reassignment,
    review_deal_reassignment,
)
from app.analysis import AnalysisWorkflowError, analyze_incident, get_latest_analysis
from app.config import get_settings
from app.database import async_session_factory, engine, get_session
from app.detection import scan_stalled_deals
from app.knowledge import search_knowledge, seed_operational_policies
from app.models import (
    AgentAuditEvent,
    ApprovalRequest,
    BottleneckIncident,
    Deal,
    KnowledgeDocument,
    MonitoringRun,
    MonitoringSettings,
    SalesOwnerCapacity,
    User,
)
from app.monitoring import ProactiveMonitoringService, iter_monitoring_runs
from app.outcomes import (
    OutcomeVerificationError,
    list_incident_outcomes,
    verify_incident_outcome,
)
from app.schemas import (
    AgentAnalysisResponse,
        ApprovalRequestResponse,
        ApprovalReviewRequest,
    AgentAnalysisStatusResponse,
    BottleneckIncidentDetailResponse,
    BottleneckIncidentResponse,
    DashboardSummary,
    DealResponse,
    FollowUpTaskResponse,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    LoginRequest,
    LoginResponse,
    MonitoringRunResponse,
    MonitoringSettingsResponse,
    MonitoringSettingsUpdate,
    MonitoringStatusResponse,
    IncidentOutcomeResponse,
    ReassignmentRequestCreate,
    SalesOwnerCapacityResponse,
    UserResponse,
    ZohoAuthorizationResponse,
    ZohoConnectionStatusResponse,
    ZohoConnectionTestResponse,
    ZohoDealResponse,
    ZohoDealSyncResponse,
    ZohoDisconnectResponse,
)
from app.security import create_access_token, decode_access_token, verify_password
from app.seed import seed_default_admin, seed_default_deals, seed_monitoring_settings
from app.zoho import (
    ZohoOAuthError,
    complete_authorization,
    consume_denied_authorization,
    create_authorization_url,
    disconnect,
    fetch_deals,
    get_connection,
    test_connection,
)
from app.zoho_sync import synchronize_zoho_deals

settings = get_settings()
monitoring_service = ProactiveMonitoringService(
    enabled=settings.proactive_monitoring_enabled,
    interval_seconds=settings.proactive_monitoring_interval_seconds,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await seed_default_admin()
    await seed_monitoring_settings()
    await seed_default_deals()
    async with async_session_factory() as session:
        await seed_operational_policies(session)
    await monitoring_service.start()
    try:
        yield
    finally:
        await monitoring_service.stop()
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user_id = decode_access_token(token)
    user = await session.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_admin_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


@app.get("/api/integrations/zoho/authorize", tags=["integrations"])
async def authorize_zoho(
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RedirectResponse:
    try:
        url = await create_authorization_url(session, admin)
    except ZohoOAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.post(
    "/api/integrations/zoho/authorize",
    response_model=ZohoAuthorizationResponse,
    tags=["integrations"],
)
async def start_zoho_authorization(
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ZohoAuthorizationResponse:
    try:
        url = await create_authorization_url(session, admin)
    except ZohoOAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ZohoAuthorizationResponse(authorization_url=url)


@app.get(
    "/api/integrations/zoho/callback",
    tags=["integrations"],
)
async def zoho_callback(
    state_value: Annotated[str, Query(alias="state", min_length=16)],
    session: Annotated[AsyncSession, Depends(get_session)],
    code: Annotated[str | None, Query(min_length=1)] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    return_url = f"{settings.frontend_url.rstrip('/')}/settings/integrations/zoho"
    try:
        if error is not None or code is None:
            await consume_denied_authorization(session, state=state_value)
            query = "zoho=error&reason=Authorization+was+not+approved"
        else:
            await complete_authorization(session, state=state_value, code=code)
            query = "zoho=connected"
    except ZohoOAuthError as oauth_error:
        from urllib.parse import urlencode

        query = urlencode({"zoho": "error", "reason": oauth_error.message})
    return RedirectResponse(url=f"{return_url}?{query}", status_code=status.HTTP_303_SEE_OTHER)


@app.get(
    "/api/integrations/zoho/status",
    response_model=ZohoConnectionStatusResponse,
    tags=["integrations"],
)
async def zoho_status(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ZohoConnectionStatusResponse:
    connection = await get_connection(session)
    synchronized_deals = await session.scalar(
        select(func.count(Deal.id)).where(Deal.source == "zoho")
    )
    last_sync = await session.scalar(
        select(AgentAuditEvent)
        .where(AgentAuditEvent.event_type == "ZOHO_DEAL_SYNC_COMPLETED")
        .order_by(AgentAuditEvent.created_at.desc())
        .limit(1)
    )
    sync_error = None
    if last_sync is not None:
        errors = last_sync.details.get("errors")
        if isinstance(errors, list) and errors:
            first_error = errors[0]
            if isinstance(first_error, dict) and isinstance(first_error.get("error"), str):
                sync_error = first_error["error"]
    adapter = "zoho" if settings.crm_adapter.casefold() == "zoho" else "local"
    if connection is None:
        return ZohoConnectionStatusResponse(
            connected=False,
            adapter=adapter,
            synchronized_deals=synchronized_deals or 0,
            last_sync_at=last_sync.created_at if last_sync else None,
            last_sync_status=last_sync.status if last_sync else None,
            last_sync_error=sync_error,
        )
    return ZohoConnectionStatusResponse(
        connected=True,
        adapter=adapter,
        api_domain=connection.api_domain,
        authorized_scopes=connection.authorized_scopes,
        connected_at=connection.connected_at,
        synchronized_deals=synchronized_deals or 0,
        last_sync_at=last_sync.created_at if last_sync else None,
        last_sync_status=last_sync.status if last_sync else None,
        last_sync_error=sync_error,
    )


@app.post(
    "/api/integrations/zoho/test",
    response_model=ZohoConnectionTestResponse,
    tags=["integrations"],
)
async def test_zoho_connection(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ZohoConnectionTestResponse:
    try:
        await test_connection(session)
    except ZohoOAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ZohoConnectionTestResponse(healthy=True, message="Zoho CRM connection is healthy")


@app.delete(
    "/api/integrations/zoho",
    response_model=ZohoDisconnectResponse,
    tags=["integrations"],
)
async def disconnect_zoho(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ZohoDisconnectResponse:
    revoked = await disconnect(session)
    message = "Zoho CRM disconnected" if revoked else "Zoho CRM disconnected locally"
    return ZohoDisconnectResponse(disconnected=True, message=message)


@app.get(
    "/api/integrations/zoho/deals",
    response_model=list[ZohoDealResponse],
    tags=["integrations"],
)
async def zoho_deals(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ZohoDealResponse]:
    try:
        deals = await fetch_deals(session)
    except ZohoOAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return [ZohoDealResponse.model_validate(deal, from_attributes=True) for deal in deals]


@app.post(
    "/api/integrations/zoho/sync/deals",
    response_model=ZohoDealSyncResponse,
    tags=["integrations"],
)
async def sync_zoho_deals(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ZohoDealSyncResponse:
    try:
        result = await synchronize_zoho_deals(session)
    except ZohoOAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ZohoDealSyncResponse.model_validate(result, from_attributes=True)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from error

    return {"status": "ok", "database": "velocity"}


@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(
    credentials: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    email = str(credentials.email).lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(user.password_hash, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token, expires_in = create_access_token(user.id)
    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse(email=user.email, is_admin=user.is_admin),
    )


@app.get("/dashboard/summary", response_model=DashboardSummary, tags=["dashboard"])
async def dashboard_summary(
    _: Annotated[User, Depends(get_current_user)],
) -> DashboardSummary:
    now = datetime.now(UTC)
    return DashboardSummary.model_validate(
        {
            "generated_at": now,
            "metrics": [
                {"label": "Pipeline value", "value": "$2.84M", "change": "+12.4%", "trend": "up"},
                {"label": "At-risk revenue", "value": "$426K", "change": "12 deals", "trend": "down"},
                {"label": "Protected this week", "value": "$284K", "change": "+18.7%", "trend": "up"},
                {"label": "Median response", "value": "2.4h", "change": "38m faster", "trend": "up"},
            ],
            "pipeline": [
                {"name": "Qualified", "value": 82, "amount": "$1.12M"},
                {"name": "Discovery", "value": 64, "amount": "$768K"},
                {"name": "Proposal", "value": 47, "amount": "$592K"},
                {"name": "Negotiation", "value": 31, "amount": "$358K"},
            ],
            "risks": [
                {"account": "Northstar Labs", "owner": "Maya Chen", "amount": "$128K", "risk": 91, "reason": "Approval blocked for 5 days", "severity": "critical"},
                {"account": "Acme Systems", "owner": "Liam Brooks", "amount": "$96K", "risk": 84, "reason": "No customer activity in 8 days", "severity": "high"},
                {"account": "Vertex Health", "owner": "Ava Patel", "amount": "$74K", "risk": 77, "reason": "Owner capacity above threshold", "severity": "high"},
                {"account": "Meridian Group", "owner": "Noah Garcia", "amount": "$52K", "risk": 66, "reason": "CRM sync retry pending", "severity": "medium"},
            ],
            "activity": [
                {"title": "Risk pattern detected", "detail": "5 enterprise deals share one approval bottleneck", "occurred_at": now - timedelta(minutes=12), "kind": "alert"},
                {"title": "Reassignment approved", "detail": "3 leads moved from Maya to Noah", "occurred_at": now - timedelta(minutes=47), "kind": "action"},
                {"title": "Zoho sync recovered", "detail": "184 delayed records synchronized", "occurred_at": now - timedelta(hours=2), "kind": "sync"},
            ],
            "owner_load": [
                {"name": "Maya Chen", "initials": "MC", "utilization": 94, "active_deals": 18},
                {"name": "Liam Brooks", "initials": "LB", "utilization": 78, "active_deals": 14},
                {"name": "Ava Patel", "initials": "AP", "utilization": 67, "active_deals": 11},
                {"name": "Noah Garcia", "initials": "NG", "utilization": 42, "active_deals": 8},
            ],
        }
    )


@app.get("/api/deals", response_model=list[DealResponse], tags=["deals"])
async def list_deals(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Deal]:
    deals = await session.scalars(select(Deal).order_by(Deal.created_at.desc()))
    return list(deals)


@app.get(
    "/api/knowledge/documents",
    response_model=list[KnowledgeDocumentResponse],
    tags=["knowledge"],
)
async def list_knowledge_documents(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[KnowledgeDocument]:
    documents = await session.scalars(
        select(KnowledgeDocument).order_by(KnowledgeDocument.title)
    )
    return list(documents)


@app.post(
    "/api/knowledge/search",
    response_model=list[KnowledgeSearchResult],
    tags=["knowledge"],
)
async def search_operational_knowledge(
    request: KnowledgeSearchRequest,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[KnowledgeSearchResult]:
    matches = await search_knowledge(
        session,
        request.query,
        request.incident_type,
        request.limit,
    )
    return [
        KnowledgeSearchResult(
            title=document.title,
            content=chunk.content,
            similarity=similarity,
            version=document.version,
            metadata=chunk.chunk_metadata,
        )
        for chunk, document, similarity in matches
    ]


@app.post(
    "/api/detection/scan",
    response_model=list[BottleneckIncidentResponse],
    tags=["detection"],
)
async def scan_detection(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BottleneckIncident]:
    return await scan_stalled_deals(session)


@app.get(
    "/api/monitoring/status",
    response_model=MonitoringStatusResponse,
    tags=["monitoring"],
)
async def monitoring_status(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MonitoringStatusResponse:
    last_run = await monitoring_service.latest_run(session)
    active_settings = await session.scalar(select(MonitoringSettings).limit(1))
    return MonitoringStatusResponse(
        enabled=(
            active_settings.monitoring_enabled
            if active_settings is not None
            else monitoring_service.enabled
        ),
        active=monitoring_service.active,
        interval_seconds=(
            active_settings.scan_interval_seconds
            if active_settings is not None
            else monitoring_service.interval_seconds
        ),
        cycle_running=monitoring_service.cycle_running,
        last_scan_at=last_run.completed_at if last_run is not None else None,
        next_scan_at=monitoring_service.next_scan_at,
        last_run=last_run,
    )


async def get_persisted_monitoring_settings(
    session: AsyncSession,
) -> MonitoringSettings:
    active_settings = await session.scalar(select(MonitoringSettings).limit(1))
    if active_settings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring settings have not been initialized",
        )
    return active_settings


@app.get(
    "/api/monitoring/settings",
    response_model=MonitoringSettingsResponse,
    tags=["monitoring"],
)
async def read_monitoring_settings(
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MonitoringSettings:
    return await get_persisted_monitoring_settings(session)


@app.put(
    "/api/monitoring/settings",
    response_model=MonitoringSettingsResponse,
    tags=["monitoring"],
)
async def update_monitoring_settings(
    update: MonitoringSettingsUpdate,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MonitoringSettings:
    active_settings = await get_persisted_monitoring_settings(session)
    old_values = {
        field: getattr(active_settings, field)
        for field in MonitoringSettingsUpdate.model_fields
    }
    for field, value in update.model_dump().items():
        setattr(active_settings, field, value)
    active_settings.updated_by = admin.id
    session.add(
        AgentAuditEvent(
            event_type="MONITORING_SETTINGS_UPDATED",
            status="COMPLETED",
            details={
                "updated_by": str(admin.id),
                "old": old_values,
                "new": update.model_dump(),
            },
        )
    )
    await session.commit()
    await session.refresh(active_settings)
    monitoring_service.apply_settings(active_settings)
    return active_settings


@app.get(
    "/api/monitoring/runs",
    response_model=list[MonitoringRunResponse],
    tags=["monitoring"],
)
async def monitoring_runs(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MonitoringRun]:
    return [run async for run in iter_monitoring_runs(session)]


@app.get(
    "/api/incidents",
    response_model=list[BottleneckIncidentResponse],
    tags=["incidents"],
)
async def list_incidents(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BottleneckIncident]:
    incidents = await session.scalars(
        select(BottleneckIncident).order_by(BottleneckIncident.risk_score.desc())
    )
    return list(incidents)


@app.get(
    "/api/incidents/{incident_id}",
    response_model=BottleneckIncidentDetailResponse,
    tags=["incidents"],
)
async def get_incident(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BottleneckIncidentDetailResponse:
    incident = await session.get(BottleneckIncident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    deal = await session.get(Deal, incident.deal_id) if incident.deal_id is not None else None
    owner = (
        await session.get(SalesOwnerCapacity, incident.owner_capacity_id)
        if incident.owner_capacity_id is not None
        else None
    )
    if deal is None and owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Affected subject not found",
        )
    actions = await list_incident_actions(session, incident_id)
    approvals = [
        approval
        for approval in await list_approval_requests(session)
        if approval.incident_id == incident_id
    ]
    outcomes = await list_incident_outcomes(session, incident_id)
    timeline = list(
        await session.scalars(
            select(AgentAuditEvent)
            .where(AgentAuditEvent.incident_id == incident_id)
            .order_by(AgentAuditEvent.created_at.desc())
        )
    )
    return BottleneckIncidentDetailResponse.model_validate(
        {
            "id": incident.id,
            "deal_id": incident.deal_id,
            "owner_capacity_id": incident.owner_capacity_id,
            "incident_type": incident.incident_type,
            "title": incident.title,
            "severity": incident.severity,
            "risk_score": incident.risk_score,
            "evidence": incident.evidence,
            "status": incident.status,
            "analysis_state": incident.analysis_state,
            "detected_at": incident.detected_at,
            "updated_at": incident.updated_at,
            "affected_deal": deal,
            "affected_owner": owner,
            "actions": actions,
            "approvals": approvals,
            "outcomes": outcomes,
            "timeline": timeline,
        }
    )


@app.get(
    "/api/incidents/{incident_id}/outcomes",
    response_model=list[IncidentOutcomeResponse],
    tags=["incidents"],
)
async def get_incident_outcomes(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[IncidentOutcomeResponse]:
    if await session.get(BottleneckIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return [
        IncidentOutcomeResponse.model_validate(outcome)
        for outcome in await list_incident_outcomes(session, incident_id)
    ]


@app.post(
    "/api/incidents/{incident_id}/verify-outcome",
    response_model=IncidentOutcomeResponse,
    tags=["incidents"],
)
async def verify_outcome_now(
    incident_id: UUID,
    _: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOutcomeResponse:
    try:
        outcome = await verify_incident_outcome(session, incident_id, force=True)
    except OutcomeVerificationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return IncidentOutcomeResponse.model_validate(outcome)


@app.post(
    "/api/incidents/{incident_id}/analyze",
    response_model=AgentAnalysisResponse,
)
async def create_incident_analysis(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentAnalysisResponse:
    try:
        analysis = await analyze_incident(session, incident_id, trigger="MANUAL")
    except AnalysisWorkflowError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    if analysis is None:
        raise HTTPException(status_code=409, detail="Analysis is already current")
    return AgentAnalysisResponse.model_validate(analysis)


@app.get(
    "/api/incidents/{incident_id}/analysis",
    response_model=AgentAnalysisStatusResponse,
)
async def get_incident_analysis(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentAnalysisStatusResponse:
    incident = await session.get(BottleneckIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    analysis = await get_latest_analysis(session, incident_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    if analysis.status == "FAILED":
        from app.schemas import FailedAgentAnalysisResponse

        return FailedAgentAnalysisResponse.model_validate(analysis)
    if analysis.status == "RUNNING":
        from app.schemas import RunningAgentAnalysisResponse

        return RunningAgentAnalysisResponse.model_validate(analysis)
    return AgentAnalysisResponse.model_validate(analysis)


@app.post(
    "/api/incidents/{incident_id}/actions/create-follow-up",
    response_model=FollowUpTaskResponse,
)
async def execute_create_follow_up(
    incident_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FollowUpTaskResponse:
    try:
        active_settings = await get_persisted_monitoring_settings(session)
        task = await create_follow_up_task(
            session,
            incident_id,
            user.id,
            due_hours=active_settings.follow_up_due_hours,
        )
    except ActionExecutionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return FollowUpTaskResponse.model_validate(task)


@app.get(
    "/api/incidents/{incident_id}/actions/create-follow-up",
    response_model=FollowUpTaskResponse,
)
async def get_created_follow_up(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FollowUpTaskResponse:
    incident = await session.get(BottleneckIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    task = await get_follow_up_task(session, incident_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up task not found")
    return FollowUpTaskResponse.model_validate(task)


@app.get(
    "/api/incidents/{incident_id}/actions",
    response_model=list[FollowUpTaskResponse],
)
async def get_incident_actions(
    incident_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[FollowUpTaskResponse]:
    incident = await session.get(BottleneckIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return [
        FollowUpTaskResponse.model_validate(task)
        for task in await list_incident_actions(session, incident_id)
    ]


@app.post(
    "/api/incidents/{incident_id}/actions/request-reassignment",
    response_model=ApprovalRequestResponse,
    tags=["approvals"],
)
async def create_reassignment_request(
    incident_id: UUID,
    request: ReassignmentRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApprovalRequestResponse:
    try:
        approval = await request_deal_reassignment(
            session, incident_id, user.id, proposed_owner=request.proposed_owner
        )
    except ActionExecutionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ApprovalRequestResponse.model_validate(approval)


@app.get("/api/approvals", response_model=list[ApprovalRequestResponse], tags=["approvals"])
async def read_approvals(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ApprovalRequestResponse]:
    return [ApprovalRequestResponse.model_validate(item) for item in await list_approval_requests(session)]


@app.get("/api/approvals/owners", response_model=list[SalesOwnerCapacityResponse], tags=["approvals"])
async def read_owner_capacities(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SalesOwnerCapacityResponse]:
    return [SalesOwnerCapacityResponse.model_validate(item) for item in await list_owner_capacities(session)]


@app.get("/api/approvals/{approval_id}", response_model=ApprovalRequestResponse, tags=["approvals"])
async def read_approval(
    approval_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApprovalRequestResponse:
    approval = await get_approval_request(session, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalRequestResponse.model_validate(approval)


async def _review_reassignment(
    approval_id: UUID,
    admin: User,
    session: AsyncSession,
    decision: str,
    comment: str | None,
) -> ApprovalRequestResponse:
    try:
        approval = await review_deal_reassignment(
            session, approval_id, admin.id, decision=decision, comment=comment
        )
    except ActionExecutionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ApprovalRequestResponse.model_validate(approval)


@app.post("/api/approvals/{approval_id}/approve", response_model=ApprovalRequestResponse, tags=["approvals"])
async def approve_reassignment(
    approval_id: UUID,
    review: ApprovalReviewRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApprovalRequestResponse:
    return await _review_reassignment(approval_id, admin, session, "APPROVE", review.comment)


@app.post("/api/approvals/{approval_id}/reject", response_model=ApprovalRequestResponse, tags=["approvals"])
async def reject_reassignment(
    approval_id: UUID,
    review: ApprovalReviewRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApprovalRequestResponse:
    if not review.comment or not review.comment.strip():
        raise HTTPException(status_code=422, detail="A review comment is required for rejection")
    return await _review_reassignment(approval_id, admin, session, "REJECT", review.comment)