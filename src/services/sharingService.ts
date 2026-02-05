/**
 * Supabase-only sharing management.
 *
 * Handles add/remove/list of sharing relationships.
 * Shared content is pulled during sync and cached locally by the sidecar.
 */

import { getSupabase, getSession } from "./supabase";

export interface ShareRecipient {
  share_id: number;
  recipient_user_id: string;
  recipient_email: string;
  created_at: string;
}

export interface ShareSource {
  share_id: number;
  sharer_user_id: string;
  sharer_email: string;
  created_at: string;
}

async function requireSupabaseSession() {
  const supabase = getSupabase();
  if (!supabase) throw new Error("Supabase not configured.");
  const session = await getSession();
  if (!session?.user) throw new Error("Not signed in.");
  return { supabase, userId: session.user.id, email: session.user.email };
}

export async function lookupUserByEmail(
  email: string,
): Promise<{ user_id: string; email: string } | null> {
  const { supabase } = await requireSupabaseSession();
  const { data, error } = await supabase.rpc("lookup_user_by_email", {
    target_email: email.trim(),
  });
  if (error) throw new Error(error.message);
  if (!data || data.length === 0) return null;
  return data[0];
}

export async function addShareRecipient(
  recipientEmail: string,
): Promise<void> {
  const { supabase, userId } = await requireSupabaseSession();

  // Look up the recipient user
  const recipient = await lookupUserByEmail(recipientEmail);
  if (!recipient) {
    throw new Error("No user found with that email address.");
  }

  if (recipient.user_id === userId) {
    throw new Error("Cannot share with yourself.");
  }

  // Insert the sharing relationship
  const { error } = await supabase.from("user_shares").insert({
    sharer_id: userId,
    recipient_id: recipient.user_id,
  });

  if (error) {
    if (error.code === "23505") {
      throw new Error("Already sharing with this user.");
    }
    throw new Error(error.message);
  }
}

export async function removeShareRecipient(shareId: number): Promise<void> {
  const { supabase } = await requireSupabaseSession();
  const { error } = await supabase
    .from("user_shares")
    .delete()
    .eq("id", shareId);
  if (error) throw new Error(error.message);
}

export async function getMyShareRecipients(): Promise<ShareRecipient[]> {
  const { supabase } = await requireSupabaseSession();
  const { data, error } = await supabase.rpc("get_my_share_recipients");
  if (error) throw new Error(error.message);
  return data ?? [];
}

export async function getMyShareSources(): Promise<ShareSource[]> {
  const { supabase } = await requireSupabaseSession();
  const { data, error } = await supabase.rpc("get_my_share_sources");
  if (error) throw new Error(error.message);
  return data ?? [];
}
