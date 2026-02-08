/**
 * Bidirectional sync engine for Supabase cloud sync.
 *
 * Strategy: Last-write-wins by `updated_at` timestamp.
 * API keys are NEVER synced — they remain local only.
 */

import { getSupabase, getSession } from "./supabase";
import { sidecarApi } from "./sidecarApi";
import { pullSharedConfig } from "./sharedConfig";
import { IS_TAURI, APP_VERSION } from "./platform";

// ---------------------------------------------------------------------------
// Pull shared content (teaching points + templates from other users)
// ---------------------------------------------------------------------------

async function pullSharedContent(): Promise<void> {
  const supabase = getSupabase();
  if (!supabase) return;

  const session = await getSession();
  if (!session?.user) return;

  try {
    // Pull shared teaching points via RPC
    const { data: sharedTPs, error: tpError } = await supabase.rpc(
      "get_shared_teaching_points",
    );
    if (tpError) {
      console.error("Failed to pull shared teaching points:", tpError.message);
    } else {
      await sidecarApi.syncSharedTeachingPoints(sharedTPs ?? []);
    }
  } catch (err) {
    console.error("Failed to sync shared teaching points:", err);
  }

  try {
    // Pull shared templates via RPC
    const { data: sharedTemplates, error: tmplError } = await supabase.rpc(
      "get_shared_templates",
    );
    if (tmplError) {
      console.error("Failed to pull shared templates:", tmplError.message);
    } else {
      await sidecarApi.syncSharedTemplates(sharedTemplates ?? []);
    }
  } catch (err) {
    console.error("Failed to sync shared templates:", err);
  }
}

type SyncTable = "settings" | "history" | "templates" | "letters" | "teaching_points";

const SYNC_TABLES: SyncTable[] = [
  "settings",
  "history",
  "templates",
  "letters",
  "teaching_points",
];

// Keys that should never be synced to the cloud
const EXCLUDED_SETTINGS_KEYS = new Set([
  "claude_api_key",
  "openai_api_key",
  "aws_access_key_id",
  "aws_secret_access_key",
  "api_key",
]);

interface SyncQueueItem {
  table: SyncTable;
  operation: "upsert" | "delete";
  data: Record<string, unknown>;
  timestamp: string;
}

let syncQueue: SyncQueueItem[] = [];
let isSyncing = false;

export function isSupabaseConfigured(): boolean {
  return getSupabase() !== null;
}

// ---------------------------------------------------------------------------
// Pull: download from Supabase → merge into local via sidecar
// ---------------------------------------------------------------------------

export async function pullRemoteData(): Promise<void> {
  const supabase = getSupabase();
  if (!supabase) return;

  const session = await getSession();
  const userId = session?.user?.id;

  for (const table of SYNC_TABLES) {
    try {
      // Always filter by user_id so we only pull the current user's rows.
      // This is defense-in-depth on top of RLS policies.
      if (!userId) continue;

      let query = supabase
        .from(table)
        .select("*")
        .eq("user_id", userId)
        .order("updated_at", { ascending: false });

      const { data, error } = await query;

      if (error) {
        console.error(`Sync pull error for ${table}:`, error.message);
        continue;
      }

      if (!data || data.length === 0) continue;

      // Filter out excluded settings
      const filtered =
        table === "settings"
          ? data.filter(
              (row) => !EXCLUDED_SETTINGS_KEYS.has(row.key as string),
            )
          : data;

      if (filtered.length === 0) continue;

      // Batch merge via sidecar
      await sidecarApi.syncMerge(table, filtered);
    } catch (err) {
      console.error(`Sync pull failed for ${table}:`, err);
    }
  }

  // Pull shared config (admin-deployed API keys / credentials)
  try {
    const sharedConfig = await pullSharedConfig();
    const configUpdate: Record<string, string> = {};
    if (sharedConfig.claude_api_key) {
      configUpdate.claude_api_key = sharedConfig.claude_api_key;
    }
    if (sharedConfig.aws_access_key_id) {
      configUpdate.aws_access_key_id = sharedConfig.aws_access_key_id;
    }
    if (sharedConfig.aws_secret_access_key) {
      configUpdate.aws_secret_access_key = sharedConfig.aws_secret_access_key;
    }
    if (sharedConfig.aws_region) {
      configUpdate.aws_region = sharedConfig.aws_region;
    }
    if (sharedConfig.llm_provider) {
      configUpdate.llm_provider = sharedConfig.llm_provider;
    }
    if (Object.keys(configUpdate).length > 0) {
      await sidecarApi.updateSettings(configUpdate);
    }
  } catch (err) {
    console.error("Failed to pull shared config:", err);
  }

  // Pull shared content (teaching points + templates from other users)
  await pullSharedContent();
}

