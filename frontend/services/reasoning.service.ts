/**
 * reasoning.service.ts
 * Endpoints:
 *   GET /rte/decision/{event_id}  — RTE audit log entry for a specific event
 *   GET /metrics                  — includes route breakdown (RULE_ENGINE/BEDROCK/SUPPRESS)
 *
 * The RTE audit log is written to DynamoDB RTEAuditLog with 90-day TTL.
 * The /rte/decision endpoint is documented in the backend header comment
 * but the route handler lives inside main.py.
 *
 * NOTE: The backend does NOT currently have a dedicated GET /reasoning endpoint.
 * Reasoning data is embedded in pipeline results (/events/ingest response) and
 * in the RTE audit log. This service probes what's available and documents gaps.
 */

import { BACKEND_BASE, probe, type ProbeResult } from "./api.config";

export interface RTEDecision {
  event_id: string;
  household_id: string;
  event_type: string;
  route: "RULE_ENGINE" | "BEDROCK" | "SUPPRESS";
  stage_decided: number;
  complexity_score: number;
  rule_matched?: string;
  pattern_matched?: string;
  score_breakdown?: Record<string, number>;
  latency_ms?: number;
  timestamp?: string;
}

export interface RTEDecisionResult {
  decision?: RTEDecision;
  // The endpoint may return 404 if event_id is not found
  detail?: string;
}

export interface MetricsRouteBreakdown {
  total_events: number;
  rule_engine_count: number;
  bedrock_count: number;
  suppressed_count: number;
  avg_latency_ms?: number;
}

export const reasoningService = {
  /**
   * GET /rte/decision/{event_id}
   * Look up the RTE audit log for a specific event_id.
   * Returns 404 if the event is not found in the audit log.
   */
  async getDecision(eventId: string): Promise<ProbeResult<RTEDecisionResult>> {
    const url = `${BACKEND_BASE}/rte/decision/${eventId}`;
    const result = await probe<RTEDecisionResult>(url);
    console.log(`[reasoningService.getDecision:${eventId}]`, result);
    return result;
  },

  /**
   * GET /metrics
   * Returns route breakdown showing how many events went to each path today.
   * Useful as a proxy for reasoning activity when no dedicated /reasoning endpoint exists.
   */
  async getRouteBreakdown(): Promise<ProbeResult<Record<string, unknown>>> {
    const url = `${BACKEND_BASE}/metrics`;
    const result = await probe<Record<string, unknown>>(url);
    console.log("[reasoningService.getRouteBreakdown]", result);
    return result;
  },

  /**
   * Inventory: probe what reasoning endpoints are actually reachable.
   * Returns a map of endpoint → status so the debug page can show ✅ / ❌.
   */
  async probeEndpoints() {
    const results: Record<string, ProbeResult> = {};

    // The /rte/decision endpoint exists per the main.py docstring
    // but needs a real event_id. We probe with a sentinel to detect 404 vs 000 (no server).
    const rteProbe = await probe(`${BACKEND_BASE}/rte/decision/__probe__`);
    // 404 = endpoint exists but event not found (✅ endpoint reachable)
    // network error = backend down (❌)
    results["rte_decision"] = {
      ...rteProbe,
      status: rteProbe.status === "error" && rteProbe.error?.includes("404") ? "ok" : rteProbe.status,
    };

    results["metrics"] = await probe(`${BACKEND_BASE}/metrics`);

    console.log("[reasoningService.probeEndpoints]", results);
    return results;
  },
};
