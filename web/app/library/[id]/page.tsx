"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Trash2,
  Download,
  Copy,
  Check,
  Repeat2,
  Star,
  Pencil,
  FolderInput,
  Folder as FolderIcon,
  Tag as TagIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ResultTabs, PlanCard } from "@/components/research/result-tabs";
import {
  RenameDialog,
  TagsDialog,
  MoveDialog,
} from "@/components/library/library-browser";
import { useAuth } from "@/components/auth/auth-provider";
import { openAuthDialog } from "@/lib/use-auth-dialog";
import { downloadReportPdf } from "@/lib/api";
import {
  getReport,
  deleteReport,
  renameReport,
  setStarred,
  moveToFolder,
  setReportTags,
  listFolders,
  createFolder,
  listTags,
  type LibraryEntry,
  type Folder,
  type Tag,
} from "@/lib/library";

export default function LibraryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const { loading: authLoading, user, session } = useAuth();
  const token = session?.access_token;

  const [entry, setEntry] = React.useState<LibraryEntry | null>(null);
  const [status, setStatus] = React.useState<
    "loading" | "ready" | "notfound" | "error"
  >("loading");
  const [message, setMessage] = React.useState<string | null>(null);

  const [folders, setFolders] = React.useState<Folder[]>([]);
  const [tags, setTags] = React.useState<Tag[]>([]);

  const [downloading, setDownloading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [starBusy, setStarBusy] = React.useState(false);

  const [renameOpen, setRenameOpen] = React.useState(false);
  const [tagsOpen, setTagsOpen] = React.useState(false);
  const [moveOpen, setMoveOpen] = React.useState(false);

  React.useEffect(() => {
    if (authLoading || !id) return;
    if (!user || !token) {
      setStatus("ready"); // fall through to the sign-in gate below
      return;
    }
    let alive = true;
    setStatus("loading");
    getReport(token, id)
      .then((row) => {
        if (!alive) return;
        if (!row) {
          setStatus("notfound");
        } else {
          setEntry(row);
          setStatus("ready");
        }
      })
      .catch((err) => {
        if (!alive) return;
        setMessage(err instanceof Error ? err.message : "Couldn't load report.");
        setStatus("error");
      });
    return () => {
      alive = false;
    };
  }, [id, user, token, authLoading]);

  // Folders & tags power the move / edit-tags dialogs. Best-effort.
  React.useEffect(() => {
    if (!user || !token) return;
    let alive = true;
    Promise.all([listFolders(token), listTags(token)])
      .then(([f, t]) => {
        if (!alive) return;
        setFolders(f);
        setTags(t);
      })
      .catch(() => {
        /* non-critical */
      });
    return () => {
      alive = false;
    };
  }, [user, token]);

  const handleDownload = async () => {
    if (!entry) return;
    setDownloading(true);
    try {
      await downloadReportPdf({
        title: entry.result.query,
        final_report: entry.result.final_report,
        chart_specs: entry.result.chart_specs,
      });
      toast.success("PDF downloaded");
    } catch (err) {
      toast.error("Couldn't generate the PDF", {
        description: err instanceof Error ? err.message : "Is the backend running?",
      });
    } finally {
      setDownloading(false);
    }
  };

  const handleCopy = async () => {
    if (!entry) return;
    try {
      await navigator.clipboard.writeText(entry.result.final_report);
      setCopied(true);
      toast.success("Report copied as Markdown");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Couldn't copy to clipboard");
    }
  };

  const handleDelete = async () => {
    if (!id || !token) return;
    setDeleting(true);
    try {
      await deleteReport(token, id);
      toast.success("Removed from library");
      router.push("/library");
    } catch (err) {
      toast.error("Couldn't delete", {
        description: err instanceof Error ? err.message : undefined,
      });
      setDeleting(false);
    }
  };

  const handleToggleStar = async () => {
    if (!entry || !token) return;
    const next = !entry.starred;
    setStarBusy(true);
    setEntry({ ...entry, starred: next });
    try {
      await setStarred(token, entry.id, next);
    } catch (err) {
      setEntry({ ...entry, starred: !next });
      toast.error("Couldn't update star", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setStarBusy(false);
    }
  };

  const handleRename = async (_: LibraryEntry, title: string) => {
    if (!token || !entry) return;
    await renameReport(token, entry.id, title);
    setEntry({ ...entry, title });
    toast.success("Renamed");
  };

  const handleMove = async (_: LibraryEntry, folderId: string | null) => {
    if (!token || !entry) return;
    await moveToFolder(token, entry.id, folderId);
    setEntry({ ...entry, folder_id: folderId });
    toast.success(folderId ? "Moved to folder" : "Removed from folder");
  };

  const handleTags = async (_: LibraryEntry, next: string[]) => {
    if (!token || !entry) return;
    const saved = await setReportTags(token, entry.id, next);
    setEntry({ ...entry, tags: saved });
    toast.success("Tags updated");
  };

  const handleCreateFolder = async (name: string): Promise<Folder> => {
    if (!token) throw new Error("Sign in to create folders.");
    const folder = await createFolder(token, name);
    setFolders((prev) =>
      prev.some((f) => f.id === folder.id)
        ? prev
        : [...prev, folder].sort((a, b) => a.name.localeCompare(b.name))
    );
    return folder;
  };

  const backLink = (
    <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2">
      <Link href="/library">
        <ArrowLeft className="h-4 w-4" />
        Library
      </Link>
    </Button>
  );

  if (authLoading || status === "loading") {
    return (
      <div className="container max-w-4xl pt-10">
        {backLink}
        <div className="flex justify-center py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      </div>
    );
  }

  if (!user || !token) {
    return (
      <div className="container max-w-4xl pt-10">
        {backLink}
        <Gate
          title="Sign in to view this report"
          body="Saved reports are private to your account."
          action={
            <Button variant="horizon" size="sm" onClick={openAuthDialog}>
              Sign in
            </Button>
          }
        />
      </div>
    );
  }

  if (status === "notfound") {
    return (
      <div className="container max-w-4xl pt-10">
        {backLink}
        <Gate
          title="Report not found"
          body="It may have been deleted, or it belongs to another account."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/library">Back to library</Link>
            </Button>
          }
        />
      </div>
    );
  }

  if (status === "error" || !entry) {
    return (
      <div className="container max-w-4xl pt-10">
        {backLink}
        <Gate
          title="Something went wrong"
          body={message ?? "Couldn't load this report."}
        />
      </div>
    );
  }

  const { result } = entry;
  const folderName = folders.find((f) => f.id === entry.folder_id)?.name;

  return (
    <div className="container grid max-w-6xl gap-6 pb-24 pt-8 lg:grid-cols-12">
      <div className="lg:col-span-12">{backLink}</div>

      <aside className="lg:col-span-4 xl:col-span-3">
        <div className="lg:sticky lg:top-24 space-y-4">
          <div>
            <div className="flex items-start gap-2">
              <button
                type="button"
                onClick={handleToggleStar}
                disabled={starBusy}
                aria-label={entry.starred ? "Unstar" : "Star"}
                className={
                  "mt-1 shrink-0 rounded-md p-1 transition-colors " +
                  (entry.starred
                    ? "text-accent"
                    : "text-muted-foreground/60 hover:text-accent")
                }
              >
                <Star
                  className={"h-5 w-5" + (entry.starred ? " fill-current" : "")}
                />
              </button>
              <h1 className="font-display text-2xl font-semibold leading-tight tracking-tight">
                {entry.title}
              </h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Saved {formatDate(entry.created_at)}
            </p>
          </div>

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
            <Button variant="outline" size="sm" onClick={handleCopy}>
              {copied ? (
                <Check className="h-4 w-4" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
              Copy
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDelete}
              disabled={deleting}
              className="text-muted-foreground hover:text-destructive"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete
            </Button>
          </div>

          {/* Organize */}
          <div className="glass rounded-2xl border border-border/70 p-4 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5 text-muted-foreground">
                <FolderIcon className="h-4 w-4 shrink-0" />
                <span className="truncate">{folderName ?? "No folder"}</span>
              </span>
              <Button variant="ghost" size="sm" onClick={() => setMoveOpen(true)}>
                <FolderInput className="h-4 w-4" />
                Move
              </Button>
            </div>

            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <TagIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                {entry.tags.length === 0 ? (
                  <span className="text-muted-foreground">No tags</span>
                ) : (
                  entry.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="px-2 py-0">
                      {tag}
                    </Badge>
                  ))
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={() => setTagsOpen(true)}>
                <TagIcon className="h-4 w-4" />
                Edit
              </Button>
            </div>

            <div className="flex justify-end border-t border-border/60 pt-2">
              <Button variant="ghost" size="sm" onClick={() => setRenameOpen(true)}>
                <Pencil className="h-4 w-4" />
                Rename
              </Button>
            </div>
          </div>

          {result.revision_count > 0 && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Repeat2 className="h-3.5 w-3.5" />
              Revised {result.revision_count} time
              {result.revision_count === 1 ? "" : "s"} before approval
            </p>
          )}

          {result.plan.sub_questions.length > 0 && (
            <PlanCard
              subQuestions={result.plan.sub_questions.map((s) => s.question)}
            />
          )}
        </div>
      </aside>

      <div className="lg:col-span-8 xl:col-span-9">
        <ResultTabs result={result} />
      </div>

      {/* Editing dialogs (shared with the library browser) */}
      <RenameDialog
        target={renameOpen ? entry : null}
        onOpenChange={(open) => !open && setRenameOpen(false)}
        onSubmit={handleRename}
      />
      <TagsDialog
        target={tagsOpen ? entry : null}
        allTags={tags}
        onOpenChange={(open) => !open && setTagsOpen(false)}
        onSubmit={handleTags}
      />
      <MoveDialog
        target={moveOpen ? entry : null}
        folders={folders}
        onOpenChange={(open) => !open && setMoveOpen(false)}
        onMove={handleMove}
        onCreateFolder={handleCreateFolder}
      />
    </div>
  );
}

function Gate({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center gap-3 rounded-2xl border border-border/70 px-6 py-16 text-center">
      <div>
        <p className="font-display text-lg font-medium">{title}</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          {body}
        </p>
      </div>
      {action}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
