/**
 * Supabase is entirely optional. When the env vars are absent the whole app
 * still runs — research works, there's just no sign-in and nothing is saved.
 * Every Supabase entry point checks `isSupabaseConfigured()` first and the
 * UI degrades gracefully (the auth button and library simply don't appear).
 */

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export function isSupabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}
