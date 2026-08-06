"use client";

import { useState } from "react";
import { Bot, Check, Clipboard, Cpu, ShieldCheck, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AgentAuditEvent } from "@/lib/api";

function titleCase(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function eventSource(event: AgentAuditEvent) {
  const explicitSource = event.details.source ?? event.details.execution_source ?? event.details.actor;
  if (typeof explicitSource === "string" && explicitSource.trim()) return titleCase(explicitSource);
  if (event.event_type.includes("APPROV") || event.event_type.includes("REJECT")) return "Administrator";
  if (event.analysis_id || event.event_type.includes("ANALYSIS")) return "AI recommendation";
  if (event.monitoring_run_id || event.event_type.includes("DETECT")) return "Deterministic monitor";
  return "Velocity system";
}

function SourceIcon({ source }: { source: string }) {
  if (source === "Administrator") return <UserRound className="size-4" />;
  if (source === "AI recommendation") return <Bot className="size-4" />;
  if (source === "Deterministic monitor") return <Cpu className="size-4" />;
  return <ShieldCheck className="size-4" />;
}

export function AuditTimeline({ events, formatDateTime }: { events: AgentAuditEvent[]; formatDateTime: (value: string | null) => string }) {
  const [copiedId, setCopiedId] = useState("");

  if (events.length === 0) {
    return <div className="border-y border-border py-8 text-center"><p className="text-sm font-medium">No audit events recorded</p><p className="mt-1 text-xs text-muted-foreground">Events will appear after detection or an action attempt.</p></div>;
  }

  async function copyId(id: string) {
    await navigator.clipboard.writeText(id);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((current) => current === id ? "" : current), 1500);
  }

  return <ol className="divide-y divide-border border-y border-border">
    {events.map((event) => {
      const source = eventSource(event);
      const failed = event.status.toLowerCase().includes("fail");
      return <li key={event.id} className="flex gap-3 py-4">
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-secondary text-muted-foreground"><SourceIcon source={source} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><p className="text-sm font-medium">{titleCase(event.event_type)}</p><Badge variant={failed ? "destructive" : "outline"}>{titleCase(event.status)}</Badge></div>
          <p className="mt-1 text-xs text-muted-foreground">{source} · {formatDateTime(event.created_at)}</p>
          <div className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground"><span className="truncate font-mono">{event.id}</span><Button type="button" variant="ghost" size="icon" className="size-7 shrink-0" onClick={() => void copyId(event.id)} aria-label="Copy audit correlation ID" title="Copy correlation ID">{copiedId === event.id ? <Check className="size-3.5 text-emerald-700" /> : <Clipboard className="size-3.5" />}</Button></div>
        </div>
      </li>;
    })}
  </ol>;
}