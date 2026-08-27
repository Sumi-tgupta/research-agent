"use client";

import { ArrowUpRight, Compass } from "lucide-react";
import type { SubQuestion } from "@/lib/types";

interface FollowUpsProps {
  query: string;
  subQuestions: SubQuestion[];
  onFollowUp: (query: string) => void;
}

export function FollowUps({ query, subQuestions, onFollowUp }: FollowUpsProps) {
  const deepeners = [
    `What are the strongest counterarguments about ${shorten(query)}?`,
    `What is the most recent evidence on ${shorten(query)}?`,
  ];

  const items = [
    ...subQuestions.slice(0, 4).map((sq) => sq.question),
    ...deepeners,
  ];

  if (items.length === 0) return null;

  return (
    <div className="rounded-2xl border border-border/60 bg-card/30 p-5">
      <div className="flex items-center gap-2">
        <Compass className="h-4 w-4 text-accent" />
        <h3 className="font-display text-base font-semibold">Keep exploring</h3>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Start a fresh run on a related thread.
      </p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {items.map((q, i) => (
          <button
            key={`${i}-${q}`}
            type="button"
            onClick={() => onFollowUp(q)}
            className="group flex items-start gap-2 rounded-xl border border-border/60 bg-background/40 p-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-background/70"
          >
            <span className="flex-1 leading-snug">{q}</span>
            <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-accent" />
          </button>
        ))}
      </div>
    </div>
  );
}

function shorten(text: string, max = 80): string {
  const clean = text.trim().replace(/\?+$/, "");
  return clean.length > max ? `${clean.slice(0, max).trimEnd()}…` : clean;
}
