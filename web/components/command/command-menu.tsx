"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import {
  Plus,
  FileText,
  Library,
  ShieldCheck,
  BarChart3,
  Download,
  Copy,
  Sun,
  Moon,
  Sparkles,
  Home,
} from "lucide-react";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { useCommandMenu } from "@/lib/use-command-menu";
import { downloadReportPdf } from "@/lib/api";
import { isLibraryEnabled } from "@/lib/library";
import type { ResearchRequest, ResearchResult } from "@/lib/types";
import type { ResearchPhase } from "@/lib/use-research";

interface CommandMenuProps {
  phase: ResearchPhase;
  result: ResearchResult | null;
  onStart: (request: ResearchRequest) => void;
  onReset: () => void;
}

const EXAMPLES = [
  "How do small modular reactors compare to conventional nuclear?",
  "What is the latest evidence on microplastics in human blood?",
  "Compare GLP-1 drugs for weight loss: efficacy and side effects.",
];

function setTab(tab: string) {
  window.dispatchEvent(new CustomEvent("aurelia:set-tab", { detail: tab }));
}

export function CommandMenu({
  phase,
  result,
  onStart,
  onReset,
}: CommandMenuProps) {
  const [open, setOpen] = useCommandMenu();
  const { setTheme, resolvedTheme } = useTheme();
  const router = useRouter();
  const libraryEnabled = isLibraryEnabled();

  // Global ⌘K / Ctrl+K toggle.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const run = (fn: () => void) => {
    setOpen(false);
    // let the dialog close before side effects (focus, scroll, toasts)
    requestAnimationFrame(fn);
  };

  const hasResult = phase === "complete" && !!result?.final_report;

  const startExample = (q: string) =>
    onStart({
      query: q,
      num_sub_questions: 4,
      max_results_per_subquestion: 5,
      citation_style: "apa",
    });

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Research">
          <CommandItem onSelect={() => run(onReset)}>
            <Plus />
            New research
          </CommandItem>
          {EXAMPLES.map((q) => (
            <CommandItem
              key={q}
              value={`example ${q}`}
              onSelect={() => run(() => startExample(q))}
            >
              <Sparkles />
              <span className="truncate">{q}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandGroup heading="Navigate">
          <CommandItem
            value="home research"
            onSelect={() => run(() => router.push("/"))}
          >
            <Home />
            Home
          </CommandItem>
          {libraryEnabled && (
            <CommandItem
              value="library saved reports"
              onSelect={() => run(() => router.push("/library"))}
            >
              <Library />
              Saved library
            </CommandItem>
          )}
        </CommandGroup>

        {hasResult && result && (
          <CommandGroup heading="This report">
            <CommandItem onSelect={() => run(() => setTab("report"))}>
              <FileText />
              View report
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTab("sources"))}>
              <Library />
              View sources
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTab("claims"))}>
              <ShieldCheck />
              View claims
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTab("charts"))}>
              <BarChart3 />
              View charts
            </CommandItem>
            <CommandItem
              onSelect={() =>
                run(async () => {
                  try {
                    await downloadReportPdf({
                      title: result.query,
                      final_report: result.final_report,
                      chart_specs: result.chart_specs,
                    });
                    toast.success("PDF downloaded");
                  } catch {
                    toast.error("Couldn't generate the PDF");
                  }
                })
              }
            >
              <Download />
              Download PDF
            </CommandItem>
            <CommandItem
              onSelect={() =>
                run(async () => {
                  try {
                    await navigator.clipboard.writeText(result.final_report);
                    toast.success("Report copied as Markdown");
                  } catch {
                    toast.error("Couldn't copy to clipboard");
                  }
                })
              }
            >
              <Copy />
              Copy report as Markdown
            </CommandItem>
          </CommandGroup>
        )}

        <CommandGroup heading="Appearance">
          {resolvedTheme === "light" ? (
            <CommandItem onSelect={() => run(() => setTheme("dark"))}>
              <Moon />
              Switch to dark
            </CommandItem>
          ) : (
            <CommandItem onSelect={() => run(() => setTheme("light"))}>
              <Sun />
              Switch to light
            </CommandItem>
          )}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
