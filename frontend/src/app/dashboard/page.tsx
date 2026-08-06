"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Activity, AlertTriangle, Bell, Bot, BriefcaseBusiness, CheckCircle2, ChevronDown,
  CircleDollarSign, LayoutDashboard, LoaderCircle, LogOut, Menu, Radar, RefreshCw,
  Search, Settings, ShieldCheck, Sparkles, TrendingUp, Unplug, Users,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BottleneckIncident, DashboardSummary, Deal, getDashboardSummary, getDeals,
  getIncidents, getMonitoringStatus, getOwnerCapacities, MonitoringStatus,
  SalesOwnerCapacity, scanForBottlenecks,
} from "@/lib/api";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function formatCurrency(value: string) {
  return currencyFormatter.format(Number(value));
}

function formatDate(value: string | null) {
  return value ? dateFormatter.format(new Date(value)) : "Not scheduled";
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatOptionalDateTime(value: string | null) {
  return value ? formatDateTime(value) : "Not available";
}

function formatRunDuration(startedAt: string | undefined, completedAt: string | null | undefined) {
  if (!startedAt) return "No completed run";
  if (!completedAt) return "In progress";
  const durationSeconds = Math.max(0, Math.round((new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 1000));
  return durationSeconds < 60 ? `${durationSeconds}s` : `${Math.floor(durationSeconds / 60)}m ${durationSeconds % 60}s`;
}

const severityStyles: Record<BottleneckIncident["severity"], string> = {
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  high: "border-orange-200 bg-orange-50 text-orange-800",
  critical: "border-red-200 bg-red-50 text-red-700",
};

function SeverityBadge({ severity }: { severity: BottleneckIncident["severity"] }) {
  return <Badge variant="outline" className={severityStyles[severity]}>{severity[0].toUpperCase() + severity.slice(1)}</Badge>;
}

const navItems = [
  { label: "Overview", icon: LayoutDashboard, active: true },
  { label: "Pipeline", icon: BriefcaseBusiness },
  { label: "Risk monitor", icon: AlertTriangle, count: 12 },
  { label: "Agent runs", icon: Bot },
  { label: "Team capacity", icon: Users },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return <div className="flex h-full flex-col bg-[#211f1d] text-white">
    <div className="flex h-16 items-center gap-2.5 border-b border-white/10 px-5">
      <span className="grid size-8 place-items-center rounded-md bg-primary"><TrendingUp className="size-4" /></span>
      <span className="text-lg font-semibold">Velocity</span>
      <Badge className="ml-auto border-white/10 bg-white/10 text-[10px] text-white">AI OPS</Badge>
    </div>
    <div className="px-4 pb-2 pt-5 text-[11px] font-medium uppercase text-white/35">Workspace</div>
    <nav className="space-y-1 px-3">
      {navItems.map(({ label, icon: Icon, active, count }) => <button key={label} onClick={onNavigate} className={`flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm transition-colors ${active ? "bg-primary text-white" : "text-white/60 hover:bg-white/5 hover:text-white"}`}><Icon className="size-4" /><span>{label}</span>{count && <span className="ml-auto rounded bg-white/10 px-1.5 py-0.5 text-xs">{count}</span>}</button>)}
    </nav>
    <div className="mt-auto border-t border-white/10 p-3">
      <Link href="/settings/monitoring" onClick={onNavigate} className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-white/55 hover:bg-white/5 hover:text-white"><Settings className="size-4" /> Settings</Link>
      <Link href="/settings/integrations/zoho" onClick={onNavigate} className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-white/55 hover:bg-white/5 hover:text-white"><Unplug className="size-4" /> Zoho integration</Link>
      <div className="mt-3 rounded-md border border-white/10 bg-white/5 p-3">
        <div className="flex items-center gap-2 text-xs font-medium"><ShieldCheck className="size-3.5 text-emerald-400" /> Systems operational</div>
        <p className="mt-1 text-[11px] text-white/35">CRM provider status available in integrations</p>
      </div>
    </div>
  </div>;
}

function LoadingDashboard() {
  return <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} className="h-36 rounded-lg" />)}</div>;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [incidents, setIncidents] = useState<BottleneckIncident[] | null>(null);
  const [monitoring, setMonitoring] = useState<MonitoringStatus | null>(null);
  const [owners, setOwners] = useState<SalesOwnerCapacity[]>([]);
  const [asOf, setAsOf] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const router = useRouter();

  async function loadDashboard() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) { router.replace("/login"); return; }
    setError("");
    setSuccess("");
    setIsLoading(true);
    try {
      const [nextSummary, nextDeals, nextIncidents, nextMonitoring, nextOwners] = await Promise.all([
        getDashboardSummary(token),
        getDeals(token),
        getIncidents(token),
        getMonitoringStatus(token),
        getOwnerCapacities(token),
      ]);
      setSummary(nextSummary);
      setDeals(nextDeals);
      setIncidents(nextIncidents);
      setMonitoring(nextMonitoring);
      setOwners(nextOwners);
      setAsOf(Date.now());
    }
    catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Dashboard unavailable");
      if (requestError instanceof Error && requestError.message.toLowerCase().includes("token")) router.replace("/login");
    } finally {
      setIsLoading(false);
    }
  }

  async function scanBottlenecks() {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) { router.replace("/login"); return; }
    setError("");
    setSuccess("");
    setIsScanning(true);
    try {
      const detected = await scanForBottlenecks(token);
      const [nextSummary, nextDeals, nextIncidents, nextMonitoring, nextOwners] = await Promise.all([
        getDashboardSummary(token),
        getDeals(token),
        getIncidents(token),
        getMonitoringStatus(token),
        getOwnerCapacities(token),
      ]);
      setSummary(nextSummary);
      setDeals(nextDeals);
      setIncidents(nextIncidents);
      setMonitoring(nextMonitoring);
      setOwners(nextOwners);
      setAsOf(Date.now());
      setSuccess(`Scan complete. ${detected.length} active bottleneck${detected.length === 1 ? "" : "s"} detected.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Bottleneck scan failed");
    } finally {
      setIsScanning(false);
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    Promise.all([getDashboardSummary(token), getDeals(token), getIncidents(token), getMonitoringStatus(token), getOwnerCapacities(token)])
      .then(([nextSummary, nextDeals, nextIncidents, nextMonitoring, nextOwners]) => {
        setSummary(nextSummary);
        setDeals(nextDeals);
        setIncidents(nextIncidents);
        setMonitoring(nextMonitoring);
        setOwners(nextOwners);
        setAsOf(Date.now());
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : "Dashboard unavailable");
        router.replace("/login");
      })
      .finally(() => setIsLoading(false));

    const poll = window.setInterval(() => {
      Promise.all([getMonitoringStatus(token), getIncidents(token)])
        .then(([nextMonitoring, nextIncidents]) => {
          setMonitoring(nextMonitoring);
          setIncidents(nextIncidents);
          setAsOf(Date.now());
        })
        .catch(() => undefined);
    }, 15_000);
    return () => window.clearInterval(poll);
  }, [router]);

  function signOut() {
    localStorage.removeItem("velocity_access_token");
    localStorage.removeItem("velocity_user");
    router.replace("/login");
  }

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground lg:grid lg:grid-cols-[248px_1fr]">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] lg:block"><Sidebar /></aside>
    <div className="lg:col-start-2">
      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-background/95 px-4 backdrop-blur sm:px-6">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}><SheetTrigger asChild><Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation"><Menu /></Button></SheetTrigger><SheetContent side="left" className="w-[280px] border-0 p-0"><SheetTitle className="sr-only">Navigation</SheetTitle><Sidebar onNavigate={() => setMobileOpen(false)} /></SheetContent></Sheet>
        <div className="relative hidden w-full max-w-sm md:block"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="h-9 bg-secondary/60 pl-9" placeholder="Search deals, owners, or incidents" /></div>
        <div className="ml-auto flex items-center gap-1.5">
          <Button variant="ghost" size="icon" aria-label="Notifications" className="relative"><Bell /><span className="absolute right-2 top-2 size-1.5 rounded-full bg-primary" /></Button>
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" className="h-10 gap-2 px-2"><Avatar className="size-7"><AvatarFallback className="bg-[#211f1d] text-xs text-white">VA</AvatarFallback></Avatar><span className="hidden text-sm sm:inline">Velocity Admin</span><ChevronDown className="size-3.5 text-muted-foreground" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-56"><DropdownMenuLabel>admin@velocitycrm.com</DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem><Settings /> Account settings</DropdownMenuItem><DropdownMenuItem onClick={signOut}><LogOut /> Sign out</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
        </div>
      </header>

      <div className="p-4 sm:p-6 xl:p-8">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div><div className="flex items-center gap-2 text-sm font-medium text-primary"><Sparkles className="size-4" /> Operations intelligence</div><h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Good morning, Admin</h1><p className="mt-1 text-sm text-muted-foreground">Here is what needs attention across your revenue operation.</p></div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={isLoading || isScanning} onClick={() => void loadDashboard()}><RefreshCw className={isLoading ? "animate-spin" : ""} /> Refresh data</Button>
            <Button variant="outline" size="sm" disabled={isLoading || isScanning} onClick={() => void scanBottlenecks()}>{isScanning ? <LoaderCircle className="animate-spin" /> : <Radar />} {isScanning ? "Scanning..." : "Scan for Bottlenecks"}</Button>
          </div>
        </div>

        {success && <div role="status" className="mb-5 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="size-4 shrink-0" />{success}</div>}
        {error && <div role="alert" className="mb-5 flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive"><AlertTriangle className="size-4 shrink-0" />{error}</div>}
        {isLoading ? <LoadingDashboard /> : !summary || !deals || !incidents ? <div className="rounded-md border border-border bg-background p-8 text-center text-sm text-muted-foreground">Dashboard data is unavailable. Refresh to try again.</div> : <>
          <section className="mb-4 border-y border-border bg-background px-4 py-4 sm:px-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center">
              <div className="flex min-w-52 items-center gap-3">
                <span className={`size-2.5 rounded-full ${monitoring?.active ? "bg-emerald-500" : "bg-zinc-400"}`} />
                <div><p className="text-sm font-semibold">Proactive monitoring</p><p className="text-xs text-muted-foreground">{monitoring?.cycle_running ? "Scan in progress" : monitoring?.active ? "Active" : "Stopped"}</p></div>
              </div>
              <div className="grid flex-1 grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 xl:grid-cols-7">
                <div><p className="text-[11px] text-muted-foreground">Interval</p><p className="mt-0.5 text-sm font-medium">{monitoring ? `${monitoring.interval_seconds}s` : "-"}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Last scan</p><p className="mt-0.5 text-sm font-medium">{formatOptionalDateTime(monitoring?.last_scan_at ?? null)}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Next expected</p><p className="mt-0.5 text-sm font-medium">{formatOptionalDateTime(monitoring?.next_scan_at ?? null)}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Deals scanned</p><p className="mt-0.5 text-sm font-medium tabular-nums">{monitoring?.last_run?.deals_scanned ?? 0}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Incidents detected</p><p className="mt-0.5 text-sm font-medium tabular-nums">{monitoring?.last_run?.incidents_created ?? 0}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Last status</p><p className="mt-0.5 text-sm font-medium">{monitoring?.last_run?.status.replaceAll("_", " ") ?? "No runs"}</p></div>
                <div><p className="text-[11px] text-muted-foreground">Run duration</p><p className="mt-0.5 text-sm font-medium">{formatRunDuration(monitoring?.last_run?.started_at, monitoring?.last_run?.completed_at)}</p></div>
              </div>
            </div>
          </section>

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {(() => {
              const activeDeals = deals.filter((deal) => deal.status.toLowerCase() === "active");
              const attentionDeals = deals.filter((deal) =>
                deal.status.toLowerCase() !== "active"
                || (deal.next_follow_up_at !== null && new Date(deal.next_follow_up_at).getTime() < asOf)
              );
              const cards = [
                { label: "Total deals", value: String(deals.length), detail: "Across all pipeline stages", icon: BriefcaseBusiness },
                { label: "Active deals", value: String(activeDeals.length), detail: "Currently progressing", icon: TrendingUp },
                { label: "Total pipeline value", value: formatCurrency(deals.reduce((total, deal) => total + Number(deal.value), 0).toString()), detail: "Open CRM opportunity value", icon: CircleDollarSign },
                { label: "Deals needing attention", value: String(attentionDeals.length), detail: "Inactive or follow-up overdue", icon: AlertTriangle },
              ];
              return cards.map(({ label, value, detail, icon: Icon }) => <Card key={label} className="gap-4 py-5 shadow-none"><CardHeader className="flex-row items-center justify-between px-5"><CardDescription>{label}</CardDescription><span className="grid size-8 place-items-center rounded-md bg-secondary text-muted-foreground"><Icon className="size-4" /></span></CardHeader><CardContent className="px-5"><p className="text-2xl font-semibold">{value}</p><p className="mt-2 text-xs text-muted-foreground">{detail}</p></CardContent></Card>);
            })()}
          </section>

          {(() => {
            const activeIncidents = incidents.filter((incident) => incident.status.toLowerCase() === "open");
            const affectedDealIds = new Set(activeIncidents.flatMap((incident) => incident.deal_id ? [incident.deal_id] : []));
            const valueAtRisk = deals
              .filter((deal) => affectedDealIds.has(deal.id))
              .reduce((total, deal) => total + Number(deal.value), 0);
            const cards = [
              { label: "Active bottlenecks", value: String(activeIncidents.length), detail: "Open incidents requiring action", icon: Radar },
              { label: "Critical incidents", value: String(activeIncidents.filter((incident) => incident.severity === "critical").length), detail: "Immediate intervention required", icon: AlertTriangle },
              { label: "High-risk incidents", value: String(activeIncidents.filter((incident) => incident.severity === "high").length), detail: "High severity open incidents", icon: ShieldCheck },
              { label: "Pipeline value at risk", value: currencyFormatter.format(valueAtRisk), detail: "Unique deals with open incidents", icon: CircleDollarSign },
            ];
            return <section className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, detail, icon: Icon }) => <Card key={label} className="gap-4 py-5 shadow-none"><CardHeader className="flex-row items-center justify-between px-5"><CardDescription>{label}</CardDescription><span className="grid size-8 place-items-center rounded-md bg-secondary text-muted-foreground"><Icon className="size-4" /></span></CardHeader><CardContent className="px-5"><p className="text-2xl font-semibold">{value}</p><p className="mt-2 text-xs text-muted-foreground">{detail}</p></CardContent></Card>)}</section>;
          })()}

          <section className="mt-4">
            <Card className="shadow-none">
              <CardHeader className="flex-row items-start justify-between">
                <div><CardTitle>Bottleneck incidents</CardTitle><CardDescription>Detected pipeline risks and their current status</CardDescription></div>
                <Badge variant="outline">{incidents.length} total</Badge>
              </CardHeader>
              <CardContent className="px-0">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1180px] text-sm">
                    <thead><tr className="border-y border-border bg-secondary/35 text-left text-xs text-muted-foreground"><th className="px-6 py-3 font-medium">Incident title</th><th className="px-4 py-3 font-medium">Affected subject</th><th className="px-4 py-3 font-medium">Incident type</th><th className="px-4 py-3 font-medium">Risk score</th><th className="px-4 py-3 font-medium">Severity</th><th className="px-4 py-3 font-medium">Analysis</th><th className="px-4 py-3 font-medium">Status</th><th className="px-6 py-3 font-medium">Detection time</th></tr></thead>
                    <tbody>{incidents.length === 0 ? <tr><td colSpan={8} className="px-6 py-12 text-center text-muted-foreground">{monitoring?.last_run ? "The latest monitoring run found no bottleneck incidents." : "Monitoring has not completed a run yet. Run a scan to evaluate the pipeline."}</td></tr> : incidents.map((incident) => { const deal = deals.find((item) => item.id === incident.deal_id); const subject = deal?.name ?? (typeof incident.evidence.owner_name === "string" ? incident.evidence.owner_name : "Sales owner"); const analysisLabel = { PENDING_ANALYSIS: "Waiting for analysis", ANALYZING: "AI analysis in progress", ANALYZED: "Analysis completed", ANALYSIS_FAILED: "Analysis failed" }[incident.analysis_state]; return <tr key={incident.id} tabIndex={0} role="link" aria-label={`View details for ${incident.title}`} onClick={() => router.push(`/incidents/${incident.id}`)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); router.push(`/incidents/${incident.id}`); } }} className="cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-secondary/35 focus-visible:bg-secondary/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"><td className="px-6 py-4 font-medium">{incident.title}</td><td className="px-4 py-4 text-muted-foreground">{subject}</td><td className="px-4 py-4 text-muted-foreground">{incident.incident_type.replaceAll("_", " ")}</td><td className="px-4 py-4 font-semibold tabular-nums">{incident.risk_score}</td><td className="px-4 py-4"><SeverityBadge severity={incident.severity} /></td><td className="px-4 py-4"><Badge variant={incident.analysis_state === "ANALYSIS_FAILED" ? "destructive" : "outline"}>{analysisLabel}</Badge></td><td className="px-4 py-4"><Badge variant={incident.status.toLowerCase() === "open" ? "secondary" : "outline"}>{incident.status}</Badge></td><td className="px-6 py-4 whitespace-nowrap text-muted-foreground">{formatDateTime(incident.detected_at)}</td></tr>; })}</tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-[1.45fr_0.75fr]">
            <Card className="shadow-none"><CardHeader className="flex-row items-start justify-between"><div><CardTitle>Pipeline momentum</CardTitle><CardDescription>Current value and conversion by stage</CardDescription></div><Badge variant="outline">$2.84M total</Badge></CardHeader><CardContent><div className="flex h-44 items-end gap-3 border-b border-border pb-0 sm:gap-6">{summary.pipeline.map((stage, index) => <div key={stage.name} className="flex h-full flex-1 flex-col justify-end"><div className="mb-2 text-center"><p className="text-sm font-semibold">{stage.amount}</p><p className="text-xs text-muted-foreground">{stage.value} deals</p></div><div className="w-full rounded-t bg-primary/90" style={{ height: `${42 + index * 12}%`, opacity: 1 - index * 0.14 }} /></div>)}</div><div className="mt-3 grid grid-cols-4 gap-3 text-center text-xs text-muted-foreground">{summary.pipeline.map((stage) => <span key={stage.name}>{stage.name}</span>)}</div></CardContent></Card>
            <Card className="shadow-none"><CardHeader><CardTitle>Owner capacity</CardTitle><CardDescription>Current active Deals against configured limits</CardDescription></CardHeader><CardContent className="space-y-5">{owners.filter((owner) => owner.is_active).map((owner) => { const activeDeals = deals.filter((deal) => deal.status.toLowerCase() === "active" && deal.owner_name === owner.owner_name).length; const utilization = Math.min(100, Math.round((activeDeals / owner.max_active_deals) * 100)); const initials = owner.owner_name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase(); return <div key={owner.id}><div className="mb-2 flex items-center gap-3"><Avatar className="size-8"><AvatarFallback className="bg-secondary text-xs">{initials}</AvatarFallback></Avatar><div className="min-w-0 flex-1"><div className="flex justify-between gap-3 text-sm"><span className="truncate font-medium">{owner.owner_name}</span><span className={utilization > 85 ? "font-semibold text-primary" : "text-muted-foreground"}>{utilization}%</span></div><p className="text-xs text-muted-foreground">{activeDeals} / {owner.max_active_deals} active Deals</p></div></div><Progress value={utilization} className="h-1.5" /></div>; })}</CardContent></Card>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-[1.45fr_0.75fr]">
            <Card className="shadow-none"><CardHeader className="flex-row items-start justify-between"><div><CardTitle>Deals</CardTitle><CardDescription>Live opportunities from Velocity CRM</CardDescription></div><Badge variant="outline">{deals.length} total</Badge></CardHeader><CardContent className="px-0"><div className="overflow-x-auto"><table className="w-full min-w-[980px] text-sm"><thead><tr className="border-y border-border bg-secondary/35 text-left text-xs text-muted-foreground"><th className="px-6 py-3 font-medium">Deal name</th><th className="px-4 py-3 font-medium">Stage</th><th className="px-4 py-3 font-medium">Owner</th><th className="px-4 py-3 font-medium">Value</th><th className="px-4 py-3 font-medium">Last activity</th><th className="px-4 py-3 font-medium">Next follow-up</th><th className="px-6 py-3 font-medium">Status</th></tr></thead><tbody>{deals.length === 0 ? <tr><td colSpan={7} className="px-6 py-12 text-center text-muted-foreground">No deals are available yet.</td></tr> : deals.map((deal) => { const followUpOverdue = deal.next_follow_up_at !== null && new Date(deal.next_follow_up_at).getTime() < asOf; return <tr key={deal.id} className="border-b border-border last:border-0"><td className="px-6 py-4 font-medium">{deal.name}</td><td className="px-4 py-4 text-muted-foreground">{deal.stage}</td><td className="px-4 py-4 text-muted-foreground">{deal.owner_name}</td><td className="px-4 py-4 font-medium tabular-nums">{formatCurrency(deal.value)}</td><td className="px-4 py-4 whitespace-nowrap text-muted-foreground">{formatDate(deal.last_activity_at)}</td><td className={`px-4 py-4 whitespace-nowrap ${followUpOverdue ? "font-medium text-destructive" : "text-muted-foreground"}`}>{formatDate(deal.next_follow_up_at)}</td><td className="px-6 py-4"><Badge variant={deal.status.toLowerCase() === "active" ? "secondary" : "outline"}>{deal.status}</Badge></td></tr>; })}</tbody></table></div></CardContent></Card>
            <Card className="shadow-none"><CardHeader><CardTitle>Live activity</CardTitle><CardDescription>Agent and system events</CardDescription></CardHeader><CardContent className="space-y-5">{summary.activity.map((item) => { const Icon = item.kind === "alert" ? AlertTriangle : item.kind === "action" ? CheckCircle2 : Activity; return <div key={item.title} className="flex gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-md bg-secondary"><Icon className="size-4 text-primary" /></span><div><p className="text-sm font-medium">{item.title}</p><p className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.detail}</p><p className="mt-1 text-[11px] text-muted-foreground">{new Date(item.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p></div></div>; })}<Button variant="outline" className="w-full" size="sm">View audit trail</Button></CardContent></Card>
          </section>
        </>}
      </div>
    </div>
  </main>;
}