// ---------------------------------------------------------------------------
// Push queue
// ---------------------------------------------------------------------------

export function queueChange(
  table: SyncTable,
  operation: "upsert" | "delete",
  data: Record<string, unknown>,
): void {
  // Don't queue setting changes for excluded keys
  if (
    table === "settings" &&
    EXCLUDED_SETTINGS_KEYS.has(data.key as string)
  ) {
    return;
  }

  syncQueue.push({
    table,
    operation,
    data,
    timestamp: new Date().toISOString(),
  });

  // Debounced push
  schedulePush();
}

let pushTimer: ReturnType<typeof setTimeout> | null = null;

function schedulePush(): void {
  if (pushTimer) clearTimeout(pushTimer);
  pushTimer = setTimeout(() => pushQueuedChanges(), 2000);
}

async function pushQueuedChanges(): Promise<void> {
  if (isSyncing || syncQueue.length === 0) return;
  isSyncing = true;

  const supabase = getSupabase();
  if (!supabase) {
    isSyncing = false;
    return;
  }

  const session = await getSession();
  if (!session?.user?.id) {
    isSyncing = false;
    return;
  }
  const userId = session.user.id;

  const batch = [...syncQueue];
  syncQueue = [];

  for (const item of batch) {
    try {
      if (item.operation === "upsert") {
        const { id: _localId, ...rest } = item.data as Record<string, unknown>;
        const row = { ...rest, user_id: userId };

        if (item.table === "settings") {
          const { error } = await supabase
            .from(item.table)
            .upsert(row, { onConflict: "user_id,key" });
          if (error) {
            console.error(`Sync push error for ${item.table}:`, error.message);
            syncQueue.push(item);
          }
        } else {
          const { error } = await supabase
            .from(item.table)
            .upsert(row, { onConflict: "sync_id" });
          if (error) {
            console.error(`Sync push error for ${item.table}:`, error.message);
            syncQueue.push(item);
          }
        }
      } else if (item.operation === "delete") {
        if (item.table === "settings") {
          const key = item.data.key;
          if (key != null) {
            const { error } = await supabase
              .from(item.table)
              .delete()
              .eq("user_id", userId)
              .eq("key", key);
            if (error) {
              console.error(`Sync delete error for ${item.table}:`, error.message);
            }
          }
        } else {
          const syncId = item.data.sync_id;
          if (syncId != null) {
            const { error } = await supabase
              .from(item.table)
              .delete()
              .eq("sync_id", syncId);
            if (error) {
              console.error(`Sync delete error for ${item.table}:`, error.message);
            }
          }
        }
      }
    } catch (err) {
      console.error("Sync push failed:", err);
      syncQueue.push(item);
    }
  }

  isSyncing = false;

  // If items were re-queued, schedule another push
  if (syncQueue.length > 0) {
    schedulePush();
  }
}

// ---------------------------------------------------------------------------
// Push all local data on first sign-in
// ---------------------------------------------------------------------------

