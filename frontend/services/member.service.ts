/**
 * member.service.ts
 * Wraps /graph/{hh}/members — returns the members affected by life events
 * with their constraints and impact levels.
 *
 * Note: The backend currently exposes member data via the graph endpoint
 * (filtered to the board-exam life event). This service is the typed wrapper.
 */

import { BACKEND_BASE, DEFAULT_HOUSEHOLD_ID, probe, type ProbeResult } from "./api.config";

export interface AffectedMember {
  member_id: string;
  member_name: string;
  impact: "high" | "medium" | "low";
  constraints: string[];
  life_event: string;
}

export interface MemberListResult {
  household_id: string;
  members: AffectedMember[];
}

export const memberService = {
  /**
   * GET /graph/{household_id}/members
   * Returns members affected by active life events (currently board_exams).
   */
  async getMembers(householdId = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult<MemberListResult>> {
    const url = `${BACKEND_BASE}/graph/${householdId}/members`;
    const result = await probe<MemberListResult>(url);
    console.log("[memberService.getMembers]", result);
    return result;
  },

  /**
   * Convenience: resolve a member id to its index within the Sharma family.
   * Useful for building UI display without additional API calls.
   */
  async getMembersSummary(householdId = DEFAULT_HOUSEHOLD_ID) {
    const result = await memberService.getMembers(householdId);
    if (result.status !== "ok" || !result.data) return result;

    const summary = result.data.members.map((m) => ({
      id: m.member_id,
      name: m.member_name,
      impact: m.impact,
      constraintCount: m.constraints.length,
      lifeEvent: m.life_event,
    }));

    return { ...result, summary };
  },
};
