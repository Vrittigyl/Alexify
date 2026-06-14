/**
 * pattern.service.ts
 * Endpoints: GET /patterns   POST /patterns/promote
 *
 * /patterns returns all patterns with confidence bands:
 *   OBSERVING  → being tracked, confidence < 0.6
 *   LEARNING   → confident enough to suggest, 0.6–0.9
 *   PROMOTED   → became a rule (confidence >= 0.9, 30+ days)
 *   DEMOTED    → was promoted, then missed 3 times
 *   RETIRED    → permanently retired
 */

import { BACKEND_BASE, probe, type ProbeResult, fetchWithTimeout } from "./api.config";

export interface Pattern {
  household_id: string;
  pattern_id: string;
  description: string;
  confidence: number;
  confidence_band: "OBSERVING" | "LEARNING" | "PROMOTED" | "DEMOTED" | "RETIRED";
  observation_days: number;
  member_id?: string;
  device_type?: string;
  device_id?: string;
  event_type?: string;
  time_window?: string;
  day_pattern?: string[];
  total_observations?: number;
  total_matches?: number;
  first_observed?: string;
  last_observed?: string;
  consecutive_misses?: number;
  promoted_at?: string;
  promoted_rule_id?: string;
  demoted_at?: string;
  retired_at?: string;
}

export interface PatternsResponse {
  count: number;
  patterns: Pattern[];
}

export interface PromoteResponse {
  status: string;
  rule_id?: string;
  message?: string;
}

export const patternService = {
  /**
   * GET /patterns
   * Returns all patterns for the default household with their confidence bands.
   */
  async getPatterns(): Promise<ProbeResult<PatternsResponse>> {
    const url = `${BACKEND_BASE}/patterns`;
    const result = await probe<PatternsResponse>(url);
    console.log("[patternService.getPatterns]", result);
    return result;
  },

  /**
   * POST /patterns/promote
   * Promote a pattern to a rule (requires confidence >= 0.9, 30+ days).
   * Protected endpoint — requires X-API-Key in production.
   */
  async promotePattern(patternId: string): Promise<ProbeResult<PromoteResponse>> {
    const url = `${BACKEND_BASE}/patterns/promote`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<PromoteResponse>(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pattern_id: patternId }),
      });
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[patternService.promotePattern]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[patternService.promotePattern]", result);
      return result;
    }
  },

  /** Filter patterns by band */
  async getByBand(band: Pattern["confidence_band"]) {
    const result = await patternService.getPatterns();
    if (result.status !== "ok" || !result.data) return result;
    return {
      ...result,
      data: {
        ...result.data,
        patterns: result.data.patterns.filter((p) => p.confidence_band === band),
        count: result.data.patterns.filter((p) => p.confidence_band === band).length,
      },
    };
  },
};
