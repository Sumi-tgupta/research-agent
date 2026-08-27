"use client";

import { SearchComposer } from "./search-composer";
import type { ResearchRequest } from "@/lib/types";

interface HeroProps {
  onSubmit: (request: ResearchRequest) => void;
  disabled?: boolean;
}

const EXAMPLES = [
  "How do small modular reactors compare to conventional nuclear on cost and safety?",
  "What does recent evidence say about microplastics in the human bloodstream?",
  "Compare GLP-1 drugs for weight loss: efficacy, side effects, and cost.",
  "Is grid-scale sodium-ion battery storage viable within this decade?",
];

const PIPELINE = [
  { n: 1, label: "Planner", desc: "Splits your question into focused sub-questions" },
  { n: 2, label: "Web Search", desc: "Scans the open web for current sources" },
  { n: 3, label: "Paper Retrieval", desc: "Pulls papers from arXiv & Semantic Scholar" },
  { n: 4, label: "Dedup & Rank", desc: "Merges and ranks sources by relevance" },
  { n: 5, label: "Fact Checking", desc: "Cross-checks each claim across sources" },
  { n: 6, label: "Writer", desc: "Drafts a report with inline citations" },
  { n: 7, label: "Reviewer", desc: "Critiques and sends back for revision" },
  { n: 8, label: "Citations", desc: "Compiles a formatted bibliography" },
  { n: 9, label: "Charts", desc: "Extracts chartable comparisons" },
];

export function Hero({ onSubmit, disabled }: HeroProps) {
  return (
    <div className="container flex flex-col items-center pt-16 pb-24 sm:pt-24">
      <div className="animate-fade-in-up text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/40 px-3.5 py-1 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_8px_2px_hsl(var(--accent)/0.6)]" />
          Multi-agent research
        </span>

        <h1 className="mx-auto mt-6 max-w-3xl text-balance font-display text-4xl font-semibold leading-[1.08] tracking-tight sm:text-6xl">
          Answers you can trace{" "}
          <span className="bg-gradient-to-r from-horizon via-aurora to-primary bg-clip-text text-transparent">
            back to the source.
          </span>
        </h1>

        <p className="mx-auto mt-5 max-w-xl text-balance text-lg leading-relaxed text-muted-foreground">
          A team of agents plans your question, searches the web and academic
          literature, fact-checks every claim, and writes a cited report —
          while you watch it work.
        </p>
      </div>

      <div className="mt-10 w-full max-w-2xl animate-fade-in-up [animation-delay:120ms]">
        <SearchComposer onSubmit={onSubmit} disabled={disabled} autoFocus />

        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              disabled={disabled}
              onClick={() =>
                onSubmit({
                  query: example,
                  num_sub_questions: 4,
                  max_results_per_subquestion: 5,
                  citation_style: "apa",
                })
              }
              className="max-w-full truncate rounded-full border border-border/60 bg-background/30 px-3.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-border hover:bg-background/60 hover:text-foreground disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <section
        id="how-it-works"
        className="mt-24 w-full max-w-5xl scroll-mt-24 animate-fade-in-up [animation-delay:220ms]"
      >
        <div className="mb-8 text-center">
          <h2 className="font-display text-2xl font-semibold tracking-tight">
            Nine agents, one traceable answer
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Every run flows through the same pipeline. You see each step as it
            completes.
          </p>
        </div>

        <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-3">
          {PIPELINE.map((step) => (
            <li
              key={step.n}
              className="glass group rounded-xl border border-border/60 p-4 transition-colors hover:border-primary/40"
            >
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 font-mono text-xs font-semibold text-accent">
                  {String(step.n).padStart(2, "0")}
                </span>
                <span className="font-medium">{step.label}</span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {step.desc}
              </p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
