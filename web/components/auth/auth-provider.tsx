"use client";

import * as React from "react";
import type { Session, User, SupabaseClient } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

interface AuthContextValue {
  enabled: boolean;
  loading: boolean;
  user: User | null;
  session: Session | null;
  client: SupabaseClient | null;
  signOut: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const clientRef = React.useRef<SupabaseClient | null>(
    getSupabaseBrowserClient()
  );
  const enabled = clientRef.current !== null;

  const [user, setUser] = React.useState<User | null>(null);
  const [session, setSession] = React.useState<Session | null>(null);
  const [loading, setLoading] = React.useState<boolean>(enabled);

  React.useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    client.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setUser(data.session?.user ?? null);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setUser(newSession?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = React.useCallback(async () => {
    await clientRef.current?.auth.signOut();
    setUser(null);
    setSession(null);
  }, []);

  const value: AuthContextValue = {
    enabled,
    loading,
    user,
    session,
    client: clientRef.current,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    // Safe default so components can call useAuth() even if the provider is
    // somehow absent — behaves as anonymous mode.
    return {
      enabled: false,
      loading: false,
      user: null,
      session: null,
      client: null,
      signOut: async () => {},
    };
  }
  return ctx;
}
