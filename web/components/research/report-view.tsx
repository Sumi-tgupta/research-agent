"use client";

import * as React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationMarker } from "./citation-marker";
import { resolveCitation } from "@/lib/citations";
import type { ResearchDocument } from "@/lib/types";

interface ReportViewProps {
  report: string;
  sourceIndex: ResearchDocument[];
  onNavigate?: (n: number) => void;
}

const CITATION_SPLIT = /(\[\d+\])/g;
const CITATION_NUM = /^\[(\d+)\]$/;

/** Replace "[N]" tokens inside a plain string with clickable markers. */
function splitString(
  text: string,
  sourceIndex: ResearchDocument[],
  onNavigate?: (n: number) => void,
  keyPrefix = ""
): React.ReactNode[] {
  const parts = text.split(CITATION_SPLIT);
  return parts.map((part, i) => {
    const match = part.match(CITATION_NUM);
    if (match) {
      const n = Number.parseInt(match[1], 10);
      return (
        <CitationMarker
          key={`${keyPrefix}-c${i}`}
          n={n}
          doc={resolveCitation(sourceIndex, n)}
          onNavigate={onNavigate}
        />
      );
    }
    return <React.Fragment key={`${keyPrefix}-t${i}`}>{part}</React.Fragment>;
  });
}

/** Recursively walk rendered children, injecting citation markers into text. */
function injectCitations(
  children: React.ReactNode,
  sourceIndex: ResearchDocument[],
  onNavigate?: (n: number) => void,
  keyPrefix = "k"
): React.ReactNode {
  return React.Children.map(children, (child, i) => {
    if (typeof child === "string") {
      if (!child.includes("[")) return child;
      return splitString(child, sourceIndex, onNavigate, `${keyPrefix}-${i}`);
    }
    if (
      React.isValidElement(child) &&
      (child.props as { children?: React.ReactNode })?.children
    ) {
      const props = child.props as { children?: React.ReactNode };
      return React.cloneElement(
        child,
        undefined,
        injectCitations(
          props.children,
          sourceIndex,
          onNavigate,
          `${keyPrefix}-${i}`
        )
      );
    }
    return child;
  });
}

export function ReportView({
  report,
  sourceIndex,
  onNavigate,
}: ReportViewProps) {
  const components = React.useMemo(() => {
    const wrap =
      (Tag: keyof JSX.IntrinsicElements) =>
      ({ children }: { children?: React.ReactNode }) => (
        <Tag>{injectCitations(children, sourceIndex, onNavigate)}</Tag>
      );

    return {
      p: wrap("p"),
      li: wrap("li"),
      td: wrap("td"),
      th: wrap("th"),
      h1: wrap("h1"),
      h2: wrap("h2"),
      h3: wrap("h3"),
      // Open any real links in a new tab.
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      ),
    } as const;
  }, [sourceIndex, onNavigate]);

  return (
    <article className="report-prose">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {report}
      </Markdown>
    </article>
  );
}
