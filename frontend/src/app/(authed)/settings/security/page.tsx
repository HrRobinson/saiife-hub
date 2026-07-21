"use client";
import { AccountShell } from "@/components/AccountShell";
import { PasskeyList } from "@/components/PasskeyList";
import { useAuth } from "@/lib/auth-context";

export default function SecuritySettings() {
  const { user } = useAuth();
  return (
    <AccountShell email={user?.email ?? ""}>
      <div className="briefing-in mb-8">
        <div className="briefing-label">account · security</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Security</h1>
      </div>
      <PasskeyList />
    </AccountShell>
  );
}
