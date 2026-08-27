"use client";

import Link from "next/link";
import { LogOut, Library, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/components/auth/auth-provider";
import { openAuthDialog } from "@/lib/use-auth-dialog";

/**
 * Header account control. Nothing renders when Supabase is unconfigured; a
 * "Sign in" button when signed out; an initial-avatar dropdown when signed in.
 */
export function UserMenu() {
  const { enabled, loading, user, signOut } = useAuth();

  if (!enabled) return null;

  if (loading) {
    return <div className="h-9 w-9 animate-pulse rounded-full bg-muted/60" />;
  }

  if (!user) {
    return (
      <Button variant="outline" size="sm" onClick={openAuthDialog}>
        <UserIcon className="h-4 w-4" />
        Sign in
      </Button>
    );
  }

  const email = user.email ?? "Account";
  const initial = email.charAt(0).toUpperCase();

  const handleSignOut = async () => {
    await signOut();
    toast.success("Signed out.");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Account menu"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border/70 bg-gradient-to-b from-secondary/70 to-background/40 font-display text-sm font-semibold text-foreground transition-colors hover:border-border focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {initial}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[13rem]">
        <DropdownMenuLabel className="normal-case tracking-normal">
          <span className="block text-xs font-normal text-muted-foreground">
            Signed in as
          </span>
          <span className="block truncate text-sm font-medium text-foreground">
            {email}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/library">
            <Library className="h-4 w-4" />
            Saved library
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={handleSignOut}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
