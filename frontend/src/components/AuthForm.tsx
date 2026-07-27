"use client";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Input } from "@saiife/ui";
import { ApiException, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { loginWithPasskey } from "@/lib/passkey";

type Mode = "signup" | "login";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

const TABS = ["passkey", "google", "password"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = { passkey: "passkey", google: "google", password: "email" };

export function AuthForm({ mode }: { mode: Mode }) {
  const [tab, setTab] = useState<Tab>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [verifyEmailSent, setVerifyEmailSent] = useState(false);
  const router = useRouter();
  const { refresh } = useAuth();

  async function submitPassword(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await api("/api/v1/auth/signup", { method: "POST", json: { email, password } });
        setVerifyEmailSent(true);
      } else {
        await api("/api/v1/auth/login", { method: "POST", json: { email, password } });
        await refresh();
        router.push("/dashboard");
      }
    } catch (e) {
      if (e instanceof ApiException) {
        setError(
          e.code === "email_unverified"
            ? "Verify your email before signing in."
            : e.code === "email_taken"
              ? "An account with this email already exists."
              : e.code === "invalid_credentials"
                ? "Email or password is incorrect."
                : e.message,
        );
      } else {
        setError("Something went wrong — try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function startGoogle() {
    window.location.href = `${API_URL}/api/v1/auth/google/start`;
  }

  async function doPasskey() {
    setError(null);
    setSubmitting(true);
    try {
      await loginWithPasskey();
      await refresh();
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof ApiException ? e.message : "Passkey login was cancelled or failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (verifyEmailSent) {
    return (
      <div className="frame ticks px-6 py-8 text-center">
        <div className="briefing-label mx-auto w-fit">check your inbox</div>
        <p className="mt-4 font-mono text-xs leading-relaxed text-muted-foreground">
          We sent a verification link to <span className="text-foreground/80">{email}</span>. Click
          it to finish signing up.
        </p>
      </div>
    );
  }

  return (
    <div className="frame ticks space-y-5 px-6 py-7">
      <div className="grid grid-cols-3 gap-1.5">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`stamp rounded border py-1.5 text-[10px] uppercase tracking-wide transition-colors ${
              tab === t
                ? "border-foreground/40 text-foreground"
                : "border-border text-muted-foreground hover:border-border/70 hover:text-foreground/70"
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === "password" && (
        <form onSubmit={submitPassword} className="space-y-4">
          <div>
            <label className="briefing-label" htmlFor="email">
              email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-2 h-10 font-mono"
            />
          </div>
          <div>
            <label className="briefing-label" htmlFor="pw">
              password
            </label>
            <Input
              id="pw"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-2 h-10 font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
          >
            <span>{submitting ? "Working…" : mode === "signup" ? "Create account" : "Sign in"}</span>
            <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
          </button>
        </form>
      )}

      {tab === "google" && (
        <button
          type="button"
          onClick={startGoogle}
          className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <span>Continue with Google</span>
          <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
        </button>
      )}

      {tab === "passkey" && (
        <button
          type="button"
          onClick={doPasskey}
          disabled={submitting}
          className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          <span>
            {submitting
              ? "Working…"
              : mode === "signup"
                ? "Register a passkey"
                : "Sign in with passkey"}
          </span>
          <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
        </button>
      )}

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </div>
  );
}
