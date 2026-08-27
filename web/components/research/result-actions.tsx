"use client";

import * as React from "react";
import Link from "next/link";
import { Download, Copy, Plus, Loader2, Check, Bookmark } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadReportPdf } from "@/lib/api";
import type { ResearchResult } from "@/lib/types";
import { isLibraryEnabled, saveReport } from "@/lib/library";
import { useAuth } from "@/components/auth/auth-provider";
import { openAuthDialog } from "@/lib/use-auth-dialog";

interface ResultActionsProps {
  result: ResearchResult;
  onNewSearch: () => void;
}

export function ResultActions({ result, onNewSearch }: ResultActionsProps) {
  const { user, session } = useAuth();
  const [downloading, setDownloading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  // The backend auto-saves for signed-in users and returns saved_id on the
  // result, so a streamed result may already be in the library.
  const [savedId, setSavedId] = React.useState<string | null>(
    result.saved_id ?? null
  );

  // Reset when a different result flows in (e.g. a follow-up search).
  React.useEffect(() => {
    setSavedId(result.saved_id ?? null);
  }, [result]);

  const libraryEnabled = isLibraryEnabled();

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadReportPdf({
        title: result.query,
        final_report: result.final_report,
        chart_specs: result.chart_specs,
      });
      toast.success("PDF downloaded");
    } catch (err) {
      toast.error("Couldn't generate the PDF", {
        description:
          err instanceof Error ? err.message : "Is the backend running?",
      });
    } finally {
      setDownloading(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(result.final_report);
      setCopied(true);
      toast.success("Report copied as Markdown");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Couldn't copy to clipboard");
    }
  };

  const handleSave = async () => {
    if (!user) {
      toast.info("Sign in to save this to your library.");
      openAuthDialog();
      return;
    }
    setSaving(true);
    try {
      const id = await saveReport(session?.access_token, result);
      setSavedId(id);
      toast.success("Saved to your library", {
        action: {
          label: "View",
          onClick: () => {
            window.location.href = `/library/${id}`;
          },
        },
      });
    } catch (err) {
      toast.error("Couldn't save the report", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="horizon"
        size="sm"
        onClick={handleDownload}
        disabled={downloading || !result.final_report}
      >
        {downloading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        Download PDF
      </Button>
      {libraryEnabled &&
        (savedId ? (
          <Button asChild variant="outline" size="sm">
            <Link href={`/library/${savedId}`}>
              <Check className="h-4 w-4" />
              Saved · View
            </Link>
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={handleSave}
            disabled={saving || !result.final_report}
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Bookmark className="h-4 w-4" />
            )}
            Save
          </Button>
        ))}
      <Button
        variant="outline"
        size="sm"
        onClick={handleCopy}
        disabled={!result.final_report}
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        Copy Markdown
      </Button>
      <Button variant="ghost" size="sm" onClick={onNewSearch}>
        <Plus className="h-4 w-4" />
        New research
      </Button>
    </div>
  );
}
