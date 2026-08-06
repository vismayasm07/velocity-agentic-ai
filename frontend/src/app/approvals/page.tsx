"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Clock3, Inbox, LoaderCircle,
  ShieldCheck, UserRoundCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApprovalRequest, ApprovalStatus, getApprovals } from "@/lib/api";

const filters: Array<{ label: string; value: "ALL" | ApprovalStatus }> = [
  { label: "All", value: "ALL" },
  { label: "Pending", value: "PENDING" },
  { label: "Approved", value: "APPROVED" },
  { label: "Executed", value: "EXECUTED" },
  { label: "Rejected", value: "REJECTED" },
  { label: "Expired", value: "EXPIRED" },
  { label: "Failed", value: "EXECUTION_FAILED" },
];

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ApprovalInboxPage() {
  const [approvals, setApprovals] = useState<ApprovalRequest[] | null>(null);
  const [filter, setFilter] = useState<"ALL" | ApprovalStatus>("PENDING");
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    getApprovals(token)
      .then(setApprovals)
      .catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Approvals unavailable"));
  }, [router]);

  const visible = approvals?.filter((approval) => filter === "ALL" || approval.status === filter) ?? [];
  const pendingCount = approvals?.filter((approval) => approval.status === "PENDING").length ?? 0;

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="border-b border-border bg-[#211f1d] text-white">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link href="/dashboard" className="grid size-9 place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white" aria-label="Back to dashboard"><ArrowLeft className="size-4" /></Link>
        <span className="grid size-8 place-items-center rounded-md bg-primary"><Inbox className="size-4" /></span>
        <div><p className="text-sm font-semibold">Approval inbox</p><p className="text-[11px] text-white/45">High-impact actions</p></div>
        <div className="ml-auto flex items-center gap-2 text-xs text-amber-200"><ShieldCheck className="size-4" /> Human review required</div>
      </div>
    </header>

    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <section className="flex flex-col gap-5 border-b border-border pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="text-sm font-medium text-primary">Decision queue</p><h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Deal owner reassignments</h1><p className="mt-2 max-w-2xl text-sm text-muted-foreground">Review the recommendation and current CRM state before authorizing any ownership change.</p></div>
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"><Clock3 className="size-4" /><strong>{pendingCount}</strong> pending</div>
      </section>

      <div className="mt-6 flex flex-wrap gap-2" aria-label="Approval status filters">{filters.map((item) => <Button key={item.value} size="sm" variant={filter === item.value ? "default" : "outline"} onClick={() => setFilter(item.value)}>{item.label}</Button>)}</div>

      {error && <div role="alert" className="mt-6 flex items-center gap-2 border-y border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertTriangle className="size-4" />{error}</div>}
      {!approvals && !error && <div className="mt-6 flex h-48 items-center justify-center border-y border-border bg-background"><LoaderCircle className="size-5 animate-spin text-primary" /></div>}
      {approvals && visible.length === 0 && <div className="mt-6 border-y border-border bg-background px-5 py-16 text-center"><Inbox className="mx-auto size-6 text-muted-foreground" /><p className="mt-3 text-sm font-medium">{filter === "PENDING" ? "No decisions awaiting review" : "No approvals in this view"}</p><p className="mt-1 text-xs text-muted-foreground">{filter === "PENDING" ? "High-impact actions remain blocked until a request appears and an administrator approves it." : "Choose another status to review previous authorization activity."}</p></div>}

      {visible.length > 0 && <div className="mt-6 divide-y divide-border border-y border-border bg-background">{visible.map((approval) => <Link href={`/approvals/${approval.id}`} key={approval.id} className="grid gap-4 px-4 py-5 transition-colors hover:bg-secondary/40 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-6"><div className="flex gap-4"><span className="grid size-10 shrink-0 place-items-center rounded-md bg-secondary"><UserRoundCheck className="size-5" /></span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{approval.current_owner} to {approval.proposed_owner}</p><Badge variant={approval.status === "EXECUTION_FAILED" ? "destructive" : "outline"}>{approval.status.replaceAll("_", " ")}</Badge></div><p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{approval.reason}</p><p className="mt-2 text-xs text-muted-foreground">Requested {formatDateTime(approval.created_at)} · Expires {formatDateTime(approval.expires_at)}</p></div></div><div className="flex items-center gap-2 self-center text-xs font-medium text-primary">{approval.status === "EXECUTED" && <CheckCircle2 className="size-4 text-emerald-700" />}Open review</div></Link>)}</div>}
    </div>
  </main>;
}