import { createClient, type SupabaseClient, type Session } from "@supabase/supabase-js";

// These should be replaced with actual values from a Supabase project
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";

let supabaseInstance: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
  if (!supabaseInstance) {
    supabaseInstance = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return supabaseInstance;
}

export type SignUpResult =
  | { error: string }
  | { error: null; confirmed: true }
  | { error: null; confirmed: false };

export async function signUp(
  email: string,
  password: string,
): Promise<SignUpResult> {
  const supabase = getSupabase();
  if (!supabase) return { error: "Supabase not configured." };
  const { data, error } = await supabase.auth.signUp({ email: email.trim(), password });
  if (error) return { error: error.message };

  // Fake signup — Supabase returns a user with no identities to prevent
  // email enumeration when the address is already registered.
  if (data.user && data.user.identities?.length === 0) {
    return { error: "An account with this email already exists." };
  }

  // Auto-confirmed (email confirm disabled in Supabase dashboard) —
  // a session is returned immediately, no OTP needed.
  if (data.session) {
    return { error: null, confirmed: true };
  }

  return { error: null, confirmed: false };
}

export async function signIn(
  email: string,
  password: string,
): Promise<{ error: string | null }> {
  const supabase = getSupabase();
  if (!supabase) return { error: "Supabase not configured." };
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  return { error: error?.message ?? null };
}

export async function verifyOtp(
  email: string,
  token: string,
): Promise<{ error: string | null }> {
  const supabase = getSupabase();
  if (!supabase) return { error: "Supabase not configured." };
  const { error } = await supabase.auth.verifyOtp({
    email: email.trim(),
    token,
    type: "signup",
  });
  return { error: error?.message ?? null };
}

export async function resendSignupOtp(
  email: string,
): Promise<{ error: string | null }> {
  const supabase = getSupabase();
  if (!supabase) return { error: "Supabase not configured." };
  const { error } = await supabase.auth.resend({ type: "signup", email: email.trim() });
  return { error: error?.message ?? null };
}

export async function signOut(): Promise<void> {
  const supabase = getSupabase();
  if (supabase) {
    await supabase.auth.signOut();
  }
}

export async function getSession(): Promise<Session | null> {
  const supabase = getSupabase();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session;
}

export function onAuthStateChange(
  callback: (session: Session | null) => void,
): (() => void) | undefined {
  const supabase = getSupabase();
  if (!supabase) return undefined;
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    callback(session);
  });
  return () => data.subscription.unsubscribe();
}
