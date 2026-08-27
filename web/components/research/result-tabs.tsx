"use client";

import * as React from "react";
import { FileText, Library, ShieldCheck, BarChart3 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ReportView } from "./report-view";
import { SourcesPanel } from "./sources-panel";
import { ClaimsList } from "./claims-list";
import { ChartsPanel } from "./charts-panel";
import { ReportSkeleton } from "./states";
import { buildSourceIndex } from "@/lib/citations";
import type { ResearchResult } from "@/lib/types";

interface ResultTabsProps {
  result: ResearchResult | null;
  /** When true, empty tabs show progress hints / skeletons instead of "none". */
  running?: boolean;
}

/**
 * The Report / Sources / Claims / Charts tab surface shared by the live run
 * view and the saved-report reader. Owns tab state, clickable-citation
 * navigation (report → sources with a highlight), and responds to the global
 * "aurelia:set-tab" event dispatched by the command palette.
 */
export function ResultTabs({ result, running = false }: ResultTabsProps) {
  const [tab, setTab] = React.useState("report");
  const [highlighted, setHighlighted] = React.useState<number | null>(null);
  const highlightTimer = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );

  const sourceIndex = React.useMemo(
    () => (result ? buildSourceIndex(result.verified_claims) : []),
    [result]
  );

  const navigateToSource = React.useCallback((n: number) => {
    setTab("sources");
    setHighlighted(n);
    requestAnimationFrame(() => {
      setTimeout(() => {
        document
          .getElementById(`source-${n}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 60);
    });
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setHighlighted(null), 2600);
  }, []);

  React.useEffect(() => {
    return () => {
      if (highlightTimer.current) clearTimeout(highlightTimer.current);
    };
  }, []);

  React.useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) setTab(detail);
    };
    window.addEventListener("aurelia:set-tab", handler as EventListener);
    return () =>
      window.removeEventListener("aurelia:set-tab", handler as EventListener);
  }, []);

  const hasReport = !!result?.final_report;
  const counts = {
    sources: sourceIndex.length || result?.final_documents.length || 0,
    claims: result?.verified_claims.length || 0,
    charts: result?.chart_specs.length || 0,
  };

  return (
    <div className="glass rounded-2xl border border-border/70 p-5 sm:p-7">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-2">
          <TabsTrigger value="report">
            <FileText className="h-4 w-4" />
            Report
          </TabsTrigger>
          <TabsTrigger value="sources">
            <Library className="h-4 w-4" />
            Sources
            {counts.sources > 0 && <Count n={counts.sources} />}
          </TabsTrigger>
          <TabsTrigger value="claims">
            <ShieldCheck className="h-4 w-4" />
            Claims
            {counts.claims > 0 && <Count n={counts.claims} />}
          </TabsTrigger>
          <TabsTrigger value="charts">
            <BarChart3 className="h-4 w-4" />
            Charts
            {counts.charts > 0 && <Count n={counts.charts} />}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="report">
          {hasReport ? (
            <ReportView
              report={result!.final_report}
              sourceIndex={sourceIndex}
              onNavigate={navigateToSource}
            />
          ) : running ? (
            <ReportSkeleton />
          ) : (
            <p className="text-sm text-muted-foreground">
              No report was produced for this run.
            </p>
          )}
        </TabsContent>

        <TabsContent value="sources">
          {result ? (
            <SourcesPanel
              sourceIndex={sourceIndex}
              fallbackDocs={result.final_documents}
              highlightedIndex={highlighted}
            />
          ) : (
            <PendingNote label="Sources appear once retrieval completes." />
          )}
        </TabsContent>

        <TabsContent value="claims">
          {result ? (
            <ClaimsList claims={result.verified_claims} />
          ) : (
            <PendingNote label="Claims appear after fact-checking." />
          )}
        </TabsContent>

        <TabsContent value="charts">
          {result ? (
            <ChartsPanel charts={result.chart_specs} />
          ) : (
            <PendingNote label="Charts appear at the end of the run." />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Count({ n }: { n: number }) {
  return (
    <span className="ml-1 rounded-full bg-background/60 px-1.5 text-[0.68rem] font-semibold tabular-nums">
      {n}
    </span>
  );
}

function PendingNote({ label }: { label: string }) {
  return (
    <p className="py-6 text-center text-sm text-muted-foreground">{label}</p>
  );
}

/** The research plan, rendered as a numbered sequence. Shared side panel. */
export function PlanCard({ subQuestions }: { subQuestions: string[] }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/30 p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Research plan
      </p>
      <ol className="mt-2 space-y-2">
        {subQuestions.map((q, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <span className="font-mono text-xs text-accent">{i + 1}.</span>
            <span className="leading-snug text-foreground/90">{q}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
