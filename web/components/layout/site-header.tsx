"use client";

import Link from "next/link";
import { Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { BackendStatus } from "./backend-status";
import { UserMenu } from "./user-menu";
import { AuthDialog } from "@/components/auth/auth-dialog";
import { openCommandMenu } from "@/lib/use-command-menu";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border/60 glass">
      <div className="container flex h-16 items-center gap-3">
        <Link href="/" className="group flex items-center gap-2.5">
          <HorizonMark />
          <span className="flex flex-col leading-none">
            <span className="font-display text-lg font-semibold tracking-tight">
              Aurelia
            </span>
            <span className="text-[0.64rem] font-medium uppercase tracking-[0.22em] text-muted-foreground">
              Deep Research
            </span>
          </span>
        </Link>

        <div className="flex flex-1 justify-center px-2">
          <button
            type="button"
            onClick={openCommandMenu}
            className="group flex h-9 w-full max-w-md items-center gap-2 rounded-lg border border-border/70 bg-background/40 px-3 text-sm text-muted-foreground transition-colors hover:border-border hover:bg-background/60"
          >
            <Search className="h-4 w-4" />
            <span className="flex-1 text-left">Search actions & history</span>
            <kbd className="pointer-events-none hidden items-center gap-0.5 rounded border border-border bg-muted px-1.5 font-mono text-[0.7rem] text-muted-foreground sm:inline-flex">
              ⌘K
            </kbd>
          </button>
        </div>

        <nav className="flex items-center gap-1">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="hidden text-muted-foreground hover:text-foreground sm:inline-flex"
          >
            <Link href="/#how-it-works">
              <Sparkles className="h-4 w-4" />
              How it works
            </Link>
          </Button>
          <BackendStatus />
          <ThemeToggle />
          <UserMenu />
        </nav>
      </div>
      <AuthDialog />
    </header>
  );
}

/** A rising sun over a horizon line — the app's glyph. */
function HorizonMark() {
  return (
    <span className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-border/70 bg-gradient-to-b from-secondary/60 to-background/40 shadow-inner">
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="horizonMark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="hsl(var(--horizon-glow))" />
            <stop offset="1" stopColor="hsl(var(--viridian))" />
          </linearGradient>
        </defs>
        <circle cx="12" cy="11" r="4.2" fill="url(#horizonMark)" />
        <path
          d="M3 15.5c3-2.2 5.8-2.2 9-2.2s6 0 9 2.2"
          stroke="hsl(var(--horizon-glow))"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.9"
        />
        <path
          d="M4.5 18.5c2.4-1.4 4.6-1.4 7.5-1.4s5.1 0 7.5 1.4"
          stroke="hsl(var(--aurora))"
          strokeWidth="1.3"
          strokeLinecap="round"
          opacity="0.55"
        />
      </svg>
    </span>
  );
}
