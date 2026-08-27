/**
 * Client-side mirror of app/citations.py :: build_source_index.
 *
 * The Writer emits inline "[N]" markers; the backend's bibliography and the
 * numbering handed to the Writer both come from this exact ordering, so to
 * make markers clickable in the rendered report we must reproduce it 1:1:
 * dedup by (url || title) in first-seen order, scanning each claim's
 * supporting_sources then contradicting_sources.
 */

import type { ResearchDocument, VerifiedClaim, ClaimVerdict } from "./types";

export function buildSourceIndex(
  verifiedClaims: VerifiedClaim[]
): ResearchDocument[] {
  const seen = new Set<string>();
  const index: ResearchDocument[] = [];
  for (const claim of verifiedClaims) {
    for (const doc of [
      ...claim.supporting_sources,
      ...claim.contradicting_sources,
    ]) {
      const key = doc.url || doc.title;
      if (key && !seen.has(key)) {
        seen.add(key);
        index.push(doc);
      }
    }
  }
  return index;
}

/** Map a 1-based citation marker to its source (or undefined if out of range). */
export function resolveCitation(
  index: ResearchDocument[],
  markerNumber: number
): ResearchDocument | undefined {
  return index[markerNumber - 1];
}

const MARKER_RE = /\[(\d+)\]/g;

/** The set of [N] numbers actually used in the draft text. */
export function citedNumbers(text: string): Set<number> {
  const nums = new Set<number>();
  let m: RegExpExecArray | null;
  MARKER_RE.lastIndex = 0;
  while ((m = MARKER_RE.exec(text)) !== null) {
    nums.add(Number.parseInt(m[1], 10));
  }
  return nums;
}

// ── Display helpers ──

const SOURCE_LABELS: Record<ResearchDocument["source"], string> = {
  web: "Web",
  arxiv: "arXiv",
  semantic_scholar: "Semantic Scholar",
  openalex: "OpenAlex",
  pubmed: "PubMed",
  crossref: "Crossref",
  wikipedia: "Wikipedia",
};

export function sourceLabel(doc: ResearchDocument): string {
  if (doc.source === "web") return domainFromUrl(doc.url) || "Web";
  return SOURCE_LABELS[doc.source] ?? "Source";
}

export function sourceKind(doc: ResearchDocument): string {
  return SOURCE_LABELS[doc.source] ?? "Source";
}

export function domainFromUrl(url: string): string {
  try {
    const host = new URL(url).hostname;
    return host.startsWith("www.") ? host.slice(4) : host;
  } catch {
    return "";
  }
}

export function extractYear(publishedDate?: string | null): string {
  if (!publishedDate) return "n.d.";
  const m = publishedDate.match(/(\d{4})/);
  return m ? m[1] : "n.d.";
}

export function formatAuthors(authors: string[], max = 3): string {
  const clean = authors.filter((a) => a.trim());
  if (clean.length === 0) return "";
  if (clean.length <= max) {
    if (clean.length === 1) return clean[0];
    return `${clean.slice(0, -1).join(", ")} & ${clean[clean.length - 1]}`;
  }
  return `${clean.slice(0, max).join(", ")} et al.`;
}

export const VERDICT_META: Record<
  ClaimVerdict,
  { label: string; description: string }
> = {
  corroborated: {
    label: "Corroborated",
    description: "Two or more independent sources agree; none disagree.",
  },
  single_source: {
    label: "Single source",
    description: "Exactly one source states this claim.",
  },
  contradicted: {
    label: "Contradicted",
    description: "At least one source disagrees with this claim.",
  },
  unverified: {
    label: "Unverified",
    description: "No source could be confidently attributed.",
  },
};
