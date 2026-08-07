from datetime import datetime
from uuid import UUID, uuid4

from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    zoho_record_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    source: Mapped[str] = mapped_column(String(20), default="local", server_default="local")
    zoho_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stage: Mapped[str] = mapped_column(String(50), index=True)
    owner_name: Mapped[str] = mapped_column(String(120), index=True)
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BottleneckIncident(Base):
    __tablename__ = "bottleneck_incidents"
    __table_args__ = (
        Index(
            "uq_open_stalled_incident_per_deal",
            "deal_id",
            "incident_type",
            unique=True,
            postgresql_where=text("status = 'open' AND deal_id IS NOT NULL"),
        ),
        Index(
            "uq_open_owner_incident",
            "owner_capacity_id",
            "incident_type",
            unique=True,
            postgresql_where=text("status = 'open' AND owner_capacity_id IS NOT NULL"),
        ),
        CheckConstraint(
            "num_nonnulls(deal_id, owner_capacity_id) = 1",
            name="ck_incident_exactly_one_subject",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    deal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_capacity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sales_owner_capacities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    incident_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), index=True)
    analysis_state: Mapped[str] = mapped_column(
        String(30), default="PENDING_ANALYSIS", server_default="PENDING_ANALYSIS", index=True
    )
    analysis_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("document_type", "version", name="uq_knowledge_document_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_index"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSON)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentAnalysis(Base):
    __tablename__ = "agent_analyses"
    __table_args__ = (
        Index(
            "uq_active_analysis_per_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("bottleneck_incidents.id", ondelete="CASCADE"), index=True
    )
    model_name: Mapped[str] = mapped_column(String(100))
    trigger: Mapped[str] = mapped_column(String(20), default="MANUAL")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_evidence: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    risk_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    approval_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    policy_references: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deals_scanned: Mapped[int] = mapped_column(Integer, default=0)
    incidents_created: Mapped[int] = mapped_column(Integer, default=0)
    incidents_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_encountered: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)


class MonitoringSettings(Base):
    __tablename__ = "monitoring_settings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean)
    scan_interval_seconds: Mapped[int] = mapped_column(Integer)
    stage_sla_hours: Mapped[int] = mapped_column(Integer)
    inactivity_threshold_hours: Mapped[int] = mapped_column(Integer)
    overdue_follow_up_enabled: Mapped[bool] = mapped_column(Boolean)
    owner_overload_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    owner_max_active_deals: Mapped[int] = mapped_column(
        Integer, default=18, server_default="18"
    )
    owner_max_high_risk_deals: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5"
    )
    owner_max_overdue_follow_ups: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5"
    )
    owner_max_pipeline_value: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 2), nullable=True
    )
    automatic_rca_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    automatic_rca_min_risk_score: Mapped[int] = mapped_column(
        Integer, default=80, server_default="80"
    )
    automatic_safe_actions_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    follow_up_due_hours: Mapped[int] = mapped_column(
        Integer, default=24, server_default="24"
    )
    high_impact_actions_disabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    outcome_verification_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    outcome_check_delay_minutes: Mapped[int] = mapped_column(
        Integer, default=60, server_default="60"
    )
    maximum_outcome_checks: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3"
    )
    resolution_risk_threshold: Mapped[int] = mapped_column(
        Integer, default=20, server_default="20"
    )
    updated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentAuditEvent(Base):
    __tablename__ = "agent_audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bottleneck_incidents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    monitoring_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        Index(
            "uq_follow_up_task_active_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'IN_PROGRESS')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    deal_id: Mapped[UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("bottleneck_incidents.id", ondelete="CASCADE"), index=True
    )
    agent_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_analyses.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str] = mapped_column(String(120), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    execution_source: Mapped[str] = mapped_column(String(20), index=True)
    execution_result: Mapped[dict[str, object]] = mapped_column(JSON)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SalesOwnerCapacity(Base):
    __tablename__ = "sales_owner_capacities"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    active_deals: Mapped[int] = mapped_column(Integer, default=0)
    max_active_deals: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index(
            "uq_pending_reassignment_per_incident",
            "incident_id",
            unique=True,
            postgresql_where=text(
                "status = 'PENDING' AND action_type = 'REQUEST_REASSIGNMENT'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("bottleneck_incidents.id", ondelete="CASCADE"), index=True
    )
    agent_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_analyses.id", ondelete="RESTRICT"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    current_owner: Mapped[str] = mapped_column(String(120))
    proposed_owner: Mapped[str] = mapped_column(String(120), index=True)
    reason: Mapped[str] = mapped_column(Text)
    expected_outcome: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IncidentOutcome(Base):
    __tablename__ = "incident_outcomes"
    __table_args__ = (
        Index(
            "uq_active_outcome_check_per_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("verification_status IN ('PENDING', 'RUNNING')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("bottleneck_incidents.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    action_id: Mapped[UUID] = mapped_column(index=True)
    verification_status: Mapped[str] = mapped_column(String(20), index=True)
    previous_risk_score: Mapped[int] = mapped_column(Integer)
    current_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_evidence: Mapped[dict[str, object]] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(30), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ZohoOAuthState(Base):
    __tablename__ = "zoho_oauth_states"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ZohoConnection(Base):
    __tablename__ = "zoho_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    api_domain: Mapped[str] = mapped_column(String(255))
    authorized_scopes: Mapped[str] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connected_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )