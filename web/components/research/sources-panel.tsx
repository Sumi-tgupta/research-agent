"use client";

import { SourceCard } from "./source-card";
import { Library } from "lucide-react";
import type { ResearchDocument } from "@/lib/types";

interface SourcesPanelProps {
  sourceIndex: ResearchDocument[];
  fallbackDocs?: ResearchDocument[];
  highlightedIndex?: number | null;
}

export function SourcesPanel({
  sourceIndex,
  fallbackDocs = [],
  highlightedIndex,
}: SourcesPanelProps) {
  const useIndex = sourceIndex.length > 0;
  const docs = useIndex ? sourceIndex : fallbackDocs;

  if (docs.length === 0) {
    return (
      <EmptyPanel
        title="No sources to show"
        body="This run didn't attach any retrievable sources."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Library className="h-4 w-4" />
        <span>
          {docs.length} {useIndex ? "cited" : "retrieved"} source
          {docs.length === 1 ? "" : "s"}
          {useIndex ? " · numbered to match the report" : ""}
        </span>
      </div>
      <div className="space-y-3">
        {docs.map((doc, i) => (
          <SourceCard
            key={`${doc.url || doc.title}-${i}`}
            doc={doc}
            index={useIndex ? i + 1 : undefined}
            highlighted={useIndex && highlightedIndex === i + 1}
          />
        ))}
      </div>
    </div>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border/70 p-8 text-center">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
