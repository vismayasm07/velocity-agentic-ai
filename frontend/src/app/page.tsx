import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Check, ChevronRight, CircleAlert, Gauge, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";

const heroImage = "https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=2400&q=85";
const features = [
  { icon: Gauge, title: "Detect sooner", copy: "Surface stalled deals, overloaded owners, and failing syncs while there is still time to act." },
  { icon: Sparkles, title: "Understand why", copy: "Turn CRM history and operating policies into concise, evidence-backed root cause analysis." },
  { icon: ShieldCheck, title: "Act with control", copy: "Keep every recommendation behind approval rules, entity limits, and a complete audit trail." },
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-background">
      <section className="relative min-h-[92svh] border-b border-border">
        <Image src={heroImage} alt="Sales team reviewing CRM pipeline performance together" fill priority unoptimized sizes="100vw" className="object-cover object-[68%_center]" />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(253,251,248,0.99)_0%,rgba(253,251,248,0.95)_40%,rgba(253,251,248,0.48)_68%,rgba(253,251,248,0.14)_100%)]" />
        <div className="absolute inset-x-0 top-0 z-20 border-b border-black/5 bg-background/80 backdrop-blur-md">
          <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
            <Link href="/" className="flex items-center gap-2.5" aria-label="Velocity home">
              <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground shadow-sm"><TrendingUp className="size-4" /></span>
              <span className="text-lg font-semibold">Velocity</span>
            </Link>
            <div className="hidden items-center gap-8 text-sm text-muted-foreground md:flex">
              <a href="#platform" className="transition-colors hover:text-foreground">Platform</a>
              <a href="#outcomes" className="transition-colors hover:text-foreground">Outcomes</a>
              <a href="#security" className="transition-colors hover:text-foreground">Security</a>
            </div>
            <Button asChild size="lg" className="h-9 px-4 shadow-sm"><Link href="/login">Sign in <ArrowRight data-icon="inline-end" /></Link></Button>
          </nav>
        </div>
        <div className="relative z-10 mx-auto flex min-h-[92svh] max-w-7xl items-center px-5 pb-20 pt-28 sm:px-8">
          <div className="max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="mb-6 inline-flex items-center gap-2 border-l-2 border-primary pl-3 text-sm font-medium text-primary"><Sparkles className="size-4" /> Proactive CRM operations intelligence</div>
            <h1 className="max-w-xl text-5xl font-semibold leading-[1.04] text-balance sm:text-6xl lg:text-7xl">Keep every deal moving.</h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-muted-foreground sm:text-xl">Velocity finds pipeline bottlenecks before they cost you revenue, explains what is slowing work down, and recommends the next best action.</p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg" className="h-11 px-5 text-base shadow-lg shadow-primary/15"><Link href="/login">Open your workspace <ArrowRight data-icon="inline-end" /></Link></Button>
              <Button asChild variant="outline" size="lg" className="h-11 bg-background/80 px-5 text-base backdrop-blur-sm"><a href="#platform">Explore the platform <ChevronRight data-icon="inline-end" /></a></Button>
            </div>
            <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-sm text-foreground/75">
              {["Early risk detection", "Evidence-backed RCA", "Guarded actions"].map((item) => <span key={item} className="flex items-center gap-2"><Check className="size-4 text-primary" /> {item}</span>)}
            </div>
          </div>
        </div>
        <div className="absolute inset-x-0 bottom-0 z-10 h-2 bg-primary" />
      </section>

      <section id="platform" className="bg-[#211f1d] py-20 text-white sm:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 px-5 sm:px-8 lg:grid-cols-[0.78fr_1.22fr] lg:items-center">
          <div>
            <p className="text-sm font-medium text-[#ff766b]">One operating view</p>
            <h2 className="mt-4 max-w-md text-3xl font-semibold leading-tight sm:text-4xl">See the pressure building before the pipeline stalls.</h2>
            <p className="mt-5 max-w-md leading-7 text-white/60">Live signals connect workload, deal inactivity, approvals, and sync health into a clear operational picture.</p>
          </div>
          <div className="overflow-hidden rounded-lg border border-white/10 bg-[#292624] shadow-2xl">
            <div className="flex h-12 items-center justify-between border-b border-white/10 px-4 sm:px-5">
              <div className="flex items-center gap-2 text-sm font-medium"><Gauge className="size-4 text-[#ff766b]" /> Pipeline pulse</div>
              <span className="flex items-center gap-2 text-xs text-white/50"><span className="size-1.5 rounded-full bg-emerald-400" /> Live</span>
            </div>
            <div className="grid gap-px bg-white/10 sm:grid-cols-3">
              {[["At-risk deals", "12", "+3 today"], ["Pipeline health", "87%", "+4.2%"], ["SLA protected", "$284k", "this week"]].map(([label, value, note]) => (
                <div key={label} className="bg-[#292624] p-5"><p className="text-xs text-white/50">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-[#ff938a]">{note}</p></div>
              ))}
            </div>
            <div className="p-4 sm:p-5">
              <div className="rounded-md border border-[#b83b34]/35 bg-[#3a2825] p-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-[#b83b34] text-white"><CircleAlert className="size-4" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">Enterprise pipeline at risk</p><span className="text-xs text-[#ff938a]">Risk score 82</span></div>
                    <p className="mt-1 text-sm leading-6 text-white/55">Five deals are waiting on the same approval owner, whose workload is 34% over capacity.</p>
                    <div className="mt-4 flex flex-wrap gap-2 text-xs"><span className="rounded border border-white/10 bg-white/5 px-2 py-1">Root cause verified</span><span className="rounded border border-white/10 bg-white/5 px-2 py-1">Reassignment ready</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="outcomes" className="border-b border-border py-20 sm:py-24">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 sm:px-8 md:grid-cols-3">
          {features.map(({ icon: FeatureIcon, title, copy }) => <article key={title} className="border-t-2 border-primary pt-6"><FeatureIcon className="size-5 text-primary" /><h3 className="mt-5 text-xl font-semibold">{title}</h3><p className="mt-3 leading-7 text-muted-foreground">{copy}</p></article>)}
        </div>
      </section>
      <section id="security" className="bg-secondary py-16">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 sm:px-8 md:flex-row md:items-center md:justify-between">
          <div className="max-w-2xl"><p className="text-sm font-medium text-primary">Built for accountable automation</p><h2 className="mt-2 text-2xl font-semibold sm:text-3xl">Move faster without giving up control.</h2></div>
          <Button asChild size="lg" className="h-11 self-start px-5 md:self-auto"><Link href="/login">Access Velocity <ArrowRight data-icon="inline-end" /></Link></Button>
        </div>
      </section>
      <footer className="border-t border-border bg-background"><div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-7 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-8"><div className="flex items-center gap-2 font-medium text-foreground"><TrendingUp className="size-4 text-primary" /> Velocity CRM Agent</div><p>Proactive intelligence for revenue operations.</p></div></footer>
    </main>
  );
}
