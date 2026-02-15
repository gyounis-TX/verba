/**
 * Bidirectional sync engine for desktop ↔ cloud sync.
 *
 * NOTE: Cloud sync is currently disabled during the AWS migration.
 * The sync engine relied on direct Supabase client calls which have been
 * removed. Desktop mode works fully offline via SQLite. Web mode reads/writes
 * directly from RDS via the sidecar. A future iteration will re-enable
 * desktop ↔ RDS sync via sidecar API endpoints.
 *
 * Strategy: Last-write-wins by `updated_at` timestamp.
 * API keys are NEVER synced — they remain local only.
 */

import { sidecarApi } from "./sidecarApi";
import { IS_TAURI } from "./platform";

type SyncTable = "settings" | "history" | "templates" | "letters" | "teaching_points";

export function isCloudSyncAvailable(): boolean {
  // Cloud sync is disabled during AWS migration.
  // Will be re-enabled when sidecar sync endpoints are ready.
  return false;
}

// ---------------------------------------------------------------------------
// Pull: download from cloud → merge into local via sidecar
// ---------------------------------------------------------------------------

export async function pullRemoteData(): Promise<void> {
  if (!IS_TAURI) return; // Web mode: backend reads directly from RDS
  // TODO: Re-enable via sidecar sync API after AWS migration
  return;
}

// ---------------------------------------------------------------------------
// Push queue (disabled — cloud sync not available)
// ---------------------------------------------------------------------------

export function queueChange(
  _table: SyncTable,
  _operation: "upsert" | "delete",
  _data: Record<string, unknown>,
): void {
  if (!IS_TAURI) return; // Web mode: backend writes directly to RDS
  if (!isCloudSyncAvailable()) return;
  // TODO: Re-enable via sidecar sync API after AWS migration
}

export async function pushAllLocal(): Promise<void> {
  if (!IS_TAURI) return;
  // TODO: Re-enable via sidecar sync API after AWS migration
  return;
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
  if (!IS_TAURI) return; // Web mode: backend writes directly to RDS
  if (!isCloudSyncAvailable()) return;
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
  if (!IS_TAURI) return;
  if (!isCloudSyncAvailable()) return;
  queueChange("settings", "upsert", {
    key,
    value,
    updated_at: new Date().toISOString(),
  });
}

/**
 * Delete a record from cloud by sync_id.
 */
export async function deleteFromCloud(
  _table: SyncTable,
  _syncId: string,
): Promise<void> {
  if (!IS_TAURI) return;
  // TODO: Re-enable via sidecar sync API after AWS migration
  return;
}

// Keep old name as alias for callers that haven't updated
export const deleteFromSupabase = deleteFromCloud;

// ---------------------------------------------------------------------------
// Full sync
// ---------------------------------------------------------------------------

export async function fullSync(): Promise<void> {
  if (!IS_TAURI) return;
  // Cloud sync disabled during AWS migration
  // TODO: Re-enable via sidecar sync API
  return;
}
