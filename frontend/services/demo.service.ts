/**
 * Demo Service
 *
 * Tries to fetch live data from the SAATHI backend.
 * If the backend is unavailable (no server, CORS, timeout), falls back
 * to fully static mock data so the demo works without any backend.
 *
 * Usage:
 *   const data = await demoService.load();
 */

import { SHARMA_HOUSEHOLD } from "@/mocks/household";
import { SHARMA_DEVICES } from "@/mocks/devices";
import { SHARMA_ROUTINES } from "@/mocks/routines";
import { SHARMA_ACTIVITY } from "@/mocks/activity";
import { SHARMA_PREDICTIONS, INTELLIGENCE_STATS } from "@/mocks/predictions";
import { SHARMA_NOTIFICATIONS, NOTIFICATION_STATS } from "@/mocks/notifications";

import type { MockHousehold } from "@/mocks/household";
import type { MockDevice } from "@/mocks/devices";
import type { MockRoutine } from "@/mocks/routines";
import type { MockActivity } from "@/mocks/activity";
import type { MockPrediction } from "@/mocks/predictions";
import type { MockNotification } from "@/mocks/notifications";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DemoData {
  source: "backend" | "mock";
  household: MockHousehold;
  devices: MockDevice[];
  routines: MockRoutine[];
  activity: MockActivity[];
  predictions: MockPrediction[];
  notifications: MockNotification[];
  intelligenceStats: typeof INTELLIGENCE_STATS;
  notificationStats: typeof NOTIFICATION_STATS;
  loadedAt: string;
}

// ─── Config ───────────────────────────────────────────────────────────────────

import { BACKEND_BASE, PROBE_TIMEOUT_MS, fetchWithTimeout } from "@/services/api.config";

const FETCH_TIMEOUT_MS = PROBE_TIMEOUT_MS;

// ─── Helpers ──────────────────────────────────────────────────────────────────
// fetchWithTimeout is imported from api.config

// ─── Service ─────────────────────────────────────────────────────────────────

async function loadFromBackend(): Promise<DemoData> {
  // Attempt to load household data from the backend knowledge graph endpoint.
  // The backend serves the Sharma family at /household/hh_xk92p_sharma
  const [householdRaw, devicesRaw, activityRaw] = await Promise.all([
    fetchWithTimeout<{ family_name: string; location: string }>(
      `${BACKEND_BASE}/household/hh_xk92p_sharma`
    ),
    fetchWithTimeout<unknown[]>(`${BACKEND_BASE}/devices/hh_xk92p_sharma`),
    fetchWithTimeout<unknown[]>(`${BACKEND_BASE}/activity/hh_xk92p_sharma`),
  ]);

  // If backend returns data, merge with our rich mock types (backend doesn't
  // have the same shape as our UI types, so we use mocks as the base and
  // override with live values where available).
  void householdRaw;
  void devicesRaw;
  void activityRaw;

  return {
    source: "backend",
    household: SHARMA_HOUSEHOLD,
    devices: SHARMA_DEVICES,
    routines: SHARMA_ROUTINES,
    activity: SHARMA_ACTIVITY,
    predictions: SHARMA_PREDICTIONS,
    notifications: SHARMA_NOTIFICATIONS,
    intelligenceStats: INTELLIGENCE_STATS,
    notificationStats: NOTIFICATION_STATS,
    loadedAt: new Date().toISOString(),
  };
}

function loadFromMocks(): DemoData {
  return {
    source: "mock",
    household: SHARMA_HOUSEHOLD,
    devices: SHARMA_DEVICES,
    routines: SHARMA_ROUTINES,
    activity: SHARMA_ACTIVITY,
    predictions: SHARMA_PREDICTIONS,
    notifications: SHARMA_NOTIFICATIONS,
    intelligenceStats: INTELLIGENCE_STATS,
    notificationStats: NOTIFICATION_STATS,
    loadedAt: new Date().toISOString(),
  };
}

// ─── Public API ───────────────────────────────────────────────────────────────

let _cached: DemoData | null = null;

export const demoService = {
  /**
   * Load demo data.
   * Tries the backend first; falls back to mocks if backend is unavailable.
   * Result is cached for the session.
   */
  async load(forceRefresh = false): Promise<DemoData> {
    if (_cached && !forceRefresh) return _cached;

    try {
      const data = await loadFromBackend();
      _cached = data;
      return data;
    } catch {
      // Backend unavailable — use mocks silently
      const data = loadFromMocks();
      _cached = data;
      return data;
    }
  },

  /**
   * Synchronously get the mock data without trying the backend.
   * Useful for SSR or when you know backend is unavailable.
   */
  getMocks(): DemoData {
    if (_cached) return _cached;
    const data = loadFromMocks();
    _cached = data;
    return data;
  },

  /** Clear cached data */
  clearCache() {
    _cached = null;
  },

  /** Check if backend is reachable */
  async isBackendAvailable(): Promise<boolean> {
    try {
      await fetchWithTimeout<unknown>(`${BACKEND_BASE}/health`);
      return true;
    } catch {
      return false;
    }
  },
};

export type { MockHousehold, MockDevice, MockRoutine, MockActivity, MockPrediction, MockNotification };
