"use client";

import { ExternalLink, Quote, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  sourceKind,
  sourceLabel,
  formatAuthors,
  extractYear,
} from "@/lib/citations";
import { cn } from "@/lib/utils";
import type { ResearchDocument } from "@/lib/types";

interface SourceCardProps {
  doc: ResearchDocument;
  index?: number;
  highlighted?: boolean;
}

export function SourceCard({ doc, index, highlighted }: SourceCardProps) {
  const excerpt = doc.snippet || doc.abstract || "";
  const year = doc.published_date ? extractYear(doc.published_date) : "";

  return (
    <div
      id={index ? `source-${index}` : undefined}
      className={cn(
        "scroll-mt-24 rounded-xl border border-border/60 bg-card/40 p-4 transition-all duration-500",
        highlighted && "border-accent/70 bg-accent/5 ring-1 ring-accent/40"
      )}
    >
      <div className="flex gap-3">
        {index !== undefined && (
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-secondary font-mono text-xs font-semibold text-accent">
            {index}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Badge variant="outline" className="border-border/70">
              {sourceKind(doc)}
            </Badge>
            <span className="truncate text-xs text-muted-foreground">
              {sourceLabel(doc)}
              {year ? ` · ${year}` : ""}
            </span>
          </div>

          <a
            href={doc.url || undefined}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "group mt-1.5 block font-serif text-[0.95rem] font-medium leading-snug text-foreground",
              doc.url && "hover:text-accent"
            )}
          >
            <span className="align-middle">{doc.title}</span>
            {doc.url && (
              <ExternalLink className="ml-1 inline h-3 w-3 align-middle text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            )}
          </a>

          {doc.authors.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {formatAuthors(doc.authors, 4)}
            </p>
          )}

          {excerpt && (
            <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted-foreground">
              {excerpt}
            </p>
          )}

          {(doc.citation_count != null || doc.relevance_score != null) && (
            <div className="mt-2.5 flex items-center gap-4 text-xs text-muted-foreground">
              {doc.citation_count != null && (
                <span className="inline-flex items-center gap-1">
                  <Quote className="h-3 w-3" />
                  {doc.citation_count.toLocaleString()} citations
                </span>
              )}
              {doc.relevance_score != null && (
                <span className="inline-flex items-center gap-1">
                  <Star className="h-3 w-3" />
                  {(doc.relevance_score * 100).toFixed(0)}% relevance
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
