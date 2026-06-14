/**
 * simulation.service.ts
 * Endpoints:
 *   POST /admin/seed                    — seed DynamoDB with Sharma family data
 *   POST /simulate/event/{name}         — fire a named event (6 available)
 *   POST /simulate/demo                 — full 10-event demo playback
 *
 * Named events available (from EventSimulator class):
 *   water_tank_full | board_exam | guest_arrival |
 *   pressure_cooker_5_whistles | dadaji_medicine | fridge_door_open
 */

import {
  BACKEND_BASE,
  NAMED_EVENTS,
  probe,
  fetchWithTimeout,
  type ProbeResult,
  type NamedEvent,
} from "./api.config";

export interface SeedResponse {
  status: string;
  summary: unknown;
}

export interface SimulationResult {
  event_name: string;
  event_id: string;
  route: "RULE_ENGINE" | "BEDROCK" | "SUPPRESS";
  actions_count: number;
  latency_ms: number;
}

export interface DemoPlaybackResponse {
  status: string;
  events_processed: number;
  results: SimulationResult[];
}

export const simulationService = {
  /**
   * POST /admin/seed
   * Seeds DynamoDB with the full Sharma family knowledge graph.
   * Protected endpoint — requires X-API-Key in production.
   */
  async seedDatabase(): Promise<ProbeResult<SeedResponse>> {
    const url = `${BACKEND_BASE}/admin/seed`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<SeedResponse>(url, { method: "POST" }, 15_000);
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[simulationService.seedDatabase]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[simulationService.seedDatabase]", result);
      return result;
    }
  },

  /**
   * POST /simulate/event/{name}
   * Fire a single named demo event through the full SAATHI pipeline.
   */
  async fireNamedEvent(name: NamedEvent): Promise<ProbeResult<unknown>> {
    const url = `${BACKEND_BASE}/simulate/event/${name}`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<unknown>(url, { method: "POST" });
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log(`[simulationService.fireNamedEvent:${name}]`, result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log(`[simulationService.fireNamedEvent:${name}]`, result);
      return result;
    }
  },

  /**
   * POST /simulate/demo
   * Play back all 10 demo_script.json events at 10× speed.
   * Long-running: timeout set to 45s.
   */
  async runFullDemo(): Promise<ProbeResult<DemoPlaybackResponse>> {
    const url = `${BACKEND_BASE}/simulate/demo`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<DemoPlaybackResponse>(url, { method: "POST" }, 45_000);
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[simulationService.runFullDemo]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[simulationService.runFullDemo]", result);
      return result;
    }
  },

  /**
   * Probe all simulation endpoints (read-only — no mutation).
   * Only tests that the endpoints are reachable, not that they execute.
   */
  async probeEndpoints() {
    // We can probe /health instead of triggering actual events
    const health = await probe(`${BACKEND_BASE}/health`);
    // Named events are POST-only — we can verify the route exists by
    // attempting with an invalid name and expecting a 404
    const invalidEvent = await probe(`${BACKEND_BASE}/simulate/event/__probe__`);
    const knownEndpoint = invalidEvent.status === "error" && invalidEvent.error?.includes("404")
      ? { ...invalidEvent, status: "ok" as const }
      : invalidEvent;

    const results = {
      health,
      simulate_named_event: knownEndpoint,
      named_events: NAMED_EVENTS,
    };
    console.log("[simulationService.probeEndpoints]", results);
    return results;
  },

  namedEvents: NAMED_EVENTS,
};
