"use client";

import * as React from "react";
import { ArrowUp, SlidersHorizontal, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ResearchRequest, CitationStyle } from "@/lib/types";

interface SearchComposerProps {
  onSubmit: (request: ResearchRequest) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  initialQuery?: string;
  className?: string;
}

const LANGUAGES = [
  "English",
  "Spanish",
  "French",
  "German",
  "Hindi",
  "Chinese",
  "Japanese",
  "Portuguese",
];

export function SearchComposer({
  onSubmit,
  disabled = false,
  autoFocus = false,
  initialQuery = "",
  className,
}: SearchComposerProps) {
  const [query, setQuery] = React.useState(initialQuery);
  const [showOptions, setShowOptions] = React.useState(false);
  const [numSubQuestions, setNumSubQuestions] = React.useState(4);
  const [maxResults, setMaxResults] = React.useState(5);
  const [maxRevisions, setMaxRevisions] = React.useState(1);
  const [citationStyle, setCitationStyle] =
    React.useState<CitationStyle>("apa");
  const [language, setLanguage] = React.useState("English");
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  // Grow the textarea with its content.
  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [query]);

  const submit = () => {
    const trimmed = query.trim();
    if (!trimmed || disabled) return;
    onSubmit({
      query: trimmed,
      num_sub_questions: numSubQuestions,
      max_results_per_subquestion: maxResults,
      target_language: language,
      max_revisions: maxRevisions,
      citation_style: citationStyle,
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className={cn("w-full", className)}>
      <div className="glass-strong rounded-2xl border border-border/80 shadow-2xl shadow-black/20 transition-colors focus-within:border-primary/50">
        <Textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={2}
          placeholder="Ask a research question — e.g. How do small modular reactors compare to conventional nuclear on cost and safety?"
          className="min-h-[64px] resize-none border-0 bg-transparent px-5 py-4 text-base leading-relaxed shadow-none focus-visible:ring-0"
        />

        <div className="flex items-center justify-between gap-2 border-t border-border/60 px-3 py-2.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowOptions((v) => !v)}
            className={cn(
              "text-muted-foreground hover:text-foreground",
              showOptions && "text-foreground"
            )}
            aria-expanded={showOptions}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Options
          </Button>

          <div className="flex items-center gap-2">
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {numSubQuestions} sub-questions · {citationStyle.toUpperCase()}
            </span>
            <Button
              type="button"
              variant="horizon"
              size="icon"
              onClick={submit}
              disabled={disabled || !query.trim()}
              aria-label="Start research"
            >
              {disabled ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {showOptions && (
          <div className="grid animate-fade-in grid-cols-1 gap-x-6 gap-y-4 border-t border-border/60 px-5 py-4 sm:grid-cols-2">
            <Stepper
              label="Sub-questions"
              hint="How many facets to break the query into"
              value={numSubQuestions}
              min={2}
              max={8}
              onChange={setNumSubQuestions}
            />
            <Stepper
              label="Sources per sub-question"
              hint="Depth of retrieval per facet"
              value={maxResults}
              min={3}
              max={10}
              onChange={setMaxResults}
            />
            <Stepper
              label="Revision passes"
              hint="Max writer↔reviewer loops"
              value={maxRevisions}
              min={0}
              max={3}
              onChange={setMaxRevisions}
            />
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">Language</span>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="h-9 rounded-md border border-input bg-background/60 px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <span className="text-sm font-medium">Citation style</span>
              <div className="inline-flex w-fit rounded-lg border border-border bg-background/50 p-1">
                {(["apa", "mla"] as CitationStyle[]).map((style) => (
                  <button
                    key={style}
                    type="button"
                    onClick={() => setCitationStyle(style)}
                    className={cn(
                      "rounded-md px-4 py-1 text-sm font-medium transition-colors",
                      citationStyle === style
                        ? "bg-primary/90 text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {style.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stepper({
  label,
  hint,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex items-center gap-3">
        <div className="inline-flex items-center rounded-md border border-border bg-background/50">
          <button
            type="button"
            onClick={() => onChange(Math.max(min, value - 1))}
            disabled={value <= min}
            className="flex h-9 w-9 items-center justify-center text-lg text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
            aria-label={`Decrease ${label}`}
          >
            −
          </button>
          <span className="w-8 text-center text-sm font-semibold tabular-nums">
            {value}
          </span>
          <button
            type="button"
            onClick={() => onChange(Math.min(max, value + 1))}
            disabled={value >= max}
            className="flex h-9 w-9 items-center justify-center text-lg text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
            aria-label={`Increase ${label}`}
          >
            +
          </button>
        </div>
        {hint && (
          <span className="text-xs leading-tight text-muted-foreground">
            {hint}
          </span>
        )}
      </div>
    </div>
  );
}
