/**
 * Saved-library data layer (Phase 11) — talks to the FastAPI backend, not
 * Supabase directly.
 *
 * Persistence moved server-side: the backend owns the normalized library
 * tables and scopes every row to the verified JWT's user. So each call here
 * hits the backend's /library, /folders, /tags endpoints with the user's
 * Supabase access token in the Authorization header. (The earlier version
 * wrote straight to a Supabase `reports` table from the browser; that's been
 * replaced.)
 *
 * `isLibraryEnabled()` still gates the UI on whether Supabase sign-in is
 * configured on the frontend — without it there's no token to send, and the
 * library simply doesn't appear.
 */

import { API_BASE_URL, ApiError } from "@/lib/api";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import type { ResearchResult } from "@/lib/types";

/** Lightweight row for list views (no heavy result JSON). */
export interface LibrarySummary {
  id: string;
  title: string;
  query: string;
  status: string;
  starred: boolean;
  folder_id: string | null;
  tags: string[];
  created_at: string;
}

/** Full entry: summary metadata + the reconstructed ResearchResult. */
export interface LibraryEntry extends LibrarySummary {
  citation_style: string;
  pdf_url: string | null;
  follow_ups: string[];
  result: ResearchResult;
}

export interface Folder {
  id: string;
  name: string;
}

export interface Tag {
  id: string;
  name: string;
}

/** Optional filters for the list view — mapped to query params. */
export interface LibraryFilters {
  search?: string;
  folderId?: string;
  starred?: boolean;
  tag?: string;
}

/** Metadata that travels with a manual save (defaults mirror the backend). */
export interface SaveOptions {
  citationStyle?: string;
  targetLanguage?: string;
  numSubQuestions?: number;
  maxResultsPerSubquestion?: number;
  title?: string;
}

export function isLibraryEnabled(): boolean {
  return isSupabaseConfigured();
}

// --------------------------------------------------------------------------- //
// Fetch helper
// --------------------------------------------------------------------------- //

async function authed<T>(
  token: string | undefined | null,
  path: string,
  init: RequestInit = {}
): Promise<T> {
  if (!token) {
    throw new ApiError("Sign in to use your library.", 401);
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let detail: string | undefined;
    try {
      detail = ((await res.json()) as { detail?: string }).detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      detail ?? `Request failed (${res.status} ${res.statusText}).`,
      res.status
    );
  }

  return (await res.json()) as T;
}

function withQuery(path: string, filters?: LibraryFilters): string {
  if (!filters) return path;
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.folderId) params.set("folder_id", filters.folderId);
  if (typeof filters.starred === "boolean")
    params.set("starred", String(filters.starred));
  if (filters.tag) params.set("tag", filters.tag);
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

// --------------------------------------------------------------------------- //
// Library entries
// --------------------------------------------------------------------------- //

/** Lists the current user's saved reports, newest first. */
export function listReports(
  token: string | null | undefined,
  filters?: LibraryFilters
): Promise<LibrarySummary[]> {
  return authed<LibrarySummary[]>(token, withQuery("/library", filters));
}

/** Fetches one saved report in full, or null if it doesn't exist / isn't yours. */
export async function getReport(
  token: string | null | undefined,
  id: string
): Promise<LibraryEntry | null> {
  try {
    return await authed<LibraryEntry>(token, `/library/${id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/** Persists a completed report for the current user; returns the new id. */
export async function saveReport(
  token: string | null | undefined,
  result: ResearchResult,
  options: SaveOptions = {}
): Promise<string> {
  const data = await authed<{ id: string }>(token, "/library", {
    method: "POST",
    body: JSON.stringify({
      result,
      citation_style: options.citationStyle ?? "apa",
      target_language: options.targetLanguage ?? "English",
      num_sub_questions: options.numSubQuestions ?? null,
      max_results_per_subquestion: options.maxResultsPerSubquestion ?? 5,
      title: options.title ?? null,
    }),
  });
  return data.id;
}

/** Removes a saved report. */
export async function deleteReport(
  token: string | null | undefined,
  id: string
): Promise<void> {
  await authed<{ ok: boolean }>(token, `/library/${id}`, { method: "DELETE" });
}

/** Renames a saved report. */
export async function renameReport(
  token: string | null | undefined,
  id: string,
  title: string
): Promise<void> {
  await authed(token, `/library/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/** Stars / unstars a saved report. */
export async function setStarred(
  token: string | null | undefined,
  id: string,
  starred: boolean
): Promise<void> {
  await authed(token, `/library/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ starred }),
  });
}

/** Moves a report into a folder, or out of any folder when `folderId` is null. */
export async function moveToFolder(
  token: string | null | undefined,
  id: string,
  folderId: string | null
): Promise<void> {
  const body =
    folderId === null ? { clear_folder: true } : { folder_id: folderId };
  await authed(token, `/library/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Replaces a report's tags; returns the resulting tag names. */
export async function setReportTags(
  token: string | null | undefined,
  id: string,
  tags: string[]
): Promise<string[]> {
  const data = await authed<{ tags: string[] }>(token, `/library/${id}/tags`, {
    method: "PUT",
    body: JSON.stringify({ tags }),
  });
  return data.tags;
}

// --------------------------------------------------------------------------- //
// Folders & tags
// --------------------------------------------------------------------------- //

export function listFolders(
  token: string | null | undefined
): Promise<Folder[]> {
  return authed<Folder[]>(token, "/folders");
}

export function createFolder(
  token: string | null | undefined,
  name: string
): Promise<Folder> {
  return authed<Folder>(token, "/folders", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteFolder(
  token: string | null | undefined,
  id: string
): Promise<void> {
  await authed<{ ok: boolean }>(token, `/folders/${id}`, { method: "DELETE" });
}

export function listTags(token: string | null | undefined): Promise<Tag[]> {
  return authed<Tag[]>(token, "/tags");
}
