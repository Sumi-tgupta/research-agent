"use client";

import * as React from "react";
import { ChevronDown, CheckCircle2, XCircle, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SourceCard } from "./source-card";
import { VERDICT_META } from "@/lib/citations";
import { cn } from "@/lib/utils";
import type { VerifiedClaim, ClaimVerdict } from "@/lib/types";

interface ClaimsListProps {
  claims: VerifiedClaim[];
}

const VERDICT_ORDER: ClaimVerdict[] = [
  "contradicted",
  "corroborated",
  "single_source",
  "unverified",
];

export function ClaimsList({ claims }: ClaimsListProps) {
  if (claims.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/70 p-8 text-center">
        <p className="font-medium">No verified claims</p>
        <p className="mt-1 text-sm text-muted-foreground">
          The fact-checker didn&apos;t extract any attributable claims for this
          run.
        </p>
      </div>
    );
  }

  const counts = VERDICT_ORDER.map((v) => ({
    verdict: v,
    count: claims.filter((c) => c.verdict === v).length,
  })).filter((c) => c.count > 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          {claims.length} claim{claims.length === 1 ? "" : "s"} checked
        </span>
        <span className="mx-1 text-border">·</span>
        {counts.map(({ verdict, count }) => (
          <Badge key={verdict} variant={verdict}>
            {count} {VERDICT_META[verdict].label.toLowerCase()}
          </Badge>
        ))}
      </div>

      <div className="space-y-3">
        {claims.map((claim, i) => (
          <ClaimCard key={i} claim={claim} />
        ))}
      </div>
    </div>
  );
}

function ClaimCard({ claim }: { claim: VerifiedClaim }) {
  const [open, setOpen] = React.useState(false);
  const meta = VERDICT_META[claim.verdict];
  const totalSources =
    claim.supporting_sources.length + claim.contradicting_sources.length;

  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={claim.verdict} title={meta.description}>
          {meta.label}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {Math.round(claim.confidence * 100)}% confidence
        </span>
      </div>

      <p className="mt-2.5 font-serif text-[0.98rem] leading-relaxed text-foreground/90">
        {claim.text}
      </p>

      {claim.note && (
        <p className="mt-1.5 text-xs italic text-muted-foreground">
          {claim.note}
        </p>
      )}

      <div className="mt-3 flex items-center gap-4 text-xs">
        {claim.supporting_sources.length > 0 && (
          <span className="inline-flex items-center gap-1 text-primary">
            <CheckCircle2 className="h-3.5 w-3.5" />
            {claim.supporting_sources.length} supporting
          </span>
        )}
        {claim.contradicting_sources.length > 0 && (
          <span className="inline-flex items-center gap-1 text-destructive">
            <XCircle className="h-3.5 w-3.5" />
            {claim.contradicting_sources.length} contradicting
          </span>
        )}
        {totalSources > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ml-auto inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
            aria-expanded={open}
          >
            {open ? "Hide" : "Show"} sources
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                open && "rotate-180"
              )}
            />
          </button>
        )}
      </div>

      {open && totalSources > 0 && (
        <div className="mt-3 space-y-2 border-t border-border/50 pt-3">
          {claim.supporting_sources.map((doc, i) => (
            <SourceCard key={`s-${i}`} doc={doc} />
          ))}
          {claim.contradicting_sources.map((doc, i) => (
            <SourceCard key={`c-${i}`} doc={doc} />
          ))}
        </div>
      )}
    </div>
  );
}
