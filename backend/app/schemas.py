from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    email: EmailStr
    is_admin: bool


class ZohoConnectionStatusResponse(BaseModel):
    connected: bool
    adapter: Literal["local", "zoho"] = "local"
    api_domain: str | None = None
    authorized_scopes: str | None = None
    connected_at: datetime | None = None
    synchronized_deals: int = 0
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None


class ZohoAuthorizationResponse(BaseModel):
    authorization_url: str


class ZohoConnectionSuccessResponse(BaseModel):
    connected: bool


class ZohoConnectionTestResponse(BaseModel):
    healthy: bool
    message: str


class ZohoDisconnectResponse(BaseModel):
    disconnected: bool
    message: str


class ZohoDealResponse(BaseModel):
    zoho_record_id: str
    deal_name: str | None
    stage: str | None
    amount: Decimal | None
    owner: str | None
    closing_date: str | None
    created_time: datetime | None
    modified_time: datetime | None


class ZohoDealSyncResponse(BaseModel):
    fetched: int
    created: int
    updated: int
    unchanged: int
    failed: int
    errors: list[dict[str, str]]
    started_at: datetime
    completed_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zoho_record_id: str | None
    source: str
    zoho_modified_at: datetime | None
    last_synced_at: datetime | None
    name: str
    value: Decimal
    stage: str
    owner_name: str
    stage_entered_at: datetime
    last_activity_at: datetime
    next_follow_up_at: datetime | None
    status: str
    created_at: datetime


class BottleneckIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID | None
    owner_capacity_id: UUID | None
    incident_type: str
    title: str
    severity: Literal["low", "medium", "high", "critical"]
    risk_score: int
    evidence: dict[str, object]
    status: str
    analysis_state: Literal[
        "PENDING_ANALYSIS", "ANALYZING", "ANALYZED", "ANALYSIS_FAILED"
    ]
    detected_at: datetime
    updated_at: datetime


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    document_type: str
    version: str
    content: str
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    incident_type: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResult(BaseModel):
    title: str
    content: str
    similarity: float
    version: str
    metadata: dict[str, object]


ActionType = Literal[
    "CREATE_FOLLOW_UP",
    "SEND_MANAGER_ALERT",
    "REQUEST_REASSIGNMENT",
    "REQUEST_HUMAN_REVIEW",
]


class RootCauseAnalysisContent(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    root_cause: str = Field(min_length=1, max_length=2000)
    supporting_evidence: list[str] = Field(min_length=1, max_length=10)
    risk_explanation: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)
    action_type: ActionType
    confidence: float = Field(ge=0, le=1)
    approval_required: bool
    policy_references: list[str] = Field(default_factory=list, max_length=10)
    expected_outcome: str = Field(min_length=1, max_length=2000)


class AgentAnalysisResponse(RootCauseAnalysisContent):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    model_name: str
    status: Literal["COMPLETED"]
    error_message: None = None
    created_at: datetime
    updated_at: datetime


class FailedAgentAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    model_name: str
    status: Literal["FAILED"]
    error_message: str
    created_at: datetime
    updated_at: datetime


class RunningAgentAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    model_name: str
    status: Literal["RUNNING"]
    error_message: None = None
    created_at: datetime
    updated_at: datetime


AgentAnalysisStatusResponse = (
    AgentAnalysisResponse | FailedAgentAnalysisResponse | RunningAgentAnalysisResponse
)


class FollowUpTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    incident_id: UUID
    agent_analysis_id: UUID
    title: str
    description: str
    assigned_to: str
    due_at: datetime
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED", "FAILED"]
    execution_source: Literal["MANUAL", "AUTOMATIC"]
    execution_result: dict[str, object]
    created_by: UUID | None
    created_at: datetime
    completed_at: datetime | None


class ReassignmentRequestCreate(BaseModel):
    proposed_owner: str | None = Field(default=None, min_length=1, max_length=120)


class ApprovalReviewRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    agent_analysis_id: UUID
    action_type: Literal["REQUEST_REASSIGNMENT"]
    requested_by: UUID
    current_owner: str
    proposed_owner: str
    reason: str
    expected_outcome: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED", "EXECUTION_FAILED"]
    reviewed_by: UUID | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None
    expires_at: datetime


class SalesOwnerCapacityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str
    active_deals: int
    max_active_deals: int
    is_active: bool


class AgentAuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID | None
    analysis_id: UUID | None
    monitoring_run_id: UUID | None
    event_type: str
    status: str
    details: dict[str, object]
    created_at: datetime


class IncidentOutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    action_type: str
    action_id: UUID
    verification_status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    previous_risk_score: int
    current_risk_score: int | None
    verification_evidence: dict[str, object]
    outcome: Literal[
        "SUCCESSFUL",
        "PARTIALLY_SUCCESSFUL",
        "FAILED",
        "AWAITING_EVIDENCE",
        "RECURRED",
    ]
    verified_at: datetime | None
    next_check_at: datetime | None
    created_at: datetime


class BottleneckIncidentDetailResponse(BottleneckIncidentResponse):
    affected_deal: DealResponse | None
    affected_owner: SalesOwnerCapacityResponse | None
    actions: list[FollowUpTaskResponse]
    approvals: list[ApprovalRequestResponse]
    outcomes: list[IncidentOutcomeResponse]
    timeline: list[AgentAuditEventResponse]


class MonitoringRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    completed_at: datetime | None
    deals_scanned: int
    incidents_created: int
    incidents_updated: int
    errors_encountered: int
    status: Literal["RUNNING", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]


class MonitoringStatusResponse(BaseModel):
    enabled: bool
    active: bool
    interval_seconds: int
    cycle_running: bool
    last_scan_at: datetime | None
    next_scan_at: datetime | None
    last_run: MonitoringRunResponse | None


class MonitoringSettingsUpdate(BaseModel):
    monitoring_enabled: bool
    scan_interval_seconds: int = Field(ge=5, le=3600)
    stage_sla_hours: int = Field(ge=1, le=8760)
    inactivity_threshold_hours: int = Field(ge=1, le=8760)
    overdue_follow_up_enabled: bool
    owner_overload_enabled: bool = True
    owner_max_active_deals: int = Field(default=18, ge=1, le=10000)
    owner_max_high_risk_deals: int = Field(default=5, ge=1, le=10000)
    owner_max_overdue_follow_ups: int = Field(default=5, ge=1, le=10000)
    owner_max_pipeline_value: Decimal | None = Field(default=None, gt=0)
    automatic_rca_enabled: bool
    automatic_rca_min_risk_score: int = Field(ge=0, le=100)
    automatic_safe_actions_enabled: bool
    follow_up_due_hours: int = Field(ge=1, le=720)
    high_impact_actions_disabled: bool
    outcome_verification_enabled: bool = True
    outcome_check_delay_minutes: int = Field(default=60, ge=1, le=10080)
    maximum_outcome_checks: int = Field(default=3, ge=1, le=20)
    resolution_risk_threshold: int = Field(default=20, ge=0, le=100)


class MonitoringSettingsResponse(MonitoringSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime


class Metric(BaseModel):
    label: str
    value: str
    change: str
    trend: Literal["up", "down", "neutral"]


class PipelineStage(BaseModel):
    name: str
    value: int
    amount: str


class RiskItem(BaseModel):
    account: str
    owner: str
    amount: str
    risk: int
    reason: str
    severity: Literal["critical", "high", "medium"]


class ActivityItem(BaseModel):
    title: str
    detail: str
    occurred_at: datetime
    kind: Literal["alert", "action", "sync"]


class OwnerLoad(BaseModel):
    name: str
    initials: str
    utilization: int
    active_deals: int


class DashboardSummary(BaseModel):
    generated_at: datetime
    metrics: list[Metric]
    pipeline: list[PipelineStage]
    risks: list[RiskItem]
    activity: list[ActivityItem]
    owner_load: list[OwnerLoad]