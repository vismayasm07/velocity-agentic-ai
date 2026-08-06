"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  LoaderCircle,
  Radar,
  Save,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getMonitoringSettings,
  MonitoringSettingsUpdate,
  updateMonitoringSettings,
} from "@/lib/api";

const fields = [
  {
    key: "scan_interval_seconds",
    label: "Scan interval",
    unit: "seconds",
    min: 5,
    max: 3600,
  },
  {
    key: "stage_sla_hours",
    label: "Stage SLA",
    unit: "hours",
    min: 1,
    max: 8760,
  },
  {
    key: "inactivity_threshold_hours",
    label: "Inactivity threshold",
    unit: "hours",
    min: 1,
    max: 8760,
  },
  {
    key: "automatic_rca_min_risk_score",
    label: "Minimum risk score",
    unit: "points",
    min: 0,
    max: 100,
  },
  {
    key: "owner_max_active_deals",
    label: "Maximum active deals",
    unit: "deals",
    min: 1,
    max: 10000,
  },
  {
    key: "owner_max_high_risk_deals",
    label: "Maximum high-risk deals",
    unit: "deals",
    min: 1,
    max: 10000,
  },
  {
    key: "owner_max_overdue_follow_ups",
    label: "Maximum overdue follow-ups",
    unit: "deals",
    min: 1,
    max: 10000,
  },
  {
    key: "follow_up_due_hours",
    label: "Follow-up due window",
    unit: "hours",
    min: 1,
    max: 720,
  },
  {
    key: "outcome_check_delay_minutes",
    label: "First check delay",
    unit: "minutes",
    min: 1,
    max: 10080,
  },
  {
    key: "maximum_outcome_checks",
    label: "Maximum checks",
    unit: "checks",
    min: 1,
    max: 20,
  },
  {
    key: "resolution_risk_threshold",
    label: "Resolution threshold",
    unit: "points",
    min: 0,
    max: 100,
  },
] as const;

