/**
 * Platform detection for dual-mode (Tauri desktop / web) operation.
 */

/** True when running inside the Tauri desktop shell. */
export const IS_TAURI = Boolean(
  typeof window !== "undefined" &&
    (window as Record<string, unknown>).__TAURI_INTERNALS__,
);

/**
 * Base URL for the backend API.
 * - Tauri mode: set dynamically by sidecarApi.initialize() after port discovery.
 * - Web mode: read from VITE_API_URL env var (e.g. "https://api.explify.app").
 */
export const API_BASE_URL: string | undefined = IS_TAURI
  ? undefined // resolved at runtime via invoke("get_sidecar_port")
  : import.meta.env.VITE_API_URL;

/**
 * Application version string.
 * - Tauri mode: populated by Tauri's getVersion() at runtime.
 * - Web mode: injected at build time via VITE_APP_VERSION.
 */
export const APP_VERSION: string =
  import.meta.env.VITE_APP_VERSION ?? "0.0.0";
