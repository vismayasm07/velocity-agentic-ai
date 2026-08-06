"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, Clock3, LoaderCircle,
  ShieldAlert, ShieldCheck, UserRound, Users, X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  ApprovalRequest, getApproval, getIncident, getOwnerCapacities,
  reviewApproval, SalesOwnerCapacity,
} from "@/lib/api";

type StoredUser = { email: string; is_admin: boolean };

function getStoredUser(): StoredUser | null {
  if (typeof window === "undefined") return null;
  const storedUser = localStorage.getItem("velocity_user");
  if (!storedUser) return null;
  try {
    return JSON.parse(storedUser) as StoredUser;
  } catch {
    localStorage.removeItem("velocity_user");
    return null;
  }
}

function formatDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }) : "Not available";
}

export default function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const router = useRouter();
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [dealName, setDealName] = useState("");
  const [capacity, setCapacity] = useState<SalesOwnerCapacity | null>(null);
  const [user] = useState<StoredUser | null>(getStoredUser);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [isReviewing, setIsReviewing] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    getApproval(token, approvalId)
      .then(async (result) => {
        setApproval(result);
        const [incident, owners] = await Promise.all([
          getIncident(token, result.incident_id),
          getOwnerCapacities(token),
        ]);
        setDealName(incident.affected_deal?.name ?? "Unavailable deal");
        setCapacity(owners.find((owner) => owner.owner_name === result.proposed_owner) ?? null);
      })
      .catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Approval unavailable"));
  }, [approvalId, router]);

  async function decide(decision: "approve" | "reject") {
    if (!approval || (decision === "reject" && !comment.trim())) return;
    const token = localStorage.getItem("velocity_access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setIsReviewing(true);
    setError("");
    try {
      setApproval(await reviewApproval(token, approval.id, decision, comment.trim()));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Review could not be completed");
    } finally {
      setIsReviewing(false);
    }
  }

  if (!approval && !error) return <main className="grid min-h-svh place-items-center bg-[#f7f6f3]"><LoaderCircle className="size-6 animate-spin text-primary" /></main>;

  if (!approval) return <main className="grid min-h-svh place-items-center bg-[#f7f6f3] px-5"><div className="max-w-md text-center"><AlertTriangle className="mx-auto size-7 text-destructive" /><h1 className="mt-4 text-xl font-semibold">Unable to load approval</h1><p role="alert" className="mt-2 text-sm text-muted-foreground">{error}</p><Button asChild className="mt-5"><Link href="/approvals">Return to inbox</Link></Button></div></main>;

  const isExpired = approval.status === "EXPIRED" || (approval.status === "PENDING" && new Date(approval.expires_at) <= new Date());
  const statusPresentation = {
    PENDING: {
      title: isExpired ? "Approval expired" : "Awaiting an authorized decision",
      detail: isExpired ? "This request passed its authorization window without execution." : `No CRM change occurs before approval. This authorization expires ${formatDateTime(approval.expires_at)}.`,
      tone: "border-amber-200 bg-amber-50 text-amber-900",
      icon: Clock3,
    },
    APPROVED: {
      title: "Approved; provider execution pending",
      detail: approval.review_comment || `Authorized ${formatDateTime(approval.reviewed_at)}. The CRM result is recorded separately.`,
      tone: "border-sky-200 bg-sky-50 text-sky-900",
      icon: ShieldCheck,
    },
    EXECUTED: {
      title: "Approved and executed in CRM",
      detail: approval.review_comment || `Provider execution completed after review ${formatDateTime(approval.reviewed_at)}.`,
      tone: "border-emerald-200 bg-emerald-50 text-emerald-800",
      icon: CheckCircle2,
    },
    REJECTED: {
      title: "Request rejected; no CRM change made",
      detail: approval.review_comment || `Reviewed ${formatDateTime(approval.reviewed_at)}.`,
      tone: "border-zinc-300 bg-zinc-50 text-zinc-800",
      icon: X,
    },
    EXPIRED: {
      title: "Approval expired; no CRM change made",
      detail: `The authorization window ended ${formatDateTime(approval.expires_at)}.`,
      tone: "border-zinc-300 bg-zinc-50 text-zinc-800",
      icon: Clock3,
    },
    EXECUTION_FAILED: {
      title: "Approved, but CRM execution failed",
      detail: approval.review_comment || "The authorization is recorded, but the provider did not confirm the owner change.",
      tone: "border-red-200 bg-red-50 text-red-800",
      icon: AlertTriangle,
    },
  }[approval.status];
  const StatusIcon = statusPresentation.icon;

  return <main className="min-h-svh bg-[#f7f6f3] text-foreground">
    <header className="border-b border-border bg-background"><div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6"><Button asChild variant="ghost" size="sm"><Link href="/approvals"><ArrowLeft /> Approval inbox</Link></Button><Badge variant="outline">{isExpired && approval.status === "PENDING" ? "EXPIRED" : approval.status.replaceAll("_", " ")}</Badge></div></header>

    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
      <section className="border-b border-border pb-7"><div className="flex items-center gap-2 text-sm font-medium text-primary"><ShieldCheck className="size-4" /> Human authorization</div><h1 className="mt-2 text-2xl font-semibold sm:text-3xl">Deal owner reassignment</h1><p className="mt-2 text-sm text-muted-foreground">{dealName || "CRM deal"} · Requested {formatDateTime(approval.created_at)}</p></section>

      {error && <div role="alert" className="mt-6 flex items-center gap-2 border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertTriangle className="size-4" />{error}</div>}
      <div role="status" className={`mt-6 flex items-start gap-3 rounded-md border p-4 ${statusPresentation.tone}`}><StatusIcon className="mt-0.5 size-5 shrink-0" /><div><p className="text-sm font-medium">{statusPresentation.title}</p><p className="mt-1 text-xs leading-5 opacity-80">{statusPresentation.detail}</p></div></div>

      <section className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <Card className="shadow-none"><CardHeader><CardTitle>Ownership change</CardTitle><CardDescription>Current and proposed CRM assignment</CardDescription></CardHeader><CardContent><div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4"><div><span className="grid size-9 place-items-center rounded-md bg-secondary"><UserRound className="size-4" /></span><p className="mt-3 text-xs text-muted-foreground">Current owner</p><p className="mt-1 font-medium">{approval.current_owner}</p></div><ArrowLeft className="size-4 rotate-180 text-muted-foreground" /><div><span className="grid size-9 place-items-center rounded-md bg-emerald-50 text-emerald-700"><Users className="size-4" /></span><p className="mt-3 text-xs text-muted-foreground">Proposed owner</p><p className="mt-1 font-medium">{approval.proposed_owner}</p>{capacity && <p className="mt-1 text-xs text-muted-foreground">{capacity.active_deals}/{capacity.max_active_deals} active deals</p>}</div></div></CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardTitle>Capacity check</CardTitle><CardDescription>Live owner availability</CardDescription></CardHeader><CardContent>{capacity ? <div className="space-y-4"><div className="flex items-center justify-between text-sm"><span>Owner status</span><Badge variant="outline">{capacity.is_active ? "ACTIVE" : "INACTIVE"}</Badge></div><div className="flex items-center justify-between text-sm"><span>Available capacity</span><strong>{capacity.max_active_deals - capacity.active_deals} deals</strong></div><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary" style={{ width: `${Math.min(100, (capacity.active_deals / capacity.max_active_deals) * 100)}%` }} /></div></div> : <p className="text-sm text-muted-foreground">Capacity data is unavailable. The backend will revalidate before execution.</p>}</CardContent></Card>
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2"><Card className="shadow-none"><CardHeader><CardTitle>Recommendation evidence</CardTitle></CardHeader><CardContent><p className="text-sm leading-6">{approval.reason}</p></CardContent></Card><Card className="shadow-none"><CardHeader><CardTitle>Expected outcome</CardTitle></CardHeader><CardContent><p className="text-sm leading-6">{approval.expected_outcome}</p><p className="mt-4 text-xs text-muted-foreground">Gemini supplied advisory evidence only. Authorization is recorded against the reviewing administrator.</p></CardContent></Card></section>

      {approval.status === "PENDING" && <section className="mt-7 border-y border-border bg-background px-5 py-6 sm:px-7"><div className="flex items-center gap-2"><ShieldAlert className="size-5 text-amber-700" /><h2 className="font-semibold">Review decision</h2></div>{isExpired ? <p className="mt-3 text-sm text-muted-foreground">This request is past its authorization window and cannot execute.</p> : user?.is_admin !== true ? <p className="mt-3 text-sm text-muted-foreground">Only an administrator can approve or reject this high-impact action.</p> : <div className="mt-5"><p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">Approval authorizes one reassignment attempt. Velocity revalidates the current owner and target capacity before contacting the configured CRM adapter.</p><Label htmlFor="review-comment" className="mt-5">Review comment</Label><textarea id="review-comment" value={comment} onChange={(event) => setComment(event.target.value)} maxLength={2000} rows={4} placeholder="Record the reasoning for this decision. Required for rejection." className="mt-2 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-3 focus:ring-ring/30" /><div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button variant="outline" onClick={() => void decide("reject")} disabled={isReviewing || !comment.trim()}><X /> Reject request</Button><Button onClick={() => void decide("approve")} disabled={isReviewing}>{isReviewing ? <LoaderCircle className="animate-spin" /> : <Check />}{isReviewing ? "Authorizing and executing" : "Approve and execute"}</Button></div></div>}</section>}
    </div>
  </main>;
}