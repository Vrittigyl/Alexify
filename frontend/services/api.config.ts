/**
 * Backend API configuration — shared by all discovery services.
 * Set NEXT_PUBLIC_BACKEND_URL in .env.local to point at a live backend.
 * Defaults to http://localhost:8000 (local uvicorn).
 */

export const BACKEND_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL)
    ? process.env.NEXT_PUBLIC_BACKEND_URL
    : "http://localhost:8000";

/** Default household used in the demo / Sharma family seed */
export const DEFAULT_HOUSEHOLD_ID = "hh_xk92p_sharma";

/** Timeout for all discovery probes */
export const PROBE_TIMEOUT_MS = 3000;

// ─── Named demo events the backend supports ───────────────────────────────────
export const NAMED_EVENTS = [
  "water_tank_full",
  "board_exam",
  "guest_arrival",
  "pressure_cooker_5_whistles",
  "dadaji_medicine",
  "fridge_door_open",
] as const;

export type NamedEvent = typeof NAMED_EVENTS[number];

// ─── Fetch helper with timeout ────────────────────────────────────────────────

export async function fetchWithTimeout<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs = PROBE_TIMEOUT_MS,
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Probe result shape ───────────────────────────────────────────────────────

export type ProbeStatus = "ok" | "error" | "pending";

export interface ProbeResult<T = unknown> {
  status: ProbeStatus;
  url: string;
  data?: T;
  error?: string;
  latencyMs?: number;
}

export async function probe<T>(url: string, options?: RequestInit): Promise<ProbeResult<T>> {
  const start = performance.now();
  try {
    const data = await fetchWithTimeout<T>(url, options ?? {});
    return { status: "ok", url, data, latencyMs: Math.round(performance.now() - start) };
  } catch (err) {
    return {
      status: "error",
      url,
      error: err instanceof Error ? err.message : String(err),
      latencyMs: Math.round(performance.now() - start),
    };
  }
}
