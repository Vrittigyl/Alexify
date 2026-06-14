/**
 * event.service.ts
 * Endpoints:
 *   POST /events/ingest              — raw event through full pipeline
 *   POST /simulate/event/{name}      — named demo event (6 available)
 *   POST /simulate/demo              — full 10-event demo playback
 *   GET  /rte/decision/{event_id}    — RTE audit log lookup
 *   GET  /metrics                    — dashboard metrics snapshot
 *   GET  /metrics/circuit-breaker    — Bedrock circuit breaker state
 */

import {
  BACKEND_BASE,
  DEFAULT_HOUSEHOLD_ID,
  NAMED_EVENTS,
  probe,
  fetchWithTimeout,
  type ProbeResult,
  type NamedEvent,
} from "./api.config";

// ─── Response shapes ──────────────────────────────────────────────────────────

export interface IngestRequest {
  household_id?: string;
  device_type?: string;
  device_id?: string;
  event_type?: string;
  payload?: Record<string, unknown>;
  impact_level?: string;
}

export interface PipelineResult {
  event_id: string;
  route: "RULE_ENGINE" | "BEDROCK" | "SUPPRESS";
  stage: number;
  complexity_score: number;
  actions_proposed: number;
  actions_approved: number;
  dispatched: unknown[];
  actions_count: number;
  total_latency_ms: number;
}

export interface MetricsResponse {
  [key: string]: unknown;
}

export interface CircuitBreakerResponse {
  state: string;
  failures: number;
  [key: string]: unknown;
}

export interface RTEDecisionResponse {
  event_id: string;
  route: string;
  stage_decided: number;
  complexity_score: number;
  rule_matched?: string;
  pattern_matched?: string;
  [key: string]: unknown;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const eventService = {
  /**
   * POST /events/ingest
   * Send a raw event through the full SAATHI pipeline.
   * Returns route decision + actions dispatched.
   */
  async ingestEvent(req: IngestRequest): Promise<ProbeResult<PipelineResult>> {
    const url = `${BACKEND_BASE}/events/ingest`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<PipelineResult>(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ household_id: DEFAULT_HOUSEHOLD_ID, ...req }),
      });
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[eventService.ingestEvent]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[eventService.ingestEvent]", result);
      return result;
    }
  },

  /**
   * POST /simulate/event/{event_name}
   * Fire one of the 6 named demo events through the pipeline.
   * Valid names: water_tank_full | board_exam | guest_arrival |
   *              pressure_cooker_5_whistles | dadaji_medicine | fridge_door_open
   */
  async simulateNamedEvent(name: NamedEvent): Promise<ProbeResult<PipelineResult>> {
    const url = `${BACKEND_BASE}/simulate/event/${name}`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<PipelineResult>(url, { method: "POST" });
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log(`[eventService.simulateNamedEvent:${name}]`, result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log(`[eventService.simulateNamedEvent:${name}]`, result);
      return result;
    }
  },

  /**
   * POST /simulate/demo
   * Play back all 10 demo_script.json events at 10× speed.
   */
  async runFullDemo(): Promise<ProbeResult<{ status: string; events_processed: number; results: unknown[] }>> {
    const url = `${BACKEND_BASE}/simulate/demo`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<{ status: string; events_processed: number; results: unknown[] }>(
        url,
        { method: "POST" },
        30_000, // demo can take up to 30s
      );
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[eventService.runFullDemo]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[eventService.runFullDemo]", result);
      return result;
    }
  },

  /**
   * GET /metrics
   * Full dashboard metrics snapshot (patterns, routes, actions, etc.).
   */
  async getMetrics(): Promise<ProbeResult<MetricsResponse>> {
    const url = `${BACKEND_BASE}/metrics`;
    const result = await probe<MetricsResponse>(url);
    console.log("[eventService.getMetrics]", result);
    return result;
  },

  /**
   * GET /metrics/circuit-breaker
   * Bedrock circuit breaker state (CLOSED / OPEN / HALF_OPEN).
   */
  async getCircuitBreaker(): Promise<ProbeResult<CircuitBreakerResponse>> {
    const url = `${BACKEND_BASE}/metrics/circuit-breaker`;
    const result = await probe<CircuitBreakerResponse>(url);
    console.log("[eventService.getCircuitBreaker]", result);
    return result;
  },

  /** Probe all non-destructive event endpoints at once */
  async probeAll() {
    const [metrics, circuitBreaker] = await Promise.all([
      eventService.getMetrics(),
      eventService.getCircuitBreaker(),
    ]);
    return { metrics, circuitBreaker };
  },

  /** All named events available for simulation */
  namedEvents: NAMED_EVENTS,
};
