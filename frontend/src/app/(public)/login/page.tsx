import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="briefing-in text-center">
        <div className="display text-4xl text-foreground">saiife</div>
        <h1 className="display mt-2 text-xl text-muted-foreground">Sign in</h1>
      </div>
      <div className="briefing-in" style={{ animationDelay: "0.05s" }}>
        <AuthForm mode="login" />
      </div>
      <p
        className="briefing-in text-center font-mono text-[11px] text-muted-foreground"
        style={{ animationDelay: "0.1s" }}
      >
        no account yet?{" "}
        <Link
          href="/signup"
          className="text-foreground/70 underline underline-offset-2 transition-colors hover:text-foreground"
        >
          create one
        </Link>
      </p>
    </div>
  );
}
