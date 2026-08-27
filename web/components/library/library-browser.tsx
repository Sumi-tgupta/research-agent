"use client";

import * as React from "react";
import Link from "next/link";
import {
  Search,
  Star,
  Trash2,
  Loader2,
  MoreHorizontal,
  FolderPlus,
  Folder as FolderIcon,
  FolderInput,
  Tag as TagIcon,
  Pencil,
  ArrowUpRight,
  Check,
  X,
  Library as LibraryIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  listReports,
  deleteReport,
  renameReport,
  setStarred,
  moveToFolder,
  setReportTags,
  listFolders,
  createFolder,
  deleteFolder,
  listTags,
  type LibrarySummary,
  type Folder,
  type Tag,
  type LibraryFilters,
} from "@/lib/library";

/**
 * The full signed-in library experience: search, folder & tag filters,
 * starring, rename, move-to-folder, and tag editing — all backed by the
 * FastAPI /library endpoints (see @/lib/library). The page shell handles the
 * auth gate and only mounts this once we have a token.
 */
export function LibraryBrowser({ token }: { token: string }) {
  const [entries, setEntries] = React.useState<LibrarySummary[] | null>(null);
  const [folders, setFolders] = React.useState<Folder[]>([]);
  const [tags, setTags] = React.useState<Tag[]>([]);

  const [search, setSearch] = React.useState("");
  const [debouncedSearch, setDebouncedSearch] = React.useState("");
  const [folderId, setFolderId] = React.useState<string | null>(null);
  const [starredOnly, setStarredOnly] = React.useState(false);
  const [tagFilter, setTagFilter] = React.useState<string | null>(null);

  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  // Dialog targets.
  const [renameTarget, setRenameTarget] = React.useState<LibrarySummary | null>(null);
  const [tagsTarget, setTagsTarget] = React.useState<LibrarySummary | null>(null);
  const [moveTarget, setMoveTarget] = React.useState<LibrarySummary | null>(null);
  const [newFolderOpen, setNewFolderOpen] = React.useState(false);

  const activeFilterCount =
    (folderId ? 1 : 0) + (starredOnly ? 1 : 0) + (tagFilter ? 1 : 0);

  // Debounce the search box.
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  const filters: LibraryFilters = React.useMemo(
    () => ({
      search: debouncedSearch || undefined,
      folderId: folderId ?? undefined,
      starred: starredOnly ? true : undefined,
      tag: tagFilter ?? undefined,
    }),
    [debouncedSearch, folderId, starredOnly, tagFilter]
  );

  const loadEntries = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await listReports(token, filters));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your library.");
    } finally {
      setLoading(false);
    }
  }, [token, filters]);

  const loadFacets = React.useCallback(async () => {
    try {
      const [f, t] = await Promise.all([listFolders(token), listTags(token)]);
      setFolders(f);
      setTags(t);
    } catch {
      /* facets are non-critical; the list still works */
    }
  }, [token]);

  React.useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  React.useEffect(() => {
    loadFacets();
  }, [loadFacets]);

  // ---- mutations (optimistic where it helps) ---- //

  const handleToggleStar = async (entry: LibrarySummary) => {
    const next = !entry.starred;
    setEntries((prev) =>
      prev?.map((e) => (e.id === entry.id ? { ...e, starred: next } : e)) ?? null
    );
    try {
      await setStarred(token, entry.id, next);
      if (starredOnly && !next) {
        setEntries((prev) => prev?.filter((e) => e.id !== entry.id) ?? null);
      }
    } catch (err) {
      setEntries((prev) =>
        prev?.map((e) =>
          e.id === entry.id ? { ...e, starred: entry.starred } : e
        ) ?? null
      );
      toast.error("Couldn't update star", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const handleDelete = async (entry: LibrarySummary) => {
    setBusyId(entry.id);
    try {
      await deleteReport(token, entry.id);
      setEntries((prev) => prev?.filter((e) => e.id !== entry.id) ?? null);
      toast.success("Removed from library");
    } catch (err) {
      toast.error("Couldn't delete", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = async (entry: LibrarySummary, title: string) => {
    await renameReport(token, entry.id, title);
    setEntries((prev) =>
      prev?.map((e) => (e.id === entry.id ? { ...e, title } : e)) ?? null
    );
    toast.success("Renamed");
  };

  const handleMove = async (entry: LibrarySummary, target: string | null) => {
    await moveToFolder(token, entry.id, target);
    setEntries((prev) => {
      if (!prev) return null;
      // If a folder filter is active and the report moved elsewhere, drop it.
      if (folderId && target !== folderId) {
        return prev.filter((e) => e.id !== entry.id);
      }
      return prev.map((e) =>
        e.id === entry.id ? { ...e, folder_id: target } : e
      );
    });
    toast.success(target ? "Moved to folder" : "Removed from folder");
  };

  const handleTags = async (entry: LibrarySummary, next: string[]) => {
    const saved = await setReportTags(token, entry.id, next);
    setEntries((prev) => {
      if (!prev) return null;
      if (tagFilter && !saved.includes(tagFilter)) {
        return prev.filter((e) => e.id !== entry.id);
      }
      return prev.map((e) => (e.id === entry.id ? { ...e, tags: saved } : e));
    });
    loadFacets(); // a brand-new tag may now exist
    toast.success("Tags updated");
  };

  const handleCreateFolder = async (name: string): Promise<Folder> => {
    const folder = await createFolder(token, name);
    setFolders((prev) =>
      prev.some((f) => f.id === folder.id) ? prev : [...prev, folder].sort(byName)
    );
    return folder;
  };

  const handleDeleteFolder = async (folder: Folder) => {
    try {
      await deleteFolder(token, folder.id);
      setFolders((prev) => prev.filter((f) => f.id !== folder.id));
      if (folderId === folder.id) setFolderId(null);
      else loadEntries();
      toast.success(`Deleted folder “${folder.name}”`);
    } catch (err) {
      toast.error("Couldn't delete folder", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const clearFilters = () => {
    setFolderId(null);
    setStarredOnly(false);
    setTagFilter(null);
  };

  const activeFolderName = folders.find((f) => f.id === folderId)?.name;

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search titles and queries…"
            className="pl-9"
            aria-label="Search your library"
          />
        </div>

        <Button
          variant={starredOnly ? "horizon" : "outline"}
          size="sm"
          onClick={() => setStarredOnly((v) => !v)}
        >
          <Star className={cn("h-4 w-4", starredOnly && "fill-current")} />
          Starred
        </Button>

        {/* Folder filter */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <FolderIcon className="h-4 w-4" />
              {activeFolderName ?? "Folders"}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[13rem]">
            <DropdownMenuLabel>Filter by folder</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => setFolderId(null)}>
              {folderId === null && <Check className="h-4 w-4" />}
              <span className={cn(folderId !== null && "pl-6")}>All reports</span>
            </DropdownMenuItem>
            {folders.map((f) => (
              <DropdownMenuItem
                key={f.id}
                onSelect={(e) => {
                  e.preventDefault();
                  setFolderId(f.id);
                }}
                className="justify-between"
              >
                <span className="flex items-center gap-2 truncate">
                  {folderId === f.id ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <FolderIcon className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="truncate">{f.name}</span>
                </span>
                <button
                  type="button"
                  aria-label={`Delete folder ${f.name}`}
                  className="rounded p-1 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteFolder(f);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                setNewFolderOpen(true);
              }}
            >
              <FolderPlus className="h-4 w-4" />
              New folder…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Tag filter */}
        {tags.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <TagIcon className="h-4 w-4" />
                {tagFilter ?? "Tags"}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="max-h-72 overflow-auto">
              <DropdownMenuLabel>Filter by tag</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => setTagFilter(null)}>
                {tagFilter === null && <Check className="h-4 w-4" />}
                <span className={cn(tagFilter !== null && "pl-6")}>All tags</span>
              </DropdownMenuItem>
              {tags.map((t) => (
                <DropdownMenuItem key={t.id} onSelect={() => setTagFilter(t.name)}>
                  {tagFilter === t.name ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <TagIcon className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="truncate">{t.name}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {activeFilterCount > 0 && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {/* List */}
      {loading ? (
        <CenteredSpinner />
      ) : error ? (
        <EmptyNote
          title="Something went wrong"
          body={error}
          action={
            <Button variant="outline" size="sm" onClick={loadEntries}>
              Try again
            </Button>
          }
        />
      ) : !entries || entries.length === 0 ? (
        <EmptyNote
          icon={<LibraryIcon className="h-5 w-5" />}
          title={activeFilterCount || debouncedSearch ? "No matches" : "Nothing saved yet"}
          body={
            activeFilterCount || debouncedSearch
              ? "Try clearing filters or searching for something else."
              : "Run a research query and hit Save to keep it here."
          }
          action={
            activeFilterCount || debouncedSearch ? (
              <Button variant="outline" size="sm" onClick={() => { setSearch(""); clearFilters(); }}>
                Reset
              </Button>
            ) : (
              <Button asChild variant="horizon" size="sm">
                <Link href="/">Start researching</Link>
              </Button>
            )
          }
        />
      ) : (
        <ul className="space-y-3">
          {entries.map((entry) => (
            <LibraryRow
              key={entry.id}
              entry={entry}
              busy={busyId === entry.id}
              folderName={folders.find((f) => f.id === entry.folder_id)?.name}
              onToggleStar={() => handleToggleStar(entry)}
              onRename={() => setRenameTarget(entry)}
              onMove={() => setMoveTarget(entry)}
              onEditTags={() => setTagsTarget(entry)}
              onDelete={() => handleDelete(entry)}
            />
          ))}
        </ul>
      )}

      {/* Dialogs */}
      <RenameDialog
        target={renameTarget}
        onOpenChange={(open) => !open && setRenameTarget(null)}
        onSubmit={handleRename}
      />
      <TagsDialog
        target={tagsTarget}
        allTags={tags}
        onOpenChange={(open) => !open && setTagsTarget(null)}
        onSubmit={handleTags}
      />
      <MoveDialog
        target={moveTarget}
        folders={folders}
        onOpenChange={(open) => !open && setMoveTarget(null)}
        onMove={handleMove}
        onCreateFolder={handleCreateFolder}
      />
      <NewFolderDialog
        open={newFolderOpen}
        onOpenChange={setNewFolderOpen}
        onCreate={async (name) => {
          const f = await handleCreateFolder(name);
          setFolderId(f.id);
        }}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Row
// --------------------------------------------------------------------------- //

function LibraryRow({
  entry,
  busy,
  folderName,
  onToggleStar,
  onRename,
  onMove,
  onEditTags,
  onDelete,
}: {
  entry: LibrarySummary;
  busy: boolean;
  folderName?: string;
  onToggleStar: () => void;
  onRename: () => void;
  onMove: () => void;
  onEditTags: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="group glass rounded-2xl border border-border/70 p-4 transition-colors hover:border-border">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onToggleStar}
          aria-label={entry.starred ? "Unstar" : "Star"}
          className={cn(
            "mt-0.5 shrink-0 rounded-md p-1 transition-colors",
            entry.starred
              ? "text-accent"
              : "text-muted-foreground/60 hover:text-accent"
          )}
        >
          <Star className={cn("h-4 w-4", entry.starred && "fill-current")} />
        </button>

        <Link href={`/library/${entry.id}`} className="min-w-0 flex-1">
          <p className="truncate font-display text-lg font-medium leading-snug text-foreground">
            {entry.title}
          </p>
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {entry.query}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground/80">
            <span>{formatDate(entry.created_at)}</span>
            {folderName && (
              <span className="flex items-center gap-1">
                <FolderIcon className="h-3 w-3" />
                {folderName}
              </span>
            )}
            {entry.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="px-2 py-0">
                {tag}
              </Badge>
            ))}
          </div>
        </Link>

        <div className="flex shrink-0 items-center gap-1">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Open report">
            <Link href={`/library/${entry.id}`}>
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="More actions" disabled={busy}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <MoreHorizontal className="h-4 w-4" />
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={onRename}>
                <Pencil className="h-4 w-4" />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onMove}>
                <FolderInput className="h-4 w-4" />
                Move to folder
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onEditTags}>
                <TagIcon className="h-4 w-4" />
                Edit tags
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={onDelete}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------- //
// Dialogs
// --------------------------------------------------------------------------- //

export function RenameDialog({
  target,
  onOpenChange,
  onSubmit,
}: {
  target: LibrarySummary | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (entry: LibrarySummary, title: string) => Promise<void>;
}) {
  const [value, setValue] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (target) setValue(target.title);
  }, [target]);

  const submit = async () => {
    if (!target) return;
    const title = value.trim();
    if (!title) return;
    setSaving(true);
    try {
      await onSubmit(target, title);
      onOpenChange(false);
    } catch (err) {
      toast.error("Couldn't rename", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Rename report</DialogTitle>
          <DialogDescription>Give this saved report a clearer title.</DialogDescription>
        </DialogHeader>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          maxLength={200}
          autoFocus
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" size="sm">Cancel</Button>
          </DialogClose>
          <Button variant="horizon" size="sm" onClick={submit} disabled={saving || !value.trim()}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TagsDialog({
  target,
  allTags,
  onOpenChange,
  onSubmit,
}: {
  target: LibrarySummary | null;
  allTags: Tag[];
  onOpenChange: (open: boolean) => void;
  onSubmit: (entry: LibrarySummary, tags: string[]) => Promise<void>;
}) {
  const [current, setCurrent] = React.useState<string[]>([]);
  const [draft, setDraft] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (target) setCurrent(target.tags);
    setDraft("");
  }, [target]);

  const add = (raw: string) => {
    const name = raw.trim();
    if (!name) return;
    if (!current.some((t) => t.toLowerCase() === name.toLowerCase())) {
      setCurrent((prev) => [...prev, name]);
    }
    setDraft("");
  };

  const remove = (name: string) =>
    setCurrent((prev) => prev.filter((t) => t !== name));

  const suggestions = allTags
    .map((t) => t.name)
    .filter((n) => !current.some((c) => c.toLowerCase() === n.toLowerCase()));

  const submit = async () => {
    if (!target) return;
    setSaving(true);
    try {
      await onSubmit(target, current);
      onOpenChange(false);
    } catch (err) {
      toast.error("Couldn't update tags", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit tags</DialogTitle>
          <DialogDescription>
            Organize this report with freeform tags.
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-[2.25rem] flex-wrap gap-1.5">
          {current.length === 0 && (
            <span className="text-sm text-muted-foreground">No tags yet.</span>
          )}
          {current.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1">
              {tag}
              <button
                type="button"
                aria-label={`Remove ${tag}`}
                onClick={() => remove(tag)}
                className="rounded-full hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>

        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(draft);
            }
          }}
          placeholder="Type a tag and press Enter"
          maxLength={80}
        />

        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {suggestions.slice(0, 12).map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => add(name)}
                className="rounded-full border border-border/70 px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-accent hover:text-accent"
              >
                + {name}
              </button>
            ))}
          </div>
        )}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" size="sm">Cancel</Button>
          </DialogClose>
          <Button variant="horizon" size="sm" onClick={submit} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save tags
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MoveDialog({
  target,
  folders,
  onOpenChange,
  onMove,
  onCreateFolder,
}: {
  target: LibrarySummary | null;
  folders: Folder[];
  onOpenChange: (open: boolean) => void;
  onMove: (entry: LibrarySummary, folderId: string | null) => Promise<void>;
  onCreateFolder: (name: string) => Promise<Folder>;
}) {
  const [busy, setBusy] = React.useState(false);
  const [newName, setNewName] = React.useState("");

  React.useEffect(() => {
    setNewName("");
  }, [target]);

  const move = async (folderId: string | null) => {
    if (!target) return;
    setBusy(true);
    try {
      await onMove(target, folderId);
      onOpenChange(false);
    } catch (err) {
      toast.error("Couldn't move report", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  };

  const createAndMove = async () => {
    const name = newName.trim();
    if (!name || !target) return;
    setBusy(true);
    try {
      const folder = await onCreateFolder(name);
      await onMove(target, folder.id);
      onOpenChange(false);
    } catch (err) {
      toast.error("Couldn't create folder", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Move to folder</DialogTitle>
          <DialogDescription>
            Choose a folder for this report, or create a new one.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-56 space-y-1 overflow-auto">
          <FolderChoice
            active={target?.folder_id == null}
            label="No folder"
            icon={<X className="h-4 w-4" />}
            disabled={busy}
            onClick={() => move(null)}
          />
          {folders.map((f) => (
            <FolderChoice
              key={f.id}
              active={target?.folder_id === f.id}
              label={f.name}
              icon={<FolderIcon className="h-4 w-4" />}
              disabled={busy}
              onClick={() => move(f.id)}
            />
          ))}
        </div>

        <div className="flex items-center gap-2 border-t border-border/60 pt-4">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createAndMove()}
            placeholder="New folder name"
            maxLength={120}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={createAndMove}
            disabled={busy || !newName.trim()}
          >
            <FolderPlus className="h-4 w-4" />
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function FolderChoice({
  active,
  label,
  icon,
  disabled,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50",
        active
          ? "border-accent/60 bg-accent/10 text-foreground"
          : "border-border/60 hover:border-border hover:bg-secondary/50"
      )}
    >
      <span className="flex items-center gap-2 truncate">
        {icon}
        <span className="truncate">{label}</span>
      </span>
      {active && <Check className="h-4 w-4 text-accent" />}
    </button>
  );
}

function NewFolderDialog({
  open,
  onOpenChange,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (name: string) => Promise<void>;
}) {
  const [name, setName] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (open) setName("");
  }, [open]);

  const submit = async () => {
    const value = name.trim();
    if (!value) return;
    setSaving(true);
    try {
      await onCreate(value);
      onOpenChange(false);
    } catch (err) {
      toast.error("Couldn't create folder", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New folder</DialogTitle>
          <DialogDescription>Group related reports together.</DialogDescription>
        </DialogHeader>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Folder name"
          maxLength={120}
          autoFocus
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" size="sm">Cancel</Button>
          </DialogClose>
          <Button variant="horizon" size="sm" onClick={submit} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Shared bits
// --------------------------------------------------------------------------- //

function CenteredSpinner() {
  return (
    <div className="flex justify-center py-20 text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  );
}

function EmptyNote({
  icon,
  title,
  body,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center gap-3 rounded-2xl border border-border/70 px-6 py-16 text-center">
      {icon && (
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-border/70 bg-secondary/40 text-accent">
          {icon}
        </span>
      )}
      <div>
        <p className="font-display text-lg font-medium">{title}</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{body}</p>
      </div>
      {action}
    </div>
  );
}

function byName(a: Folder, b: Folder): number {
  return a.name.localeCompare(b.name);
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