export default function MonitoringSettingsPage() {
  const [form, setForm] = useState<MonitoringSettingsUpdate | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    getMonitoringSettings(token)
      .then((settings) => {
        setForm(settings);
        setUpdatedAt(settings.updated_at);
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : "Settings unavailable");
      })
      .finally(() => setIsLoading(false));
  }, [router]);

  const validationError = form
    ? fields.find(({ key, min, max }) => form[key] < min || form[key] > max)
    : undefined;

  async function saveSettings() {
    if (!form || validationError) return;
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setError("");
    setSuccess("");
    setIsSaving(true);
    try {
      const saved = await updateMonitoringSettings(token, form);
      setForm(saved);
      setUpdatedAt(saved.updated_at);
      setSuccess("Monitoring settings saved. Scheduler changes are active immediately; the next cycle will use the updated detection policy.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save settings");
    } finally {
      setIsSaving(false);
    }
  }

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="border-b border-border bg-[#211f1d] text-white">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link href="/dashboard" className="grid size-9 place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white" aria-label="Back to dashboard"><ArrowLeft className="size-4" /></Link>
        <span className="grid size-8 place-items-center rounded-md bg-primary"><Radar className="size-4" /></span>
        <div><p className="text-sm font-semibold">Velocity</p><p className="text-[11px] text-white/45">Administration</p></div>
        <div className="ml-auto flex items-center gap-2 text-xs text-emerald-300"><ShieldCheck className="size-4" /> Admin access</div>
      </div>
    </header>

    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-8 border-b border-border pb-6">
        <p className="text-sm font-medium text-primary">Proactive monitoring</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Monitoring settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Control scan cadence and the deterministic rules used to identify stalled deals.</p>
      </div>

      {success && <div role="status" className="mb-5 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="size-4 shrink-0" />{success}</div>}
      {error && <div role="alert" className="mb-5 flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive"><AlertTriangle className="size-4 shrink-0" />{error}</div>}

      {isLoading ? <div className="flex h-52 items-center justify-center border-y border-border bg-background"><LoaderCircle className="size-5 animate-spin text-primary" /></div> : form ? <form onSubmit={(event) => { event.preventDefault(); void saveSettings(); }} className="bg-background">
        <section className="grid gap-6 border-y border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Scheduler</h2><p className="mt-1 text-sm text-muted-foreground">Pause or adjust the recurring scan loop.</p></div>
          <div className="space-y-6">
            <label className="flex cursor-pointer items-center justify-between gap-4 border-b border-border pb-5">
              <span><span className="block text-sm font-medium">Continuous monitoring</span><span className="mt-1 block text-xs text-muted-foreground">Run deterministic bottleneck scans automatically.</span></span>
              <Checkbox checked={form.monitoring_enabled} onCheckedChange={(checked) => setForm({ ...form, monitoring_enabled: checked === true })} aria-label="Enable continuous monitoring" />
            </label>
            {fields.slice(0, 1).map(({ key, label, unit, min, max }) => <div key={key} className="max-w-sm"><Label htmlFor={key}>{label}</Label><div className="mt-2 flex items-center gap-3"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="tabular-nums" /><span className="w-16 text-sm text-muted-foreground">{unit}</span></div><p className="mt-1.5 text-xs text-muted-foreground">Allowed range: {min}-{max} seconds.</p></div>)}
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Owner workload</h2><p className="mt-1 text-sm text-muted-foreground">Detect overloaded active owners from their current CRM portfolio.</p></div>
          <div className="space-y-6">
            <label className="flex cursor-pointer items-center justify-between gap-4 border-b border-border pb-5"><span><span className="block text-sm font-medium">Owner overload detection</span><span className="mt-1 block text-xs text-muted-foreground">Evaluate active deals, high-risk deals, overdue follow-ups, and pipeline value.</span></span><Checkbox checked={form.owner_overload_enabled} onCheckedChange={(checked) => setForm({ ...form, owner_overload_enabled: checked === true })} aria-label="Enable owner overload detection" /></label>
            <div className="grid gap-5 sm:grid-cols-3">{fields.slice(4, 7).map(({ key, label, unit, min, max }) => <div key={key}><Label htmlFor={key}>{label}</Label><div className="mt-2"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="tabular-nums" /></div><p className="mt-1.5 text-xs text-muted-foreground">{unit} · {min}-{max}</p></div>)}</div>
            <div className="max-w-sm"><Label htmlFor="owner_max_pipeline_value">Maximum pipeline value</Label><div className="mt-2 flex items-center gap-3"><Input id="owner_max_pipeline_value" type="number" min={1} value={form.owner_max_pipeline_value ?? ""} placeholder="Disabled" onChange={(event) => setForm({ ...form, owner_max_pipeline_value: event.target.value || null })} /><span className="text-sm text-muted-foreground">USD</span></div><p className="mt-1.5 text-xs text-muted-foreground">Leave blank to disable this signal.</p></div>
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Detection policy</h2><p className="mt-1 text-sm text-muted-foreground">Define when stage age and inactivity contribute to deal risk.</p></div>
          <div className="grid gap-6 sm:grid-cols-2">
            {fields.slice(1, 3).map(({ key, label, unit, min, max }) => <div key={key}><Label htmlFor={key}>{label}</Label><div className="mt-2 flex items-center gap-3"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="tabular-nums" /><span className="w-12 text-sm text-muted-foreground">{unit}</span></div></div>)}
            <label className="flex cursor-pointer items-center justify-between gap-4 border-t border-border pt-5 sm:col-span-2"><span><span className="block text-sm font-medium">Overdue follow-up signal</span><span className="mt-1 block text-xs text-muted-foreground">Include overdue next actions in risk scoring.</span></span><Checkbox checked={form.overdue_follow_up_enabled} onCheckedChange={(checked) => setForm({ ...form, overdue_follow_up_enabled: checked === true })} aria-label="Enable overdue follow-up signal" /></label>
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">AI analysis</h2><p className="mt-1 text-sm text-muted-foreground">Automatically generate grounded recommendations for newly detected high-risk incidents.</p></div>
          <div className="space-y-6">
            <label className="flex cursor-pointer items-center justify-between gap-4 border-b border-border pb-5"><span><span className="block text-sm font-medium">Automatic AI analysis</span><span className="mt-1 block text-xs text-muted-foreground">Run Gemini RCA after deterministic detection.</span></span><Checkbox checked={form.automatic_rca_enabled} onCheckedChange={(checked) => setForm({ ...form, automatic_rca_enabled: checked === true })} aria-label="Enable automatic AI analysis" /></label>
            {fields.slice(3, 4).map(({ key, label, unit, min, max }) => <div key={key} className="max-w-sm"><Label htmlFor={key}>{label}</Label><div className="mt-2 flex items-center gap-3"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="tabular-nums" /><span className="w-16 text-sm text-muted-foreground">{unit}</span></div><p className="mt-1.5 text-xs text-muted-foreground">Incidents at or above this score are analyzed automatically.</p></div>)}
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Safe actions</h2><p className="mt-1 text-sm text-muted-foreground">Allow narrowly scoped follow-up creation after an eligible analysis.</p></div>
          <div className="space-y-6">
            <label className="flex cursor-pointer items-center justify-between gap-4 border-b border-border pb-5"><span><span className="block text-sm font-medium">Automatic safe actions</span><span className="mt-1 block text-xs text-muted-foreground">Create follow-up tasks only when RCA recommends it without approval.</span></span><Checkbox checked={form.automatic_safe_actions_enabled} onCheckedChange={(checked) => setForm({ ...form, automatic_safe_actions_enabled: checked === true })} aria-label="Enable automatic safe actions" /></label>
            {fields.slice(7, 8).map(({ key, label, unit, min, max }) => <div key={key} className="max-w-sm"><Label htmlFor={key}>{label}</Label><div className="mt-2 flex items-center gap-3"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="tabular-nums" /><span className="w-16 text-sm text-muted-foreground">{unit}</span></div><p className="mt-1.5 text-xs text-muted-foreground">Allowed range: {min}-{max} hours.</p></div>)}
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Outcome verification</h2><p className="mt-1 text-sm text-muted-foreground">Recheck CRM evidence after an action and resolve incidents only when deterministic risk clears.</p></div>
          <div className="space-y-6">
            <label className="flex cursor-pointer items-center justify-between gap-4 border-b border-border pb-5"><span><span className="block text-sm font-medium">Automatic outcome checks</span><span className="mt-1 block text-xs text-muted-foreground">Collect fresh CRM evidence during monitoring cycles.</span></span><Checkbox checked={form.outcome_verification_enabled} onCheckedChange={(checked) => setForm({ ...form, outcome_verification_enabled: checked === true })} aria-label="Enable automatic outcome checks" /></label>
            <div className="grid gap-5 sm:grid-cols-3">{fields.slice(8).map(({ key, label, unit, min, max }) => <div key={key}><Label htmlFor={key}>{label}</Label><div className="mt-2 flex items-center gap-2"><Input id={key} type="number" min={min} max={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} className="min-w-0 tabular-nums" /></div><p className="mt-1.5 text-xs text-muted-foreground">{unit} · {min}-{max}</p></div>)}</div>
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">High-impact actions</h2><p className="mt-1 text-sm text-muted-foreground">Emergency control for actions that modify CRM ownership.</p></div>
          <label className="flex cursor-pointer items-center justify-between gap-4 rounded-md border border-red-200 bg-red-50 p-4">
            <span><span className="block text-sm font-medium text-red-900">Disable high-impact actions</span><span className="mt-1 block text-xs leading-5 text-red-700">Blocks approved owner reassignments from executing. Pending requests remain available for review.</span></span>
            <Checkbox checked={form.high_impact_actions_disabled} onCheckedChange={(checked) => setForm({ ...form, high_impact_actions_disabled: checked === true })} aria-label="Disable high-impact actions" />
          </label>
        </section>

        <div className="flex flex-col gap-3 px-5 py-5 sm:flex-row sm:items-center sm:justify-between md:px-7">
          <p className="text-xs text-muted-foreground">{validationError ? `${validationError.label} must be between ${validationError.min} and ${validationError.max}.` : updatedAt ? `Last saved ${new Date(updatedAt).toLocaleString()} · No restart required` : ""}</p>
          <Button type="submit" disabled={isSaving || Boolean(validationError)}>{isSaving ? <LoaderCircle className="animate-spin" /> : <Save />} {isSaving ? "Saving..." : "Save settings"}</Button>
        </div>
      </form> : <div className="border-y border-border bg-background p-8 text-center text-sm text-muted-foreground">Settings could not be loaded.</div>}
    </div>
  </main>;
}