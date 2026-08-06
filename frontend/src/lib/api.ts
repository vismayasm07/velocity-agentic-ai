export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: { email: string; is_admin: boolean };
};

export type Deal = {
  id: string;
  name: string;
  value: string;
  stage: string;
  owner_name: string;
  stage_entered_at: string;
  last_activity_at: string;
  next_follow_up_at: string | null;
  status: string;
  created_at: string;
};

export type BottleneckIncident = {
  id: string;
  deal_id: string | null;
  owner_capacity_id: string | null;
  incident_type: string;
  title: string;
  severity: "low" | "medium" | "high" | "critical";
  risk_score: number;
  evidence: Record<string, unknown>;
  status: string;
  analysis_state: "PENDING_ANALYSIS" | "ANALYZING" | "ANALYZED" | "ANALYSIS_FAILED";
  detected_at: string;
  updated_at: string;
};

export type BottleneckIncidentDetail = BottleneckIncident & {
  affected_deal: Deal | null;
  affected_owner: SalesOwnerCapacity | null;
  actions: FollowUpTask[];
  approvals: ApprovalRequest[];
  outcomes: IncidentOutcome[];
  timeline: AgentAuditEvent[];
};

export type IncidentOutcome = {
  id: string;
  incident_id: string;
  action_type: string;
  action_id: string;
  verification_status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  previous_risk_score: number;
  current_risk_score: number | null;
  verification_evidence: Record<string, unknown>;
  outcome: "SUCCESSFUL" | "PARTIALLY_SUCCESSFUL" | "FAILED" | "AWAITING_EVIDENCE" | "RECURRED";
  verified_at: string | null;
  next_check_at: string | null;
  created_at: string;
};

export type AnalysisActionType =
  | "CREATE_FOLLOW_UP"
  | "SEND_MANAGER_ALERT"
  | "REQUEST_REASSIGNMENT"
  | "REQUEST_HUMAN_REVIEW";

type AnalysisRecord = {
  id: string;
  incident_id: string;
  model_name: string;
  created_at: string;
  updated_at: string;
};

export type CompletedAgentAnalysis = AnalysisRecord & {
  status: "COMPLETED";
  error_message: null;
  summary: string;
  root_cause: string;
  supporting_evidence: string[];
  risk_explanation: string;
  recommended_action: string;
  action_type: AnalysisActionType;
  confidence: number;
  approval_required: boolean;
  policy_references: string[];
  expected_outcome: string;
};

export type FailedAgentAnalysis = AnalysisRecord & {
  status: "FAILED";
  error_message: string;
};

export type RunningAgentAnalysis = AnalysisRecord & {
  status: "RUNNING";
  error_message: null;
};

export type AgentAnalysis = CompletedAgentAnalysis | FailedAgentAnalysis | RunningAgentAnalysis;

