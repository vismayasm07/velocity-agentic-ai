"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  Activity, AlertTriangle, ArrowLeft, BriefcaseBusiness, CalendarClock, CalendarPlus,
  BrainCircuit, CheckCircle2, CircleDollarSign, Clock3, LoaderCircle, Radar,
  RefreshCw, ShieldCheck, UserRound, Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditTimeline } from "@/components/audit-timeline";
import {
  AgentAnalysis, analyzeIncident, ApiError, BottleneckIncident,
  BottleneckIncidentDetail, createFollowUpTask, FollowUpTask,
  getIncident, getIncidentAnalysis, getOwnerCapacities, requestReassignment,
  SalesOwnerCapacity, verifyIncidentOutcome,
} from "@/lib/api";

type StoredUser = { email: string; is_admin: boolean };

function getStoredUser(): StoredUser | null {
  const value = localStorage.getItem("velocity_user");
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed && typeof parsed === "object" && "email" in parsed && "is_admin" in parsed) {
      return parsed as StoredUser;
    }
  } catch {
    localStorage.removeItem("velocity_user");
  }
  return null;
}

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const severityStyles: Record<BottleneckIncident["severity"], string> = {
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  high: "border-orange-200 bg-orange-50 text-orange-800",
  critical: "border-red-200 bg-red-50 text-red-700",
};

type RiskFactor = {
  days?: number;
  threshold_days?: number;
  points?: number;
  triggered?: boolean;
};

function formatDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }) : "Not scheduled";
}

function readFactor(evidence: Record<string, unknown>, key: string): RiskFactor {
  const value = evidence[key];
  return value !== null && typeof value === "object" ? value as RiskFactor : {};
}

function LoadingIncident() {
  return <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 py-8 sm:px-6 lg:grid-cols-3 lg:px-8">{Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-44 rounded-lg" />)}</div>;
}