export async function pushAllLocal(): Promise<void> {
  if (!IS_TAURI) return; // Web mode: backend writes directly to Supabase
  const supabase = getSupabase();
  if (!supabase) return;

  const session = await getSession();
  if (!session?.user?.id) return;
  const userId = session.user.id;

  for (const table of SYNC_TABLES) {
    try {
      const rows = await sidecarApi.syncExportAll(table);
      if (!rows || rows.length === 0) continue;

      const prepared = rows
        .filter((row) => {
          // Skip excluded settings
          if (table === "settings" && EXCLUDED_SETTINGS_KEYS.has(row.key as string)) {
            return false;
          }
          // Skip built-in templates
          if (table === "templates" && (row.is_builtin === 1 || row.is_builtin === true)) {
            return false;
          }
          return true;
        })
        .map((row) => {
          const { id: _localId, ...rest } = row as Record<string, unknown>;
          const cleaned: Record<string, unknown> = { ...rest, user_id: userId };
          // Coerce SQLite booleans
          if ("liked" in cleaned) cleaned.liked = Boolean(cleaned.liked);
          if ("copied" in cleaned) cleaned.copied = Boolean(cleaned.copied);
          if ("is_builtin" in cleaned) cleaned.is_builtin = Boolean(cleaned.is_builtin);
          return cleaned;
        });

      if (prepared.length === 0) continue;

      // Batch upsert
      const conflict = table === "settings" ? "user_id,key" : "sync_id";
      const { error } = await supabase
        .from(table)
        .upsert(prepared, { onConflict: conflict });

      if (error) {
        console.error(`Push all local error for ${table}:`, error.message);
      }
    } catch (err) {
      console.error(`Push all local failed for ${table}:`, err);
    }
  }
}

// ---------------------------------------------------------------------------
// Helpers for UI mutations
// ---------------------------------------------------------------------------

/**
 * After a sidecar CRUD mutation, fetch the full row and queue it for sync.
 */
export async function queueUpsertAfterMutation(
  table: SyncTable,
  recordId: number,
): Promise<void> {
  if (!IS_TAURI) return; // Web mode: backend writes directly to Supabase
  if (!isSupabaseConfigured()) return;
  try {
    const row = await sidecarApi.syncExportRecord(table, recordId);
    queueChange(table, "upsert", row);
  } catch (err) {
    console.error(`queueUpsertAfterMutation failed for ${table}/${recordId}:`, err);
  }
}

/**
 * Queue a settings key/value for sync.
 */
export function queueSettingsUpsert(key: string, value: string): void {
  if (!isSupabaseConfigured()) return;
  queueChange("settings", "upsert", {
    key,
    value,
    updated_at: new Date().toISOString(),
  });
}

/**
 * Delete a record from Supabase directly by sync_id.
 * Used for hard deletes (v1 — no cross-device delete propagation).
 */
export async function deleteFromSupabase(
  table: SyncTable,
  syncId: string,
): Promise<void> {
  if (!IS_TAURI) return; // Web mode: backend writes directly to Supabase
  const supabase = getSupabase();
  if (!supabase || !syncId) return;
  try {
    const { error } = await supabase
      .from(table)
      .delete()
      .eq("sync_id", syncId);
    if (error) {
      console.error(`Supabase delete error for ${table}:`, error.message);
    }
  } catch (err) {
    console.error(`Supabase delete failed for ${table}:`, err);
  }
}

// ---------------------------------------------------------------------------
// Full sync
// ---------------------------------------------------------------------------

export async function fullSync(): Promise<void> {
  if (!IS_TAURI) return; // Web mode: backend writes directly to Supabase
  await pushAllLocal();
  await pullRemoteData();
  await pushQueuedChanges();
  await reportAppVersion();
}

async function reportAppVersion(): Promise<void> {
  const supabase = getSupabase();
  if (!supabase) return;

  const session = await getSession();
  if (!session?.user?.id) return;

  try {
    await supabase.from("settings").upsert(
      {
        user_id: session.user.id,
        key: "app_version",
        value: APP_VERSION,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id,key" },
    );
  } catch (err) {
    console.error("Failed to report app version:", err);
  }
}
