"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Eye, EyeOff, LoaderCircle, ShieldCheck, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { login } from "@/lib/api";

const loginImage = "https://images.unsplash.com/photo-1556761175-b413da4baf72?auto=format&fit=crop&w=1800&q=85";

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    const form = new FormData(event.currentTarget);
    try {
      const response = await login(String(form.get("email")), String(form.get("password")));
      localStorage.setItem("velocity_access_token", response.access_token);
      localStorage.setItem("velocity_user", JSON.stringify(response.user));
      router.push("/dashboard");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Sign in failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-svh bg-background lg:grid-cols-[1.08fr_0.92fr]">
      <section className="relative hidden min-h-svh overflow-hidden lg:block">
        <Image src={loginImage} alt="Revenue operations team collaborating in a bright office" fill priority unoptimized sizes="54vw" className="object-cover" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(28,25,23,0.05)_30%,rgba(28,25,23,0.84)_100%)]" />
        <div className="absolute inset-x-0 bottom-0 p-10 text-white xl:p-14">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-2 text-sm font-medium text-white/75"><ShieldCheck className="size-4 text-[#ff766b]" /> Secure operations workspace</span>
            <blockquote className="mt-5 text-3xl font-medium leading-tight text-balance xl:text-4xl">The best bottleneck is the one your team resolves before the customer ever feels it.</blockquote>
            <p className="mt-5 text-sm text-white/65">Velocity Operations Intelligence</p>
          </div>
        </div>
      </section>
      <section className="relative flex min-h-svh flex-col">
        <header className="flex h-16 items-center justify-between px-5 sm:px-8 lg:px-10">
          <Link href="/" className="flex items-center gap-2.5" aria-label="Velocity home"><span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><TrendingUp className="size-4" /></span><span className="font-semibold">Velocity</span></Link>
          <Button asChild variant="ghost" size="sm"><Link href="/"><ArrowLeft data-icon="inline-start" /> Back home</Link></Button>
        </header>
        <div className="flex flex-1 items-center justify-center px-5 py-10 sm:px-8 lg:px-12">
          <div className="w-full max-w-md animate-in fade-in slide-in-from-bottom-3 duration-500">
            <div className="mb-8"><p className="text-sm font-medium text-primary">Welcome back</p><h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Sign in to Velocity</h1><p className="mt-3 text-muted-foreground">Access your live pipeline and operations workspace.</p></div>
            <form className="space-y-5" onSubmit={handleSubmit}>
              <div className="space-y-2"><Label htmlFor="email">Work email</Label><Input id="email" name="email" type="email" autoComplete="email" placeholder="you@company.com" className="h-11 px-3" required /></div>
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-4"><Label htmlFor="password">Password</Label><a href="#" className="text-sm font-medium text-primary hover:underline">Forgot password?</a></div>
                <div className="relative">
                  <Input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="Enter your password" className="h-11 px-3 pr-11" required />
                  <Button type="button" variant="ghost" size="icon" className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff /> : <Eye />}</Button>
                </div>
              </div>
              <div className="flex items-center gap-2.5"><Checkbox id="remember" /><Label htmlFor="remember" className="font-normal text-muted-foreground">Keep me signed in</Label></div>
              {error && <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p>}
              <Button type="submit" size="lg" disabled={isSubmitting} className="h-11 w-full text-base shadow-lg shadow-primary/15">{isSubmitting ? <LoaderCircle className="animate-spin" /> : <>Sign in <ArrowRight data-icon="inline-end" /></>}</Button>
            </form>
            <div className="my-8 flex items-center gap-4"><Separator className="flex-1" /><span className="text-xs text-muted-foreground">Protected access</span><Separator className="flex-1" /></div>
            <p className="text-center text-sm leading-6 text-muted-foreground">Need access to your organization?{" "}<a href="mailto:admin@velocitycrm.com" className="font-medium text-foreground hover:text-primary">Contact your administrator</a></p>
          </div>
        </div>
        <footer className="px-5 py-6 text-center text-xs text-muted-foreground sm:px-8">By continuing, you agree to your organization&apos;s access policies.</footer>
      </section>
    </main>
  );
}