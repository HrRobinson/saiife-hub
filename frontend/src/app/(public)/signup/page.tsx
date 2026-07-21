import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function SignupPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="briefing-in text-center">
        <div className="display text-4xl text-foreground">saiife</div>
        <h1 className="display mt-2 text-xl text-muted-foreground">Create your account</h1>
      </div>
      <div className="briefing-in" style={{ animationDelay: "0.05s" }}>
        <AuthForm mode="signup" />
      </div>
      <p
        className="briefing-in text-center font-mono text-[11px] text-muted-foreground"
        style={{ animationDelay: "0.1s" }}
      >
        already have an account?{" "}
        <Link
          href="/login"
          className="text-foreground/70 underline underline-offset-2 transition-colors hover:text-foreground"
        >
          sign in
        </Link>
      </p>
    </div>
  );
}
