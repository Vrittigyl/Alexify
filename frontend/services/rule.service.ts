/**
 * rule.service.ts
 * Endpoints: GET /rules   POST /rules/reload
 *
 * /rules returns all active rules in the registry:
 *   - SAFETY rules (always execute, no conflict resolution)
 *   - HEALTH rules
 *   - CUSTOM rules (per-household)
 *   - PROMOTED_PATTERN rules (promoted from patterns)
 *   - FLEET rules (apply to all households)
 */

import { BACKEND_BASE, probe, type ProbeResult, fetchWithTimeout } from "./api.config";

export interface RuleSummary {
  rule_id: string;
  rule_type: "safety" | "health" | "custom" | "promoted_pattern" | "fleet";
  active: boolean;
  priority: number | null;
}

export interface RulesResponse {
  count: number;
  rules: RuleSummary[];
}

export interface ReloadResponse {
  status: string;
  rules_loaded: number;
}

export const ruleService = {
  /**
   * GET /rules
   * List all active rules in the registry (household + FLEET).
   */
  async getRules(): Promise<ProbeResult<RulesResponse>> {
    const url = `${BACKEND_BASE}/rules`;
    const result = await probe<RulesResponse>(url);
    console.log("[ruleService.getRules]", result);
    return result;
  },

  /**
   * POST /rules/reload
   * Force-refresh the rule registry from DynamoDB.
   * Protected endpoint — requires X-API-Key in production.
   */
  async reloadRules(): Promise<ProbeResult<ReloadResponse>> {
    const url = `${BACKEND_BASE}/rules/reload`;
    const start = performance.now();
    try {
      const data = await fetchWithTimeout<ReloadResponse>(url, { method: "POST" });
      const result = { status: "ok" as const, url, data, latencyMs: Math.round(performance.now() - start) };
      console.log("[ruleService.reloadRules]", result);
      return result;
    } catch (err) {
      const result = {
        status: "error" as const,
        url,
        error: err instanceof Error ? err.message : String(err),
        latencyMs: Math.round(performance.now() - start),
      };
      console.log("[ruleService.reloadRules]", result);
      return result;
    }
  },

  /** Filter rules by type */
  async getByType(type: RuleSummary["rule_type"]) {
    const result = await ruleService.getRules();
    if (result.status !== "ok" || !result.data) return result;
    return {
      ...result,
      data: {
        ...result.data,
        rules: result.data.rules.filter((r) => r.rule_type === type),
        count: result.data.rules.filter((r) => r.rule_type === type).length,
      },
    };
  },
};
