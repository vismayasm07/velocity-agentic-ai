"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Database,
  ExternalLink,
  Link2,
  LoaderCircle,
  PlugZap,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  beginZohoAuthorization,
  disconnectZoho,
  getZohoStatus,
  syncZohoDeals,
  testZohoConnection,
  ApiError,
  type ZohoConnectionStatus,
  type ZohoDealSyncResult,
} from "@/lib/api";

type Operation = "connect" | "test" | "sync" | "disconnect" | null;

function formatDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not yet";
}

function formatRequestError(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

const requiredScopes = [
  { scope: "ZohoCRM.modules.deals.READ", label: "Deal synchronization", description: "Read Deal records from Zoho" },
  { scope: "ZohoCRM.modules.tasks.CREATE", label: "Follow-up execution", description: "Create governed Tasks in Zoho" },
  { scope: "ZohoCRM.modules.deals.UPDATE", label: "Owner reassignment", description: "Update a Deal after administrator approval" },
  { scope: "ZohoCRM.users.READ", label: "Owner resolution", description: "Resolve active Zoho users before assignment" },
] as const;

function ZohoIntegrationContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<ZohoConnectionStatus | null>(null);
  const [syncResult, setSyncResult] = useState<ZohoDealSyncResult | null>(null);
  const [operation, setOperation] = useState<Operation>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const callbackStatus = searchParams.get("zoho");
  const callbackMessage = callbackStatus === "connected" ? "Zoho CRM connected successfully." : "";
  const callbackError = callbackStatus === "error" ? searchParams.get("reason") ?? "Zoho authorization failed." : "";

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    getZohoStatus(token)
      .then(setStatus)
      .catch((requestError: unknown) => setError(formatRequestError(requestError, "Integration status unavailable")));
  }, [router]);

  function token() {
    const accessToken = localStorage.getItem("velocity_access_token");
    if (!accessToken) router.replace("/login");
    return accessToken;
  }

  async function connect() {
    const accessToken = token();
    if (!accessToken) return;
    setOperation("connect");
    setError("");
    try {
      const result = await beginZohoAuthorization(accessToken);
      window.location.assign(result.authorization_url);
    } catch (requestError) {
      setError(formatRequestError(requestError, "Unable to start authorization"));
      setOperation(null);
    }
  }

  async function testConnection() {
    const accessToken = token();
    if (!accessToken) return;
    setOperation("test");
    setError("");
    try {
      const result = await testZohoConnection(accessToken);
      setMessage(result.message);
    } catch (requestError) {
      setError(formatRequestError(requestError, "Connection test failed"));
    } finally {
      setOperation(null);
    }
  }

  async function synchronize() {
    const accessToken = token();
    if (!accessToken) return;
    setOperation("sync");
    setError("");
    try {
      const result = await syncZohoDeals(accessToken);
      setSyncResult(result);
      setStatus(await getZohoStatus(accessToken));
      setMessage(`Synchronization completed with ${result.failed} failed record${result.failed === 1 ? "" : "s"}.`);
    } catch (requestError) {
      setError(formatRequestError(requestError, "Synchronization failed"));
    } finally {
      setOperation(null);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Zoho CRM and remove the stored OAuth connection?")) return;
    const accessToken = token();
    if (!accessToken) return;
    setOperation("disconnect");
    setError("");
    try {
      const result = await disconnectZoho(accessToken);
      setMessage(result.message);
      setSyncResult(null);
      setStatus(await getZohoStatus(accessToken));
    } catch (requestError) {
      setError(formatRequestError(requestError, "Unable to disconnect Zoho CRM"));
    } finally {
      setOperation(null);
    }
  }

  const scopes = status?.authorized_scopes?.split(",").map((scope) => scope.trim()).filter(Boolean) ?? [];
  const grantedScopes = new Set(scopes.map((scope) => scope.toLowerCase()));
  const hasScope = (scope: string) => grantedScopes.has(scope.toLowerCase());
  const usesZohoAdapter = status?.adapter === "zoho";
  const canSync = status?.connected === true && hasScope("ZohoCRM.modules.deals.READ");
  const canCreateTasks = usesZohoAdapter && hasScope("ZohoCRM.modules.tasks.CREATE") && hasScope("ZohoCRM.users.READ");
  const canReassign = usesZohoAdapter && hasScope("ZohoCRM.modules.deals.UPDATE") && hasScope("ZohoCRM.users.READ");
  const isLoading = status === null && !error;

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="border-b border-border bg-[#211f1d] text-white">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link href="/settings/monitoring" className="grid size-9 place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white" aria-label="Back to settings"><ArrowLeft className="size-4" /></Link>
        <span className="grid size-8 place-items-center rounded-md bg-primary"><PlugZap className="size-4" /></span>
        <div><p className="text-sm font-semibold">Velocity</p><p className="text-[11px] text-white/45">Integrations</p></div>
        <div className="ml-auto flex items-center gap-2 text-xs text-emerald-300"><ShieldCheck className="size-4" /> Admin access</div>
      </div>
    </header>

    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-8 flex flex-col gap-5 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="text-sm font-medium text-primary">CRM connection</p><h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Zoho CRM</h1><p className="mt-2 max-w-2xl text-sm text-muted-foreground">Manage authorization, Deal synchronization, and the permissions used by governed actions.</p></div>
        <Badge variant="outline" className={status?.connected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-zinc-300 bg-white text-zinc-600"}><span className={`size-1.5 rounded-full ${status?.connected ? "bg-emerald-500" : "bg-zinc-400"}`} />{status?.connected ? "Connected" : "Not connected"}</Badge>
      </div>

      {(message || callbackMessage) && <div role="status" className="mb-5 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="size-4 shrink-0" />{message || callbackMessage}</div>}
      {(error || callbackError) && <div role="alert" className="mb-5 flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive"><AlertTriangle className="size-4 shrink-0" />{error || callbackError}</div>}
      {status?.connected && !usesZohoAdapter && <div role="status" className="mb-5 flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><AlertTriangle className="mt-0.5 size-4 shrink-0" /><div><p className="font-medium">Zoho is connected for synchronization, but actions use the local adapter</p><p className="mt-1 text-xs leading-5 text-amber-800">Follow-up and reassignment actions are recorded locally and are not executed in Zoho.</p></div></div>}

      {isLoading ? <div className="flex h-52 items-center justify-center border-y border-border bg-background"><LoaderCircle className="size-5 animate-spin text-primary" /></div> : <div className="bg-background">
        <section className="grid gap-6 border-y border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Connection</h2><p className="mt-1 text-sm text-muted-foreground">OAuth is completed on Zoho. Credentials stay in the backend.</p></div>
          <div className="space-y-5">
            <dl className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2">
              {[{ label: "API domain", value: status?.api_domain ?? "Not connected" }, { label: "Connected", value: formatDateTime(status?.connected_at ?? null) }, { label: "Active adapter", value: status?.adapter === "zoho" ? "Zoho CRM" : "Local fallback" }, { label: "Synchronized Deals", value: String(status?.synchronized_deals ?? 0) }].map((item) => <div key={item.label} className="bg-background p-4"><dt className="text-xs text-muted-foreground">{item.label}</dt><dd className="mt-1 break-words text-sm font-medium">{item.value}</dd></div>)}
            </dl>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => void connect()} disabled={operation !== null}>{operation === "connect" ? <LoaderCircle className="animate-spin" /> : status?.connected ? <RefreshCw /> : <Link2 />}{status?.connected ? "Reconnect permissions" : "Connect Zoho"}</Button>
              {status?.connected && <Button type="button" variant="outline" onClick={() => void testConnection()} disabled={operation !== null}>{operation === "test" ? <LoaderCircle className="animate-spin" /> : <PlugZap />}Test connection</Button>}
            </div>
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Execution readiness</h2><p className="mt-1 text-sm text-muted-foreground">Connection, runtime adapter, and permissions are evaluated independently.</p></div>
          <div className="divide-y divide-border border-y border-border">
            {[
              { label: "OAuth connection", detail: "Authorize provider access", ready: status?.connected === true },
              { label: "Deal synchronization", detail: "Read Deals from Zoho", ready: canSync },
              { label: "Follow-up execution", detail: usesZohoAdapter ? "Create governed Tasks in Zoho" : "Currently handled by the local adapter", ready: canCreateTasks },
              { label: "Owner reassignment", detail: usesZohoAdapter ? "Execute approved owner changes in Zoho" : "Currently handled by the local adapter", ready: canReassign },
            ].map((capability) => <div key={capability.label} className="flex items-center gap-3 py-3"><span className={`grid size-7 shrink-0 place-items-center rounded-full ${capability.ready ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{capability.ready ? <CheckCircle2 className="size-4" /> : <AlertTriangle className="size-4" />}</span><div><p className="text-sm font-medium">{capability.label}</p><p className="text-xs text-muted-foreground">{capability.detail}</p></div><Badge variant="outline" className={`ml-auto ${capability.ready ? "border-emerald-200 text-emerald-700" : "border-amber-200 text-amber-800"}`}>{capability.ready ? "READY" : "UNAVAILABLE"}</Badge></div>)}
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Deal synchronization</h2><p className="mt-1 text-sm text-muted-foreground">Import provider changes, then run deterministic bottleneck detection.</p></div>
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-3"><div><p className="text-xs text-muted-foreground">Last sync</p><p className="mt-1 text-sm font-medium">{formatDateTime(status?.last_sync_at ?? null)}</p></div><div><p className="text-xs text-muted-foreground">Status</p><p className="mt-1 text-sm font-medium">{status?.last_sync_status?.replaceAll("_", " ") ?? "No runs"}</p></div><div><p className="text-xs text-muted-foreground">Latest error</p><p className="mt-1 text-sm font-medium text-destructive">{status?.last_sync_error ?? "None"}</p></div></div>
            {syncResult && <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-5">{(["fetched", "created", "updated", "unchanged", "failed"] as const).map((key) => <div key={key} className="bg-[#fafaf8] p-3 text-center"><p className="text-lg font-semibold tabular-nums">{syncResult[key]}</p><p className="text-[11px] capitalize text-muted-foreground">{key}</p></div>)}</div>}
            <div><Button type="button" variant="outline" onClick={() => void synchronize()} disabled={!canSync || operation !== null} title={!status?.connected ? "Connect Zoho before synchronizing" : !hasScope("ZohoCRM.modules.deals.READ") ? "Reconnect Zoho with Deal read permission" : undefined}>{operation === "sync" ? <LoaderCircle className="animate-spin" /> : <Database />}{operation === "sync" ? "Synchronizing..." : "Sync Deals now"}</Button>{!canSync && <p className="mt-2 text-xs text-amber-700">{!status?.connected ? "Connect Zoho to enable synchronization." : "Deal read permission is required to synchronize."}</p>}</div>
          </div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Granted permissions</h2><p className="mt-1 text-sm text-muted-foreground">Velocity requests only the provider capabilities configured by the administrator.</p></div>
          <div>{status?.connected ? <ul className="divide-y divide-border border-y border-border">{requiredScopes.map(({ scope, label, description }) => { const granted = hasScope(scope); return <li key={scope} className="flex items-center gap-3 py-3"><span className={`grid size-7 shrink-0 place-items-center rounded-full ${granted ? "bg-emerald-50 text-emerald-700" : "bg-secondary text-muted-foreground"}`}>{granted ? <CheckCircle2 className="size-4" /> : <AlertTriangle className="size-4" />}</span><div><p className="text-sm font-medium">{label}</p><p className="text-xs text-muted-foreground">{description}</p></div><span className={`ml-auto text-xs font-medium ${granted ? "text-emerald-700" : "text-amber-700"}`}>{granted ? "Granted" : "Not granted"}</span></li>; })}</ul> : <p className="text-sm text-muted-foreground">Connect Zoho to review granted permissions.</p>}</div>
        </section>

        <section className="grid gap-6 border-b border-border px-5 py-6 md:grid-cols-[minmax(220px,0.7fr)_1.3fr] md:px-7">
          <div><h2 className="font-semibold">Disconnect</h2><p className="mt-1 text-sm text-muted-foreground">Revoke provider access and remove encrypted tokens from Velocity.</p></div>
          <div className="flex flex-col gap-4 rounded-md border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-medium text-red-900">Remove Zoho connection</p><p className="mt-1 text-xs leading-5 text-red-700">Synchronized local records remain available. New provider reads and writes stop immediately.</p></div><Button type="button" variant="destructive" onClick={() => void disconnect()} disabled={!status?.connected || operation !== null}>{operation === "disconnect" ? <LoaderCircle className="animate-spin" /> : <Unplug />}Disconnect</Button></div>
        </section>

        <div className="flex items-center justify-between px-5 py-4 text-xs text-muted-foreground md:px-7"><span>Zoho CRM API v8</span><a className="inline-flex items-center gap-1 text-primary hover:underline" href="https://www.zoho.com/crm/developer/docs/api/v8/" target="_blank" rel="noreferrer">Provider documentation<ExternalLink className="size-3" /></a></div>
      </div>}
    </div>
  </main>;
}

export default function ZohoIntegrationPage() {
  return <Suspense fallback={<main className="grid min-h-svh place-items-center bg-[#f7f6f3]"><LoaderCircle className="size-5 animate-spin text-primary" /></main>}><ZohoIntegrationContent /></Suspense>;
}