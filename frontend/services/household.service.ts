/**
 * household.service.ts
 *
 * Thin wrapper around the household-level REST endpoints.
 * Exports both a named function and a service object for backward compatibility.
 */

import { BACKEND_BASE as _BASE, DEFAULT_HOUSEHOLD_ID, probe, type ProbeResult } from "@/services/api.config";

// Allow overriding via env
const BACKEND_BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL
    ? process.env.NEXT_PUBLIC_BACKEND_URL
    : _BASE;

const TIMEOUT_MS = 5000;

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DeleteHouseholdResult {
  household_id: string;
  status: "deleted";
  items_deleted: Record<string, number>;
  total: number;
}

// ─── Named export ─────────────────────────────────────────────────────────────

/**
 * DELETE /household/{household_id}
 *
 * Permanently removes all DynamoDB data for this household:
 * graph, patterns, rules, action log, RTE audit log, metrics.
 *
 * Throws on non-2xx responses so the caller can handle the error.
 */
export async function deleteHousehold(
  householdId: string,
): Promise<DeleteHouseholdResult> {
  return fetchJSON<DeleteHouseholdResult>(
    `${BACKEND_BASE}/household/${householdId}`,
    { method: "DELETE" },
  );
}

// ─── Service object (legacy / debug page compatibility) ───────────────────────

export const householdService = {
  /** DELETE /household/{id} — wipe all household data */
  deleteHousehold,

  /** GET /health — check if backend is reachable */
  async getHealth(): Promise<ProbeResult> {
    return probe(`${BACKEND_BASE}/health`);
  },

  /** Alias — boolean availability check */
  async isBackendAvailable(): Promise<boolean> {
    const r = await probe(`${BACKEND_BASE}/health`);
    return r.status === "ok";
  },

  /** GET /graph/{household_id} — graph summary */
  async getGraph(householdId: string = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult> {
    return probe(`${BACKEND_BASE}/graph/${householdId}`);
  },

  /** GET /graph/{household_id}/members */
  async getMembers(householdId: string = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult> {
    return probe(`${BACKEND_BASE}/graph/${householdId}/members`);
  },

  /** GET /graph/{household_id}/devices */
  async getDevices(householdId: string = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult> {
    return probe(`${BACKEND_BASE}/graph/${householdId}/devices`);
  },

  /** GET /graph/{household_id}/full */
  async getGraphSummary(householdId: string = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult> {
    return probe(`${BACKEND_BASE}/graph/${householdId}/full`);
  },
};