export type FollowUpTask = {
  id: string;
  deal_id: string;
  incident_id: string;
  agent_analysis_id: string;
  title: string;
  description: string;
  assigned_to: string;
  due_at: string;
  status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED" | "FAILED";
  execution_source: "MANUAL" | "AUTOMATIC";
  execution_result: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "EXECUTED" | "EXECUTION_FAILED";

export type ApprovalRequest = {
  id: string;
  incident_id: string;
  agent_analysis_id: string;
  action_type: "REQUEST_REASSIGNMENT";
  requested_by: string;
  current_owner: string;
  proposed_owner: string;
  reason: string;
  expected_outcome: string;
  status: ApprovalStatus;
  reviewed_by: string | null;
  review_comment: string | null;
  created_at: string;
  reviewed_at: string | null;
  expires_at: string;
};

export type SalesOwnerCapacity = {
  id: string;
  owner_name: string;
  active_deals: number;
  max_active_deals: number;
  is_active: boolean;
};

export type AgentAuditEvent = {
  id: string;
  incident_id: string | null;
  analysis_id: string | null;
  monitoring_run_id: string | null;
  event_type: string;
  status: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type MonitoringRun = {
  id: string;
  started_at: string;
  completed_at: string | null;
  deals_scanned: number;
  incidents_created: number;
  incidents_updated: number;
  errors_encountered: number;
  status: "RUNNING" | "COMPLETED" | "COMPLETED_WITH_ERRORS" | "FAILED";
};

export type MonitoringStatus = {
  enabled: boolean;
  active: boolean;
  interval_seconds: number;
  cycle_running: boolean;
  last_scan_at: string | null;
  next_scan_at: string | null;
  last_run: MonitoringRun | null;
};

export type MonitoringSettingsUpdate = {
  monitoring_enabled: boolean;
  scan_interval_seconds: number;
  stage_sla_hours: number;
  inactivity_threshold_hours: number;
  overdue_follow_up_enabled: boolean;
  owner_overload_enabled: boolean;
  owner_max_active_deals: number;
  owner_max_high_risk_deals: number;
  owner_max_overdue_follow_ups: number;
  owner_max_pipeline_value: string | null;
  automatic_rca_enabled: boolean;
  automatic_rca_min_risk_score: number;
  automatic_safe_actions_enabled: boolean;
  follow_up_due_hours: number;
  high_impact_actions_disabled: boolean;
  outcome_verification_enabled: boolean;
  outcome_check_delay_minutes: number;
  maximum_outcome_checks: number;
  resolution_risk_threshold: number;
};

export type MonitoringSettings = MonitoringSettingsUpdate & {
  id: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type ZohoConnectionStatus = {
  connected: boolean;
  adapter: "local" | "zoho";
  api_domain: string | null;
  authorized_scopes: string | null;
  connected_at: string | null;
  synchronized_deals: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
};

export type ZohoDealSyncResult = {
  fetched: number;
  created: number;
  updated: number;
  unchanged: number;
  failed: number;
  errors: Array<{ deal_id?: string; error: string }>;
  started_at: string;
  completed_at: string;
};

export type DashboardSummary = {
  generated_at: string;
  metrics: Array<{ label: string; value: string; change: string; trend: "up" | "down" | "neutral" }>;
  pipeline: Array<{ name: string; value: number; amount: string }>;
  risks: Array<{ account: string; owner: string; amount: string; risk: number; reason: string; severity: "critical" | "high" | "medium" }>;
  activity: Array<{ title: string; detail: string; occurred_at: string; kind: "alert" | "action" | "sync" }>;
  owner_load: Array<{ name: string; initials: string; utilization: number; active_deals: number }>;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unable to reach Velocity" }));
    throw new ApiError(error.detail ?? "Request failed", response.status);
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export function login(email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function getDashboardSummary(token: string) {
  return request<DashboardSummary>("/dashboard/summary", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getDeals(token: string) {
  return request<Deal[]>("/api/deals", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getIncidents(token: string) {
  return request<BottleneckIncident[]>("/api/incidents", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function scanForBottlenecks(token: string) {
  return request<BottleneckIncident[]>("/api/detection/scan", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getIncident(token: string, incidentId: string) {
  return request<BottleneckIncidentDetail>(`/api/incidents/${incidentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getIncidentAnalysis(token: string, incidentId: string) {
  return request<AgentAnalysis>(`/api/incidents/${incidentId}/analysis`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function analyzeIncident(token: string, incidentId: string) {
  return request<CompletedAgentAnalysis>(`/api/incidents/${incidentId}/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getFollowUpTask(token: string, incidentId: string) {
  return request<FollowUpTask>(`/api/incidents/${incidentId}/actions/create-follow-up`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function createFollowUpTask(token: string, incidentId: string) {
  return request<FollowUpTask>(`/api/incidents/${incidentId}/actions/create-follow-up`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMonitoringStatus(token: string) {
  return request<MonitoringStatus>("/api/monitoring/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMonitoringRuns(token: string) {
  return request<MonitoringRun[]>("/api/monitoring/runs", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMonitoringSettings(token: string) {
  return request<MonitoringSettings>("/api/monitoring/settings", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function updateMonitoringSettings(token: string, settings: MonitoringSettingsUpdate) {
  return request<MonitoringSettings>("/api/monitoring/settings", {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(settings),
  });
}

export function getIncidentActions(token: string, incidentId: string) {
  return request<FollowUpTask[]>(`/api/incidents/${incidentId}/actions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getApprovals(token: string) {
  return request<ApprovalRequest[]>("/api/approvals", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getApproval(token: string, approvalId: string) {
  return request<ApprovalRequest>(`/api/approvals/${approvalId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getOwnerCapacities(token: string) {
  return request<SalesOwnerCapacity[]>("/api/approvals/owners", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function requestReassignment(token: string, incidentId: string, proposedOwner: string) {
  return request<ApprovalRequest>(`/api/incidents/${incidentId}/actions/request-reassignment`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ proposed_owner: proposedOwner }),
  });
}

export function reviewApproval(
  token: string,
  approvalId: string,
  decision: "approve" | "reject",
  comment: string,
) {
  return request<ApprovalRequest>(`/api/approvals/${approvalId}/${decision}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ comment }),
  });
}

export function getIncidentOutcomes(token: string, incidentId: string) {
  return request<IncidentOutcome[]>(`/api/incidents/${incidentId}/outcomes`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function verifyIncidentOutcome(token: string, incidentId: string) {
  return request<IncidentOutcome>(`/api/incidents/${incidentId}/verify-outcome`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getZohoStatus(token: string) {
  return request<ZohoConnectionStatus>("/api/integrations/zoho/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function beginZohoAuthorization(token: string) {
  return request<{ authorization_url: string }>("/api/integrations/zoho/authorize", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function testZohoConnection(token: string) {
  return request<{ healthy: boolean; message: string }>("/api/integrations/zoho/test", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function syncZohoDeals(token: string) {
  return request<ZohoDealSyncResult>("/api/integrations/zoho/sync/deals", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function disconnectZoho(token: string) {
  return request<{ disconnected: boolean; message: string }>("/api/integrations/zoho", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}