function OwnerIncidentDetails({
  incident,
  analysis,
  analysisError,
  isAnalyzing,
  onAnalyze,
}: {
  incident: BottleneckIncidentDetail;
  analysis: AgentAnalysis | null;
  analysisError: string;
  isAnalyzing: boolean;
  onAnalyze: () => void;
}) {
  const owner = incident.affected_owner;
  const factors = [
    ["active_deals", "Active deals"],
    ["high_risk_deals", "High-risk deals"],
    ["overdue_follow_ups", "Overdue follow-ups"],
    ["pipeline_value", "Pipeline value"],
  ] as const;
  const readWorkloadFactor = (key: string) => {
    const value = incident.evidence[key];
    return value && typeof value === "object" ? value as Record<string, unknown> : {};
  };

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8"><Button asChild variant="ghost" size="sm"><Link href="/dashboard"><ArrowLeft /> Dashboard</Link></Button><div className="flex items-center gap-2"><Badge variant={incident.status === "open" ? "secondary" : "outline"}>{incident.status}</Badge><Badge variant="outline" className={severityStyles[incident.severity]}>{incident.severity}</Badge></div></div></header>
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-9 lg:px-8">
      <section className="border-b border-border pb-7"><div className="flex items-center gap-2 text-sm font-medium text-primary"><Users className="size-4" /> Owner workload incident</div><h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{incident.title}</h1><p className="mt-3 text-sm text-muted-foreground">Detected {formatDateTime(incident.detected_at)} · ID {incident.id}</p></section>
      <section className="mt-6 grid gap-4 md:grid-cols-3">
        <Card className="shadow-none"><CardHeader><CardDescription>Affected owner</CardDescription><CardTitle>{owner?.owner_name ?? "Unknown owner"}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">{owner?.is_active ? "Active sales owner" : "Inactive sales owner"}</p></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Risk score</CardDescription><CardTitle className="text-3xl">{incident.risk_score}<span className="text-base font-normal text-muted-foreground"> / 100</span></CardTitle></CardHeader><CardContent><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary" style={{ width: `${incident.risk_score}%` }} /></div></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Status</CardDescription><CardTitle className="capitalize">{incident.status}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">Last evaluated {formatDateTime(incident.updated_at)}</p></CardContent></Card>
      </section>
      <section className="mt-6"><h2 className="text-lg font-semibold">Workload breakdown</h2><p className="mt-1 text-sm text-muted-foreground">Values and thresholds captured by the deterministic detector.</p><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{factors.map(([key, label]) => { const factor = readWorkloadFactor(key); const value = factor.value ?? 0; const threshold = factor.threshold ?? "Disabled"; return <Card key={key} className="shadow-none"><CardHeader><CardDescription>{label}</CardDescription><CardTitle>{key === "pipeline_value" ? currencyFormatter.format(Number(value)) : String(value)}</CardTitle></CardHeader><CardContent className="flex items-center justify-between gap-2"><span className="text-xs text-muted-foreground">Threshold {key === "pipeline_value" && threshold !== "Disabled" ? currencyFormatter.format(Number(threshold)) : String(threshold)}</span><Badge variant={factor.triggered === true ? "secondary" : "outline"}>{String(factor.points ?? 0)} points</Badge></CardContent></Card>; })}</div></section>
      <section className="mt-8 border-y border-border py-7"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2 text-sm font-medium text-primary"><BrainCircuit className="size-4" /> Root cause analysis</div><h2 className="mt-2 text-xl font-semibold">Grounded workload assessment</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">Gemini may recommend controlled manager review, while deterministic scans remain authoritative for resolution.</p></div><Button onClick={onAnalyze} disabled={isAnalyzing || incident.analysis_state === "ANALYZING"}>{isAnalyzing ? <LoaderCircle className="animate-spin" /> : <BrainCircuit />}{isAnalyzing ? "Analyzing" : analysis?.status === "COMPLETED" ? "Analyze again" : "Analyze with AI"}</Button></div>
        {analysisError && <div role="alert" className="mt-5 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{analysisError}</div>}
        {analysis?.status === "COMPLETED" && <div className="mt-6 grid gap-6 lg:grid-cols-2"><div className="lg:col-span-2"><p className="text-xs font-medium uppercase text-muted-foreground">Summary</p><p className="mt-2 leading-7">{analysis.summary}</p></div><div><p className="text-xs font-medium uppercase text-muted-foreground">Root cause</p><p className="mt-2 text-sm leading-6">{analysis.root_cause}</p></div><div><p className="text-xs font-medium uppercase text-muted-foreground">Recommended action</p><p className="mt-2 text-sm leading-6">{analysis.recommended_action}</p><div className="mt-3 flex gap-2"><Badge variant="secondary">{analysis.action_type.replaceAll("_", " ")}</Badge><Badge variant="outline">{Math.round(analysis.confidence * 100)}% confidence</Badge></div></div></div>}
      </section>
      <section className="mt-6 grid gap-4 lg:grid-cols-[0.8fr_1.2fr]"><Card className="shadow-none"><CardHeader><CardTitle>Audit timeline</CardTitle><CardDescription>Detector, recommendation, review, and execution events</CardDescription></CardHeader><CardContent><AuditTimeline events={incident.timeline} formatDateTime={formatDateTime} /></CardContent></Card><Card className="shadow-none"><CardHeader><CardTitle>Detection evidence</CardTitle><CardDescription>Complete structured evidence captured by the detector</CardDescription></CardHeader><CardContent><pre className="overflow-x-auto rounded-md bg-[#211f1d] p-4 text-xs leading-6 text-white/80">{JSON.stringify(incident.evidence, null, 2)}</pre></CardContent></Card></section>
    </div>
  </main>;
}

export default function IncidentDetailsPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const router = useRouter();
  const [incident, setIncident] = useState<BottleneckIncidentDetail | null>(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [analysis, setAnalysis] = useState<AgentAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [followUpTask, setFollowUpTask] = useState<FollowUpTask | null>(null);
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);
  const [owners, setOwners] = useState<SalesOwnerCapacity[]>([]);
  const [proposedOwner, setProposedOwner] = useState("");
  const [isRequestingReassignment, setIsRequestingReassignment] = useState(false);
  const [user] = useState<StoredUser | null>(() =>
    typeof window === "undefined" ? null : getStoredUser()
  );
  const [isVerifying, setIsVerifying] = useState(false);
  const [outcomeError, setOutcomeError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    Promise.all([
      getIncident(token, incidentId),
      getIncidentAnalysis(token, incidentId).catch((requestError: unknown) => {
        if (requestError instanceof ApiError && requestError.status === 404) return null;
        throw requestError;
      }),
      getOwnerCapacities(token),
    ])
      .then(([incidentResult, analysisResult, ownerResult]) => {
        setIncident(incidentResult);
        setAnalysis(analysisResult);
        setOwners(ownerResult);
        setFollowUpTask(incidentResult.actions.find((task) => task.status === "PENDING" || task.status === "IN_PROGRESS") ?? incidentResult.actions[0] ?? null);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof ApiError && requestError.status === 404) {
          setNotFound(true);
          return;
        }
        if (requestError instanceof ApiError && requestError.status === 401) {
          router.replace("/login");
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Incident details are unavailable");
      });
  }, [incidentId, router]);

  useEffect(() => {
    if (!incident) return;
    const token = localStorage.getItem("velocity_access_token");
    if (!token) return;
    const interval = window.setInterval(() => {
      void Promise.all([
        getIncident(token, incidentId),
        getIncidentAnalysis(token, incidentId).catch((requestError: unknown) => {
          if (requestError instanceof ApiError && requestError.status === 404) return null;
          throw requestError;
        }),
      ]).then(([incidentResult, analysisResult]) => {
        setIncident(incidentResult);
        setAnalysis(analysisResult);
        setFollowUpTask(incidentResult.actions.find((task) => task.status === "PENDING" || task.status === "IN_PROGRESS") ?? incidentResult.actions[0] ?? null);
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [incident, incidentId]);

  async function handleAnalyze() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setIsAnalyzing(true);
    setAnalysisError("");
    try {
      setAnalysis(await analyzeIncident(token, incidentId));
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }
      const message = requestError instanceof Error ? requestError.message : "Analysis is unavailable";
      setAnalysisError(message);
      setAnalysis((current) => current?.status === "FAILED" ? { ...current, error_message: message } : current);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleCreateFollowUp() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setIsExecuting(true);
    setActionError("");
    setActionMessage("");
    try {
      const task = await createFollowUpTask(token, incidentId);
      const alreadyExisted = incident?.actions.some((item) => item.id === task.id) ?? false;
      setFollowUpTask(task);
      setIncident((current) => current ? { ...current, status: "observing", actions: [task, ...current.actions.filter((item) => item.id !== task.id)] } : current);
      setActionMessage(alreadyExisted ? "An active follow-up already existed, so Velocity returned it without creating a duplicate." : "Follow-up created and recorded for outcome verification.");
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(requestError instanceof Error ? requestError.message : "Follow-up execution failed");
    } finally {
      setIsExecuting(false);
    }
  }

  async function handleRequestReassignment() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    if (!proposedOwner) return;
    setIsRequestingReassignment(true);
    setActionError("");
    setActionMessage("");
    try {
      const approval = await requestReassignment(token, incidentId, proposedOwner);
      const alreadyExisted = incident?.approvals.some((item) => item.id === approval.id) ?? false;
      setIncident((current) => current ? {
        ...current,
        approvals: [approval, ...current.approvals.filter((item) => item.id !== approval.id)],
      } : current);
      setActionMessage(alreadyExisted ? "A pending authorization already existed, so Velocity returned it without creating a duplicate." : "Reassignment authorization requested. No CRM owner change has occurred.");
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : "Reassignment request failed");
    } finally {
      setIsRequestingReassignment(false);
    }
  }

  async function handleVerifyOutcome() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setIsVerifying(true);
    setOutcomeError("");
    try {
      await verifyIncidentOutcome(token, incidentId);
      setIncident(await getIncident(token, incidentId));
    } catch (requestError) {
      setOutcomeError(requestError instanceof Error ? requestError.message : "Outcome verification failed");
    } finally {
      setIsVerifying(false);
    }
  }

  if (notFound) {
    return <main className="grid min-h-svh place-items-center bg-[#f7f6f3] px-5"><div className="max-w-md text-center"><span className="mx-auto grid size-12 place-items-center rounded-md bg-secondary"><Radar className="size-5 text-muted-foreground" /></span><h1 className="mt-5 text-2xl font-semibold">Incident not found</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">This incident may have been removed or the link is no longer valid.</p><Button asChild className="mt-6"><Link href="/dashboard"><ArrowLeft /> Return to dashboard</Link></Button></div></main>;
  }

  if (error) {
    return <main className="grid min-h-svh place-items-center bg-[#f7f6f3] px-5"><div className="max-w-md text-center"><span className="mx-auto grid size-12 place-items-center rounded-md bg-red-50"><AlertTriangle className="size-5 text-destructive" /></span><h1 className="mt-5 text-2xl font-semibold">Unable to load incident</h1><p role="alert" className="mt-2 text-sm leading-6 text-muted-foreground">{error}</p><div className="mt-6 flex justify-center gap-2"><Button variant="outline" onClick={() => window.location.reload()}>Try again</Button><Button asChild><Link href="/dashboard">Dashboard</Link></Button></div></div></main>;
  }

  if (!incident) {
    return <main className="min-h-svh bg-[#f7f6f3]"><header className="h-16 border-b border-border bg-background" /><LoadingIncident /></main>;
  }

  if (!incident.affected_deal) {
    return <OwnerIncidentDetails incident={incident} analysis={analysis} analysisError={analysisError} isAnalyzing={isAnalyzing} onAnalyze={() => void handleAnalyze()} />;
  }

  const deal = incident.affected_deal;
  const pendingApproval = incident.approvals.find((item) => item.status === "PENDING");
  const eligibleOwners = owners.filter((owner) => owner.is_active && owner.active_deals < owner.max_active_deals && owner.owner_name !== deal.owner_name);
  const selectedOwner = owners.find((owner) => owner.owner_name === proposedOwner);
  const latestOutcome = incident.outcomes[0];
  const isObserving = incident.status.toLowerCase() === "observing";
  const analysisLabel = {
    PENDING_ANALYSIS: "Waiting for analysis",
    ANALYZING: "AI analysis in progress",
    ANALYZED: "Analysis completed",
    ANALYSIS_FAILED: "Analysis failed",
  }[incident.analysis_state];
  const factors = [
    {
      key: "stage_duration",
      title: "Time spent in stage",
      icon: CalendarClock,
      explanation: (factor: RiskFactor) => `${deal.name} has spent ${factor.days ?? 0} days in ${deal.stage}. The detector begins adding risk after ${factor.threshold_days ?? 7} days.`,
    },
    {
      key: "activity_gap",
      title: "Time since last activity",
      icon: Activity,
      explanation: (factor: RiskFactor) => `The latest recorded activity was ${factor.days ?? 0} days ago. Risk begins increasing after ${factor.threshold_days ?? 5} days without activity.`,
    },
    {
      key: "overdue_follow_up",
      title: "Overdue follow-up",
      icon: Clock3,
      explanation: (factor: RiskFactor) => factor.triggered
        ? `The scheduled follow-up is ${factor.days ?? 0} days overdue and is actively contributing to this incident.`
        : "The next follow-up is not overdue and does not contribute to the current risk score.",
    },
  ];
  const crmTimeline = [
    { label: "Incident detected", value: incident.detected_at, icon: AlertTriangle },
    { label: "Incident last evaluated", value: incident.updated_at, icon: CheckCircle2 },
    { label: `Entered ${deal.stage}`, value: deal.stage_entered_at, icon: BriefcaseBusiness },
    { label: "Last CRM activity", value: deal.last_activity_at, icon: Activity },
    { label: "Next follow-up", value: deal.next_follow_up_at, icon: CalendarClock },
  ];

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8"><Button asChild variant="ghost" size="sm"><Link href="/dashboard"><ArrowLeft /> Dashboard</Link></Button><div className="flex items-center gap-2"><Badge variant={incident.status === "open" ? "secondary" : "outline"}>{incident.status}</Badge><Badge variant="outline" className={severityStyles[incident.severity]}>{incident.severity[0].toUpperCase() + incident.severity.slice(1)}</Badge></div></div></header>

    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-9 lg:px-8">
      <section className="border-b border-border pb-7"><div className="flex items-center gap-2 text-sm font-medium text-primary"><Radar className="size-4" /> Incident details</div><h1 className="mt-2 max-w-3xl text-2xl font-semibold sm:text-3xl">{incident.title}</h1><p className="mt-3 text-sm text-muted-foreground">Detected {formatDateTime(incident.detected_at)} · {incident.incident_type.replaceAll("_", " ")} · ID {incident.id}</p></section>

      <section className="mt-6 grid gap-4 md:grid-cols-3">
        <Card className="shadow-none"><CardHeader><CardDescription>Risk score</CardDescription><CardTitle className="text-3xl">{incident.risk_score}<span className="text-base font-normal text-muted-foreground"> / 100</span></CardTitle></CardHeader><CardContent><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary" style={{ width: `${incident.risk_score}%` }} /></div></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Severity</CardDescription><CardTitle className="capitalize">{incident.severity}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">{incident.severity === "critical" ? "Immediate intervention is recommended." : "Review the contributing factors and follow up."}</p></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Status</CardDescription><CardTitle className="capitalize">{incident.status}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">Last evaluated {formatDateTime(incident.updated_at)}</p></CardContent></Card>
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="shadow-none"><CardHeader><CardTitle>Affected deal</CardTitle><CardDescription>CRM opportunity connected to this incident</CardDescription></CardHeader><CardContent className="grid gap-5 sm:grid-cols-2"><div><p className="text-xs text-muted-foreground">Deal</p><p className="mt-1 font-medium">{deal.name}</p></div><div><p className="text-xs text-muted-foreground">Stage</p><p className="mt-1 font-medium">{deal.stage}</p></div><div><p className="flex items-center gap-1.5 text-xs text-muted-foreground"><CircleDollarSign className="size-3.5" /> Value</p><p className="mt-1 font-medium">{currencyFormatter.format(Number(deal.value))}</p></div><div><p className="flex items-center gap-1.5 text-xs text-muted-foreground"><UserRound className="size-3.5" /> Owner</p><p className="mt-1 font-medium">{deal.owner_name}</p></div><div><p className="text-xs text-muted-foreground">Stage entered</p><p className="mt-1 text-sm">{formatDateTime(deal.stage_entered_at)}</p></div><div><p className="text-xs text-muted-foreground">Last activity</p><p className="mt-1 text-sm">{formatDateTime(deal.last_activity_at)}</p></div><div className="sm:col-span-2"><p className="text-xs text-muted-foreground">Next follow-up</p><p className="mt-1 text-sm">{formatDateTime(deal.next_follow_up_at)}</p></div></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardTitle>Audit timeline</CardTitle><CardDescription>Detector, recommendation, review, and execution events</CardDescription></CardHeader><CardContent><AuditTimeline events={incident.timeline} formatDateTime={formatDateTime} /><div className="mt-5 space-y-4 border-t border-border pt-5">{crmTimeline.map(({ label, value, icon: Icon }) => <div key={label} className="flex gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-md bg-secondary"><Icon className="size-4 text-muted-foreground" /></span><div><p className="text-sm font-medium">{label}</p><p className="mt-0.5 text-xs text-muted-foreground">CRM evidence · {formatDateTime(value)}</p></div></div>)}</div></CardContent></Card>
      </section>

      {(latestOutcome || isObserving) && <section className="mt-6 border-y border-border bg-background px-5 py-6 md:px-7">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex items-center gap-2 text-sm font-medium text-primary"><RefreshCw className="size-4" /> Outcome verification</div><h2 className="mt-2 text-xl font-semibold">{latestOutcome ? latestOutcome.outcome.replaceAll("_", " ") : "Observation active"}</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{latestOutcome && typeof latestOutcome.verification_evidence.reason === "string" ? latestOutcome.verification_evidence.reason : "Fresh CRM evidence will determine whether the corrective action reduced the bottleneck."}</p></div>
          {user?.is_admin === true && latestOutcome?.verification_status === "PENDING" && <Button onClick={handleVerifyOutcome} disabled={isVerifying} className="shrink-0">{isVerifying ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}{isVerifying ? "Verifying" : "Verify Outcome Now"}</Button>}
        </div>
        {outcomeError && <div role="alert" className="mt-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"><AlertTriangle className="size-4 shrink-0" />{outcomeError}</div>}
        {latestOutcome && <div className="mt-6 grid gap-5 md:grid-cols-4">
          <div><p className="text-xs text-muted-foreground">Risk change</p><p className="mt-1 text-lg font-semibold tabular-nums">{latestOutcome.previous_risk_score} <span className="text-muted-foreground">to</span> {latestOutcome.current_risk_score ?? "Pending"}</p></div>
          <div><p className="text-xs text-muted-foreground">Verification</p><p className="mt-1 text-sm font-medium">{latestOutcome.verification_status}</p></div>
          <div><p className="text-xs text-muted-foreground">Last checked</p><p className="mt-1 text-sm font-medium">{formatDateTime(latestOutcome.verified_at)}</p></div>
          <div><p className="text-xs text-muted-foreground">Next check</p><p className="mt-1 text-sm font-medium">{formatDateTime(latestOutcome.next_check_at)}</p></div>
        </div>}
        {latestOutcome && <div className="mt-5 flex flex-wrap gap-2">{[
          ["activity_resumed", "Activity resumed"],
          ["overdue_follow_up_addressed", "Follow-up addressed"],
          ["pipeline_stage_moved", "Stage moved"],
          ["owner_reassignment_completed", "Owner changed"],
          ["risk_decreased", "Risk decreased"],
        ].map(([key, label]) => <Badge key={key} variant={latestOutcome.verification_evidence[key] === true ? "secondary" : "outline"}>{latestOutcome.verification_evidence[key] === true && <CheckCircle2 className="size-3" />}{label}</Badge>)}</div>}
        {incident.outcomes.length > 1 && <div className="mt-6 border-t border-border pt-5"><p className="text-xs font-medium uppercase text-muted-foreground">Verification history</p><div className="mt-3 divide-y divide-border">{incident.outcomes.map((outcome) => <div key={outcome.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center"><div><p className="text-sm font-medium">{outcome.outcome.replaceAll("_", " ")}</p><p className="mt-0.5 text-xs text-muted-foreground">{formatDateTime(outcome.verified_at ?? outcome.created_at)}</p></div><div className="sm:ml-auto"><Badge variant="outline">{outcome.previous_risk_score} to {outcome.current_risk_score ?? "pending"}</Badge></div></div>)}</div></div>}
      </section>}

      <section className="mt-6"><h2 className="text-lg font-semibold">Risk-factor breakdown</h2><p className="mt-1 text-sm text-muted-foreground">How each observed condition contributed to the score.</p><div className="mt-4 grid gap-4 lg:grid-cols-3">{factors.map(({ key, title, icon: Icon, explanation }) => { const factor = readFactor(incident.evidence, key); return <Card key={key} className="shadow-none"><CardHeader className="flex-row items-start justify-between"><span className="grid size-9 place-items-center rounded-md bg-secondary"><Icon className="size-4" /></span><Badge variant={factor.triggered ? "secondary" : "outline"}>{factor.points ?? 0} points</Badge></CardHeader><CardContent><CardTitle>{title}</CardTitle><p className="mt-2 text-sm leading-6 text-muted-foreground">{explanation(factor)}</p></CardContent></Card>; })}</div></section>

      <section className="mt-8 border-y border-border py-7">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex items-center gap-2 text-sm font-medium text-primary"><BrainCircuit className="size-4" /> Root cause analysis</div><h2 className="mt-2 text-xl font-semibold">Grounded incident assessment</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">Gemini reviews detector evidence and retrieved operational policies. Recommendations remain read-only and require human execution.</p></div>
          <Button onClick={handleAnalyze} disabled={isAnalyzing || incident.analysis_state === "ANALYZING"} className="shrink-0"><span className="inline-flex items-center gap-2">{isAnalyzing || incident.analysis_state === "ANALYZING" ? <LoaderCircle className="size-4 animate-spin" /> : <BrainCircuit className="size-4" />}{isAnalyzing || incident.analysis_state === "ANALYZING" ? "Analyzing" : analysis?.status === "COMPLETED" ? "Analyze again" : "Analyze with AI"}</span></Button>
        </div>

        <div className="mt-5 flex items-center gap-2 text-sm text-muted-foreground"><Badge variant={incident.analysis_state === "ANALYSIS_FAILED" ? "destructive" : "outline"}>{analysisLabel}</Badge>{incident.analysis_state === "PENDING_ANALYSIS" && <span>Automatic analysis will begin when this incident meets the configured policy.</span>}{incident.analysis_state === "ANALYZING" && <span>Grounded analysis is running. This page updates automatically.</span>}</div>

        {(analysisError || analysis?.status === "FAILED") && <div role="alert" className="mt-5 flex items-start justify-between gap-4 rounded-md border border-red-200 bg-red-50 p-4"><div><p className="text-sm font-medium text-red-800">Analysis could not be completed</p><p className="mt-1 text-sm text-red-700">{analysisError || (analysis?.status === "FAILED" ? analysis.error_message : "")}</p></div><Button size="sm" variant="outline" onClick={handleAnalyze} disabled={isAnalyzing}>Retry</Button></div>}

        {analysis?.status === "COMPLETED" && <div className="mt-6 grid gap-x-8 gap-y-6 lg:grid-cols-2">
          <div className="lg:col-span-2"><p className="text-xs font-medium uppercase text-muted-foreground">Summary</p><p className="mt-2 text-base leading-7">{analysis.summary}</p></div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Root cause</p><p className="mt-2 text-sm leading-6">{analysis.root_cause}</p></div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Risk explanation</p><p className="mt-2 text-sm leading-6">{analysis.risk_explanation}</p></div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Supporting evidence</p><ul className="mt-2 space-y-2">{analysis.supporting_evidence.map((evidence) => <li key={evidence} className="flex gap-2 text-sm leading-6"><CheckCircle2 className="mt-1 size-4 shrink-0 text-emerald-700" />{evidence}</li>)}</ul></div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Recommended action</p><p className="mt-2 text-sm font-medium leading-6">{analysis.recommended_action}</p><div className="mt-3 flex flex-wrap gap-2"><Badge variant="secondary">{analysis.action_type.replaceAll("_", " ")}</Badge><Badge variant="outline">{Math.round(analysis.confidence * 100)}% confidence</Badge><Badge variant={analysis.approval_required ? "secondary" : "outline"}><ShieldCheck className="size-3" /> {analysis.approval_required ? "Approval required" : "No approval required"}</Badge></div>{analysis.action_type === "CREATE_FOLLOW_UP" && !followUpTask && <Button className="mt-4" size="sm" onClick={handleCreateFollowUp} disabled={isExecuting}>{isExecuting ? <LoaderCircle className="animate-spin" /> : <CalendarPlus />}{isExecuting ? "Executing" : "Execute Follow-Up"}</Button>}{analysis.action_type === "REQUEST_REASSIGNMENT" && <div className="mt-4 border-t border-border pt-4">{pendingApproval ? <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 p-3"><div><p className="text-sm font-medium text-amber-900">Approval pending</p><p className="mt-1 text-xs text-amber-700">{pendingApproval.current_owner} to {pendingApproval.proposed_owner}</p></div><Button asChild variant="outline" size="sm"><Link href={`/approvals/${pendingApproval.id}`}>Review</Link></Button></div> : <div className="space-y-3"><label className="block text-xs font-medium text-muted-foreground" htmlFor="proposed-owner">Proposed owner</label><select id="proposed-owner" value={proposedOwner} onChange={(event) => setProposedOwner(event.target.value)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="">Select an available owner</option>{eligibleOwners.map((owner) => <option key={owner.owner_name} value={owner.owner_name}>{owner.owner_name} ({owner.active_deals}/{owner.max_active_deals} active)</option>)}</select>{selectedOwner && <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-md bg-secondary p-3 text-xs"><div><span className="text-muted-foreground">Current</span><p className="mt-1 font-medium">{deal.owner_name}</p></div><span className="text-muted-foreground">to</span><div><span className="text-muted-foreground">Proposed</span><p className="mt-1 font-medium">{selectedOwner.owner_name}</p><p className="mt-0.5 text-muted-foreground">{selectedOwner.active_deals}/{selectedOwner.max_active_deals} active deals</p></div></div>}<Button size="sm" onClick={handleRequestReassignment} disabled={!proposedOwner || isRequestingReassignment}>{isRequestingReassignment ? <LoaderCircle className="animate-spin" /> : <Users />}{isRequestingReassignment ? "Requesting" : "Request Reassignment"}</Button></div>}</div>}{actionError && <p role="alert" className="mt-3 text-sm text-destructive">{actionError}</p>}</div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Expected outcome</p><p className="mt-2 text-sm leading-6">{analysis.expected_outcome}</p></div>
          <div><p className="text-xs font-medium uppercase text-muted-foreground">Policy references</p><div className="mt-2 flex flex-wrap gap-2">{analysis.policy_references.length ? analysis.policy_references.map((policy) => <Badge key={policy} variant="outline">{policy}</Badge>) : <span className="text-sm text-muted-foreground">No policy cited</span>}</div><p className="mt-3 text-xs text-muted-foreground">Generated by {analysis.model_name} · {formatDateTime(analysis.updated_at)}</p></div>
        </div>}

        {actionMessage && <div role="status" className="mt-5 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="size-4 shrink-0" />{actionMessage}</div>}
        {incident.actions.length > 0 && <div className="mt-6 border-t border-border pt-5"><p className="text-xs font-medium uppercase text-muted-foreground">Follow-up history</p><div className="mt-3 divide-y divide-border border-y border-border">{incident.actions.map((task) => <div key={task.id} className="py-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div className="flex gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-md bg-emerald-50 text-emerald-700"><CalendarPlus className="size-4" /></span><div><p className="font-medium">{task.title}</p><p className="mt-1 text-sm leading-6 text-muted-foreground">{task.description}</p></div></div><div className="flex gap-2"><Badge variant="secondary">{task.execution_source === "AUTOMATIC" ? "Automatic policy" : "Manual request"}</Badge><Badge variant="outline">{task.status}</Badge></div></div><dl className="mt-4 grid gap-4 pl-12 sm:grid-cols-4"><div><dt className="text-xs text-muted-foreground">Assigned to</dt><dd className="mt-1 text-sm font-medium">{task.assigned_to}</dd></div><div><dt className="text-xs text-muted-foreground">Due</dt><dd className="mt-1 text-sm font-medium">{formatDateTime(task.due_at)}</dd></div><div><dt className="text-xs text-muted-foreground">Execution result</dt><dd className="mt-1 text-sm font-medium">{String(task.execution_result.status ?? "Recorded locally")}</dd></div><div><dt className="text-xs text-muted-foreground">Created</dt><dd className="mt-1 text-sm font-medium">{formatDateTime(task.created_at)}</dd></div></dl></div>)}</div></div>}
        {incident.approvals.length > 0 && <div className="mt-6 border-t border-border pt-5"><div className="flex items-center justify-between"><p className="text-xs font-medium uppercase text-muted-foreground">Reassignment approvals</p><Button asChild variant="ghost" size="sm"><Link href="/approvals">Approval inbox</Link></Button></div><div className="mt-3 divide-y divide-border border-y border-border">{incident.approvals.map((approval) => <Link href={`/approvals/${approval.id}`} key={approval.id} className="flex items-center gap-3 py-4 hover:bg-secondary/40"><span className="grid size-9 shrink-0 place-items-center rounded-md bg-secondary"><Users className="size-4" /></span><div className="min-w-0"><p className="text-sm font-medium">{approval.current_owner} to {approval.proposed_owner}</p><p className="mt-1 text-xs text-muted-foreground">Requested {formatDateTime(approval.created_at)}</p></div><Badge variant={approval.status === "EXECUTION_FAILED" ? "destructive" : "outline"} className="ml-auto">{approval.status.replaceAll("_", " ")}</Badge></Link>)}</div></div>}
      </section>

      <section className="mt-6"><Card className="shadow-none"><CardHeader><CardTitle>Detection evidence</CardTitle><CardDescription>Complete structured evidence captured by the detector</CardDescription></CardHeader><CardContent><pre className="overflow-x-auto rounded-md bg-[#211f1d] p-4 text-xs leading-6 text-white/80">{JSON.stringify(incident.evidence, null, 2)}</pre></CardContent></Card></section>
    </div>
  </main>;
}