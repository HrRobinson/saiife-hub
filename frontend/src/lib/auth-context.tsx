"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiException, api } from "./api";

export type Me = { id: string; email: string; email_verified: boolean };

type Ctx = {
  user: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setUser: (u: Me | null) => void;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      setUser(await api<Me>("/api/v1/auth/me"));
    } catch (e) {
      if (e instanceof ApiException && e.status === 401) setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" });
    setUser(null);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, refresh, setUser, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): Ctx {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
