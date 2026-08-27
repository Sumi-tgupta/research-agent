"use client";

import { ExternalLink } from "lucide-react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  sourceKind,
  sourceLabel,
  formatAuthors,
  extractYear,
} from "@/lib/citations";
import { cn } from "@/lib/utils";
import type { ResearchDocument } from "@/lib/types";

interface CitationMarkerProps {
  n: number;
  doc?: ResearchDocument;
  onNavigate?: (n: number) => void;
}

/** An inline, clickable "[N]" citation with a source preview on hover. */
export function CitationMarker({ n, doc, onNavigate }: CitationMarkerProps) {
  // Unknown marker (out of range) — render inert so we never mislead.
  if (!doc) {
    return <sup className="px-0.5 text-xs text-muted-foreground">[{n}]</sup>;
  }

  const excerpt = doc.snippet || doc.abstract || "";

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          onClick={() => onNavigate?.(n)}
          className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded bg-accent/15 px-1 align-baseline font-sans text-[0.7rem] font-semibold text-accent ring-1 ring-inset ring-accent/30 transition-colors hover:bg-accent/25 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Source ${n}: ${doc.title}`}
        >
          {n}
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="w-80">
        <div className="flex items-center justify-between gap-2">
          <span className="rounded bg-secondary px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wide text-secondary-foreground">
            {sourceKind(doc)}
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {sourceLabel(doc)}
          </span>
        </div>
        <p className="mt-2 font-serif text-sm font-medium leading-snug text-foreground">
          {doc.title}
        </p>
        {(doc.authors.length > 0 || doc.published_date) && (
          <p className="mt-1 text-xs text-muted-foreground">
            {formatAuthors(doc.authors)}
            {doc.authors.length > 0 && doc.published_date ? " · " : ""}
            {doc.published_date ? extractYear(doc.published_date) : ""}
          </p>
        )}
        {excerpt && (
          <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
            {excerpt}
          </p>
        )}
        {doc.url && (
          <a
            href={doc.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            Open source
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </HoverCardContent>
    </HoverCard>
  );
}
