/**
 * household.service.ts
 * Endpoints: /health  /graph/{hh}  /graph/{hh}/members  /graph/{hh}/devices
 * Pattern: try backend → log → return data or error shape
 */

import { BACKEND_BASE, DEFAULT_HOUSEHOLD_ID, probe, type ProbeResult } from "./api.config";

// ─── Response shapes (as returned by the backend) ────────────────────────────

export interface HealthResponse {
  status: string;
  household_id: string;
  version: string;
  bedrock_mock_mode: boolean;
  dynamo: string;
  redis: unknown;
  dev_mode: boolean;
  ws_connections: number;
}

export interface GraphResponse {
  household_id: string;
  graph_version: number;
  status: string;
  subgraph_nodes: number;
}

export interface MembersResponse {
  household_id: string;
  members: Array<{
    member_id: string;
    member_name: string;
    impact: string;
    constraints: string[];
    life_event: string;
  }>;
}

export interface DevicesResponse {
  household_id: string;
  device_context: Record<string, unknown>;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const householdService = {
  /**
   * GET /health
   * System health check — DynamoDB + Redis + WebSocket state.
   */
  async getHealth(): Promise<ProbeResult<HealthResponse>> {
    const url = `${BACKEND_BASE}/health`;
    const result = await probe<HealthResponse>(url);
    console.log("[householdService.getHealth]", result);
    return result;
  },

  /**
   * GET /graph/{household_id}
   * Full household knowledge graph (node + edge summary).
   */
  async getGraph(householdId = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult<GraphResponse>> {
    const url = `${BACKEND_BASE}/graph/${householdId}`;
    const result = await probe<GraphResponse>(url);
    console.log("[householdService.getGraph]", result);
    return result;
  },

  /**
   * GET /graph/{household_id}/members
   * Members affected by the Rohan board-exam life event.
   */
  async getMembers(householdId = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult<MembersResponse>> {
    const url = `${BACKEND_BASE}/graph/${householdId}/members`;
    const result = await probe<MembersResponse>(url);
    console.log("[householdService.getMembers]", result);
    return result;
  },

  /**
   * GET /graph/{household_id}/devices
   * Device impact context for the rooftop water motor.
   */
  async getDevices(householdId = DEFAULT_HOUSEHOLD_ID): Promise<ProbeResult<DevicesResponse>> {
    const url = `${BACKEND_BASE}/graph/${householdId}/devices`;
    const result = await probe<DevicesResponse>(url);
    console.log("[householdService.getDevices]", result);
    return result;
  },

  /**
   * Run all household probes at once.
   */
  async probeAll(householdId = DEFAULT_HOUSEHOLD_ID) {
    const [health, graph, members, devices] = await Promise.all([
      householdService.getHealth(),
      householdService.getGraph(householdId),
      householdService.getMembers(householdId),
      householdService.getDevices(householdId),
    ]);
    return { health, graph, members, devices };
  },
};
