"use client";

import * as React from "react";
import { Library as LibraryIcon, Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import { openAuthDialog } from "@/lib/use-auth-dialog";
import { isLibraryEnabled } from "@/lib/library";
import { LibraryBrowser } from "@/components/library/library-browser";

export default function LibraryPage() {
  const { loading: authLoading, user, session } = useAuth();
  const token = session?.access_token;

  return (
    <div className="container max-w-3xl pb-24 pt-10">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-accent">
          <LibraryIcon className="h-5 w-5" />
          <span className="text-xs font-medium uppercase tracking-[0.22em]">
            Your library
          </span>
        </div>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight">
          Saved research
        </h1>
        <p className="mt-1 text-muted-foreground">
          Every report you save lands here — fully traceable, ready to revisit.
        </p>
      </header>

      {!isLibraryEnabled() ? (
        <EmptyNote
          icon={<Lock className="h-5 w-5" />}
          title="Sign-in isn't configured"
          body="This deployment is running in anonymous mode, so there's no saved library. Research still works — reports just aren't persisted."
        />
      ) : authLoading ? (
        <CenteredSpinner />
      ) : !user || !token ? (
        <EmptyNote
          icon={<Lock className="h-5 w-5" />}
          title="Sign in to view your library"
          body="Your saved reports are private to your account."
          action={
            <Button variant="horizon" size="sm" onClick={openAuthDialog}>
              Sign in
            </Button>
          }
        />
      ) : (
        <LibraryBrowser token={token} />
      )}
    </div>
  );
}

function CenteredSpinner() {
  return (
    <div className="flex justify-center py-20 text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  );
}

function EmptyNote({
  icon,
  title,
  body,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center gap-3 rounded-2xl border border-border/70 px-6 py-16 text-center">
      {icon && (
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-border/70 bg-secondary/40 text-accent">
          {icon}
        </span>
      )}
      <div>
        <p className="font-display text-lg font-medium">{title}</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          {body}
        </p>
      </div>
      {action}
    </div>
  );
}
