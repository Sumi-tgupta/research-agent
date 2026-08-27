"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthDialog } from "@/lib/use-auth-dialog";
import { useAuth } from "@/components/auth/auth-provider";

type Mode = "signin" | "signup";

/**
 * Email + password sign-in / sign-up over Supabase. Mounted once (in the page)
 * and driven by the global useAuthDialog store. Renders nothing when Supabase
 * isn't configured.
 */
export function AuthDialog() {
  const [open, setOpen] = useAuthDialog();
  const { client, enabled } = useAuth();

  const [mode, setMode] = React.useState<Mode>("signin");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Reset transient state whenever the dialog closes.
  React.useEffect(() => {
    if (!open) {
      setBusy(false);
      setError(null);
      setPassword("");
    }
  }, [open]);

  if (!enabled) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!client || busy) return;
    setBusy(true);
    setError(null);

    try {
      if (mode === "signup") {
        const { data, error } = await client.auth.signUp({ email, password });
        if (error) throw error;
        // If email confirmation is on, there's no session yet.
        if (!data.session) {
          toast.success("Check your inbox to confirm your email.");
        } else {
          toast.success("Account created — you're signed in.");
        }
      } else {
        const { error } = await client.auth.signInWithPassword({
          email,
          password,
        });
        if (error) throw error;
        toast.success("Signed in.");
      }
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const isSignup = mode === "signup";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isSignup ? "Create your account" : "Welcome back"}
          </DialogTitle>
          <DialogDescription>
            {isSignup
              ? "Save reports to a private library you can return to anytime."
              : "Sign in to reach your saved research library."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="auth-email"
              className="text-xs font-medium text-muted-foreground"
            >
              Email
            </label>
            <Input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="auth-password"
              className="text-xs font-medium text-muted-foreground"
            >
              Password
            </label>
            <Input
              id="auth-password"
              type="password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignup ? "At least 6 characters" : "••••••••"}
            />
          </div>

          {error && (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button
            type="submit"
            variant="horizon"
            disabled={busy}
            className="mt-1 w-full"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSignup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          {isSignup ? "Already have an account?" : "New to Aurelia?"}{" "}
          <button
            type="button"
            className="font-medium text-accent underline-offset-4 hover:underline"
            onClick={() => {
              setError(null);
              setMode(isSignup ? "signin" : "signup");
            }}
          >
            {isSignup ? "Sign in" : "Create one"}
          </button>
        </p>
      </DialogContent>
    </Dialog>
  );
}
