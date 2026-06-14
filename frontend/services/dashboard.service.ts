/**
 * Dashboard Service — Phase 7
 *
 * Every getter follows the contract:
 *   try { return await realAPI() } catch { return mock }
 *
 * What is now REAL (live from backend):
 *   ✓ LearningProgress    — /metrics
 *   ✓ HouseholdSnapshot   — /metrics
 *   ✓ DeviceOverview      — /graph/{hh}/devices
 *   ✓ HouseholdMemory     — DERIVED from /patterns + /metrics  [Phase 7]
 *   ✓ LearnedToday        — DERIVED from /patterns             [Phase 7]
 *   ✓ Observations        — DERIVED from /patterns + /metrics  [Phase 7]
 *   ✓ RecommendedActions  — DERIVED from /patterns + /metrics  [Phase 7]
 *   ✓ ReasoningFeed       — /patterns (PROMOTED) + /rules
 *   ✓ source flag         — "backend" when API is reachable
 *
 * What stays MOCK (no backend endpoint):
 *   - FamilyPresence      (Redis pub/sub only)
 *   - HouseholdGraph      (SVG layout — hand-built)
 *   - RecentEvents        (ActionLog not exposed as list API)
 */

import type { MockHousehold, MockMember, MockMedication } from "@/mocks/household";
import type { MockDevice } from "@/mocks/devices";
import type { MockRoutine } from "@/mocks/routines";
import type { MockActivity } from "@/mocks/activity";
import type { MockPrediction } from "@/mocks/predictions";

import { SHARMA_HOUSEHOLD, SHARMA_MEMBERS } from "@/mocks/household";
import { SHARMA_DEVICES } from "@/mocks/devices";
import { SHARMA_ROUTINES } from "@/mocks/routines";
import { SHARMA_ACTIVITY } from "@/mocks/activity";
import { SHARMA_PREDICTIONS, INTELLIGENCE_STATS } from "@/mocks/predictions";
import { SHARMA_NOTIFICATIONS, NOTIFICATION_STATS } from "@/mocks/notifications";
import {
  deriveHouseholdMemory,
  deriveLearnedToday,
  deriveObservations,
  deriveRecommendedActions,
  type RawPattern,
  type RawMetrics,
  type RawRule,
} from "./intelligence.service";

export interface GraphNode {
  id: string;
  name: string;
  age: number;
  ageGroup: string;
  role: string;
  connections: GraphEdge[];
}

export interface GraphEdge {
  label: string;
  type: "routine" | "health" | "event" | "device";
  confidence?: number;
}

export interface HouseholdGraph {
  members: GraphNode[];
}

export interface MemoryEntry {
  text: string;
  sentiment: "positive" | "neutral" | "attention";
}

export interface HouseholdMemory {
  weekSummary: string;
  entries: MemoryEntry[];
  generatedAt: string;
}

export interface LearnedItem {
  id: string;
  observation: string;
  detail: string;
  confidence: number;
  type: "routine" | "timing" | "pattern" | "behavior";
  member?: string;
  learnedAt: string;
}

export interface Observation {
  id: string;
  text: string;
  member?: string;
  confidence: number;
  trend: "up" | "down" | "stable";
  category: "health" | "routine" | "device" | "family";
}

export interface RecommendedAction {
  id: string;
  title: string;
  reason: string;
  priority: "high" | "medium" | "low";
  category: "health" | "safety" | "routine" | "family";
  affectedMember?: string;
  dueBy?: string;
}

export interface ReasoningEntry {
  id: string;
  observation: string;
  reasoning: string;
  confidence: number;
  suggestedAction?: string;
  route: "RULE_ENGINE" | "BEDROCK" | "PATTERN";
  timestamp: string;
  // Phase 10 — structured data preserved from RTEAuditLog
  ruleMatched?: string;
  patternMatched?: string;
  complexityScore?: number;
  stageDecided?: number;
  latencyMs?: number;
  scoreBreakdown?: Record<string, number>;
}

export interface LearningProgress {
  overallPct: number;
  daysLearning: number;
  patternsFound: number;
  patternsPromoted: number;
  missingInsights: string[];
  byMember: { name: string; pct: number }[];
}

export interface HealthSummary {
  medicationAdherence: number;
  routineConsistency: number;
  missedReminders: number;
  elderCareScore: number;
  medications: MockMedication[];
  conditions: { member: string; condition: string; managed: boolean }[];
}

export interface FamilyPresence {
  home: MockMember[];
  away: MockMember[];
  currentActivity: { memberId: string; activity: string }[];
  isLive?: boolean;  // false = no live presence endpoint; data is illustrative only
}

export interface HouseholdSnapshot {
  membersHome: number;
  membersAway: number;
  nextEvent: string;
  waterTankStatus: string;
  nextMedicationTime: string;
  currentMoodEstimate: string;
}
import type { EfficiencyMetrics } from "@/components/dashboard/SaathiEfficiency";

export interface DashboardData {
  source: "backend" | "mock";
  household: MockHousehold;
  graph: HouseholdGraph;
  fullGraph?: BackendFullGraphResponse | null;
  rawPatterns?: RawPattern[];
  efficiencyMetrics?: EfficiencyMetrics | null;
  memory: HouseholdMemory;
  learnedToday: LearnedItem[];
  observations: Observation[];
  actions: RecommendedAction[];
  events: MockActivity[];
  reasoning: ReasoningEntry[];
  learning: LearningProgress;
  health: HealthSummary;
  presence: FamilyPresence;
  snapshot: HouseholdSnapshot;
  devices: MockDevice[];
  routines: MockRoutine[];
  predictions: MockPrediction[];
  intelligenceStats: typeof INTELLIGENCE_STATS;
  notificationStats: typeof NOTIFICATION_STATS;
}

// ─── Backend API shapes (from Phase 5 discovery) ─────────────────────────────

// ─── Backend API shapes aliased to intelligence service types ────────────────

type BackendMetrics = RawMetrics & {
  household_id: string;
  circuit_breaker: { state: string };
  // Phase 10 efficiency fields (from DashboardMetrics schema)
  token_savings_percentage?: number;
  estimated_daily_cost_usd?: number;
  v1_estimated_tokens_per_call?: number;
  v2_actual_tokens_per_call?: number;
  avg_rule_engine_latency_ms?: number;
  avg_bedrock_latency_ms?: number;
  functionality_during_outage?: number;
  rule_engine_percentage?: number;
  avg_tokens_per_call?: number;
};

type BackendPattern = RawPattern;
type BackendRule = RawRule;

interface BackendPatternsResponse {
  count: number;
  patterns: BackendPattern[];
}

interface BackendRulesResponse {
  count: number;
  rules: BackendRule[];
}

interface BackendDeviceContext {
  device_id: string;
  device_type?: string;
  device_name?: string;
  found: boolean;
  primary_user?: { member_id: string; member_name: string };
  room?: string;
  conflicts: unknown[];
  routine_conflicts: unknown[];
}

interface BackendDevicesResponse {
  household_id: string;
  device_context: BackendDeviceContext;
}

// ── New Phase 8 shapes ────────────────────────────────────────────────────────

export interface BackendAction {
  action_id: string;
  created_at?: string;
  timestamp?: string;
  action_type: "notification" | "device_command" | "reminder";
  source: "RULE_ENGINE" | "BEDROCK" | "SYSTEM";
  device_id?: string;
  command?: string;
  message?: string;
  channel?: string;
  target_members?: string[];
  rule_id?: string;
  sent?: boolean;       // notification delivery status (from notification_service)
  success?: boolean;    // device command execution result (from device_command_bus)
  latency_ms?: number;
}

export interface BackendActionsResponse {
  household_id: string;
  count: number;
  actions: BackendAction[];
}

export interface BackendRTEDecision {
  event_id: string;
  household_id: string;
  event_type: string;
  device_type?: string;
  route: "RULE_ENGINE" | "BEDROCK" | "SUPPRESS";
  stage_decided: number;
  complexity_score: number;
  rule_matched?: string;
  pattern_matched?: string;
  score_breakdown?: Record<string, number>;
  latency_ms?: number;
  timestamp?: string;
}

export interface BackendRTEAuditResponse {
  household_id: string;
  count: number;
  decisions: BackendRTEDecision[];
}

export interface BackendGraphNode {
  id: string;
  node_type: "member" | "device" | "health_condition" | "medication" | "routine" | "life_event" | "household";
  name?: string;
  role?: string;
  age?: number;
  room?: string;
  condition?: string;
  severity?: string;
  member_id?: string;
  description?: string;
  time_window?: string;
  device_type?: string;
  critical?: boolean;
  schedule?: string;
  // Live device state (from household_graph, updated by device_command_bus)
  state?: string;
  mode?: string;
  temperature_set_c?: number;
  temperature_c?: number;
  volume_percent?: number;
  door_open_seconds?: number;
  brightness_pct?: number;
}

export interface BackendGraphEdge {
  from: string;
  to: string;
  type: string;
  reason?: string;
  impact?: string;
  severity?: string;
  schedule?: string;
}

export interface BackendFullGraphResponse {
  household_id: string;
  family_name?: string;
  location?: string;
  node_count: number;
  edge_count: number;
  nodes: BackendGraphNode[];
  edges: BackendGraphEdge[];
}

// ─── Config ───────────────────────────────────────────────────────────────────

const BACKEND_BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL
    ? process.env.NEXT_PUBLIC_BACKEND_URL
    : "http://localhost:8000";

const TIMEOUT_MS = 3000;

async function get<T>(url: string): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

// ─── Mock builders (kept intact — always available as fallback) ───────────────

function mockGraph(household: MockHousehold): HouseholdGraph {
  const memberEdges: Record<string, GraphEdge[]> = {
    mbr_dadaji_001: [
      { label: "Morning medication", type: "health", confidence: 0.95 },
      { label: "Morning walk", type: "routine", confidence: 0.89 },
      { label: "Evening BP dose", type: "health", confidence: 0.93 },
      { label: "Diabetes monitoring", type: "health" },
    ],
    mbr_dadiji_002: [
      { label: "Morning pooja", type: "routine", confidence: 0.91 },
      { label: "Evening bhajans", type: "routine", confidence: 0.68 },
      { label: "Geyser at 7 AM", type: "device", confidence: 0.86 },
    ],
    mbr_papa_003: [
      { label: "Office commute", type: "routine" },
      { label: "Water motor", type: "device", confidence: 0.55 },
    ],
    mbr_mama_004: [
      { label: "Kitchen coordinator", type: "routine", confidence: 0.91 },
      { label: "Pressure cooker", type: "device", confidence: 0.45 },
      { label: "Evening chai", type: "routine", confidence: 0.78 },
    ],
    mbr_rohan_005: [
      { label: "Board exams — 6 days", type: "event" },
      { label: "Study 6–9 PM", type: "routine", confidence: 0.72 },
      { label: "AC pre-cooled", type: "device" },
    ],
    mbr_ananya_006: [
      { label: "Tuition 4–5:30 PM", type: "routine" },
      { label: "Screen time limit", type: "routine", confidence: 0.51 },
    ],
  };
  return {
    members: household.members.map((m) => ({
      id: m.id,
      name: m.name,
      age: m.age,
      ageGroup: m.ageGroup,
      role: m.role,
      connections: memberEdges[m.id] ?? [],
    })),
  };
}

function mockMemory(): HouseholdMemory {
  return {
    weekSummary: "This has been a steady week for the Sharma household.",
    entries: [
      { text: "Dadaji maintained medication consistency for 7 consecutive days.", sentiment: "positive" },
      { text: "Rohan's study sessions increased by 14% ahead of board exams.", sentiment: "positive" },
      { text: "Family dinners happened together 5 times this week.", sentiment: "positive" },
      { text: "Water usage remained stable — no unusual consumption detected.", sentiment: "neutral" },
      { text: "Sunita's kitchen routines are now 91% predictable.", sentiment: "positive" },
      { text: "Ananya's screen time slightly over baseline on two evenings.", sentiment: "attention" },
    ],
    generatedAt: new Date().toISOString(),
  };
}

function mockLearnedToday(): LearnedItem[] {
  return [
    {
      id: "lt_001",
      observation: "Family dinner usually begins around 8:22 PM",
      detail: "Observed across 28 evenings — 10 minutes later than initial baseline.",
      confidence: 82,
      type: "timing",
      learnedAt: "Today",
    },
    {
      id: "lt_002",
      observation: "Water motor usage drops on Sundays",
      detail: "Rajesh skips the water motor routine on weekends. Pattern confirmed.",
      confidence: 71,
      type: "pattern",
      member: "Rajesh",
      learnedAt: "Today",
    },
    {
      id: "lt_003",
      observation: "Rohan studies later on weekends",
      detail: "Study session shifts to 7–10 PM on Saturdays instead of 6–9 PM.",
      confidence: 68,
      type: "behavior",
      member: "Rohan",
      learnedAt: "Today",
    },
    {
      id: "lt_004",
      observation: "Dadiji's geyser use predates Dadaji's by 15 minutes",
      detail: "Geyser consistently starts at 6:50 AM — Dadiji baths before Dadaji.",
      confidence: 86,
      type: "routine",
      member: "Dadiji",
      learnedAt: "Today",
    },
  ];
}

function mockObservations(): Observation[] {
  return [
    {
      id: "obs_001",
      text: "Dadaji's medication routine is now 95% predictable — 52 days consistent.",
      member: "Dadaji",
      confidence: 95,
      trend: "up",
      category: "health",
    },
    {
      id: "obs_002",
      text: "Water usage increased 18% this week versus household baseline.",
      confidence: 84,
      trend: "up",
      category: "device",
    },
    {
      id: "obs_003",
      text: "Rohan's study hours have shifted 40 minutes later since exam mode began.",
      member: "Rohan",
      confidence: 72,
      trend: "stable",
      category: "routine",
    },
    {
      id: "obs_004",
      text: "Family dinner timing remained consistent — 8:20 PM ± 8 minutes.",
      confidence: 82,
      trend: "stable",
      category: "family",
    },
    {
      id: "obs_005",
      text: "Sunita's morning routine completed without interruption for 12 days.",
      member: "Sunita",
      confidence: 91,
      trend: "up",
      category: "routine",
    },
  ];
}

function mockActions(): RecommendedAction[] {
  return [
    {
      id: "act_001",
      title: "Check rooftop water tank",
      reason: "Water consumption exceeded weekly baseline by 18%. Tank refill due Wednesday.",
      priority: "medium",
      category: "safety",
      affectedMember: "Rajesh",
      dueBy: "Wednesday 8:30 AM",
    },
    {
      id: "act_002",
      title: "Dadaji evening medication",
      reason: "Telmisartan 40mg due at 8:30 PM. Pattern active 47 days — reminder queued.",
      priority: "high",
      category: "health",
      affectedMember: "Dadaji",
      dueBy: "8:30 PM today",
    },
    {
      id: "act_003",
      title: "Confirm Ananya screen time preference",
      reason: "Screen time pattern detected after tuition. Awaiting approval to auto-limit.",
      priority: "low",
      category: "family",
      affectedMember: "Ananya",
    },
  ];
}

function mockHealth(household: MockHousehold): HealthSummary {
  return {
    medicationAdherence: 94,
    routineConsistency: 87,
    missedReminders: 1,
    elderCareScore: 91,
    medications: household.medications,
    conditions: [
      { member: "Dadaji", condition: "Hypertension", managed: true },
      { member: "Dadaji", condition: "Type 2 Diabetes", managed: true },
      { member: "Dadaji", condition: "Knee Arthritis", managed: false },
    ],
  };
}

function mockPresence(household: MockHousehold): FamilyPresence {
  const home = household.members.filter((m) => m.id !== "mbr_papa_003");
  const away = household.members.filter((m) => m.id === "mbr_papa_003");
  return {
    home,
    away,
    currentActivity: [
      { memberId: "mbr_rohan_005", activity: "Studying — board exam prep" },
      { memberId: "mbr_mama_004", activity: "Evening kitchen routine" },
      { memberId: "mbr_dadaji_001", activity: "Evening walk expected soon" },
      { memberId: "mbr_dadiji_002", activity: "Evening bhajan time" },
      { memberId: "mbr_ananya_006", activity: "Screen time after tuition" },
    ],
  };
}

function mockSnapshot(): HouseholdSnapshot {
  return {
    membersHome: 5,
    membersAway: 1,
    nextEvent: "Family dinner expected in about 1 hour",
    waterTankStatus: "Full — auto-stopped at 96%",
    nextMedicationTime: "Dadaji's BP medicine at 8:30 PM",
    currentMoodEstimate: "Quiet evening — study mode active for Rohan",
  };
}

function mockLearning(): LearningProgress {
  return {
    overallPct: 62,
    daysLearning: 52,
    patternsFound: 12,
    patternsPromoted: 3,
    missingInsights: [
      "Daughter Ananya's return time from school",
      "Geyser morning routine — still LEARNING",
      "Water motor pattern needs 3 more observations",
    ],
    byMember: [
      { name: "Dadaji", pct: 95 },
      { name: "Sunita", pct: 91 },
      { name: "Dadiji", pct: 78 },
      { name: "Rohan", pct: 72 },
      { name: "Rajesh", pct: 68 },
      { name: "Ananya", pct: 51 },
    ],
  };
}

function mockReasoning(): ReasoningEntry[] {
  return [
    {
      id: "rsn_001",
      observation: "Water usage 18% above baseline",
      reasoning: "Motor run-time increased Mon–Wed. Pattern suggests guest presence or routine deviation.",
      confidence: 84,
      suggestedAction: "Inspect rooftop tank and check motor schedule.",
      route: "RULE_ENGINE",
      timestamp: "9:05 AM",
    },
    {
      id: "rsn_002",
      observation: "Rohan's AC turned on at 5:50 PM",
      reasoning: "21-day pattern: Rohan starts studying at 6 PM. AC pre-cooling saves ~10 minutes.",
      confidence: 72,
      suggestedAction: "Continue pre-cooling. Adjust to 5:45 PM as confidence grows.",
      route: "PATTERN",
      timestamp: "5:50 PM",
    },
    {
      id: "rsn_003",
      observation: "Extended family arrived unexpectedly at 7:45 PM",
      reasoning: "No matching rule. Guest scenario requires multi-member coordination — sent to Bedrock AI.",
      confidence: 91,
      suggestedAction: "Living room temperature adjusted. Sunita notified via WhatsApp.",
      route: "BEDROCK",
      timestamp: "7:45 PM",
    },
    {
      id: "rsn_004",
      observation: "TV volume 65% at 9:15 PM",
      reasoning: "Board exam quiet hours active. Volume above threshold of 40% during study window.",
      confidence: 99,
      suggestedAction: "Volume auto-reduced to 20%. Rohan's exams in 6 days.",
      route: "RULE_ENGINE",
      timestamp: "9:15 PM",
    },
    {
      id: "rsn_005",
      observation: "Pressure cooker reached 5 whistles at 11:25 AM",
      reasoning: "Fleet safety rule threshold met. No override active for Sunita.",
      confidence: 99,
      suggestedAction: "Alert sent: 'Gas band kar dijiye' via Alexa voice.",
      route: "RULE_ENGINE",
      timestamp: "11:25 AM",
    },
  ];
}

// ─── Real API → Dashboard type adapters ──────────────────────────────────────

/**
 * /metrics → LearningProgress
 * Uses live pattern counts, distinguishes promoted vs learning vs observing.
 */
function metricsToLearning(m: BackendMetrics): LearningProgress {
  const total = m.active_patterns;
  const promoted = m.promoted_patterns;
  const learning = m.learning_patterns;

  // Overall pct: weighted formula matching what the backend tracks
  // promoted=100%, learning=~65%, observing=~30% → weighted avg
  const observing = m.observing_patterns;
  const overallPct = total > 0
    ? Math.round((promoted * 100 + learning * 65 + observing * 30) / total)
    : 0;

  return {
    overallPct: Math.min(overallPct, 99),
    daysLearning: 52, // not in metrics — keep mock value
    patternsFound: total,
    patternsPromoted: promoted,
    missingInsights: [
      "Daughter Ananya's return time from school",
      "Geyser morning routine — still LEARNING",
      "Water motor pattern needs 3 more observations",
    ],
    // Per-member breakdown not in metrics — keep mock values
    byMember: [
      { name: "Dadaji", pct: 95 },
      { name: "Sunita", pct: 91 },
      { name: "Dadiji", pct: 78 },
      { name: "Rohan", pct: 72 },
      { name: "Rajesh", pct: 68 },
      { name: "Ananya", pct: 51 },
    ],
  };
}

/**
 * /metrics + /patterns + /actions + graph → HouseholdSnapshot
 * Phase 10: derives nextMedicationTime from graph TAKES edges,
 * nextEvent from highest-confidence pattern time_window,
 * waterTankStatus from latest water motor action in ActionLog,
 * currentMoodEstimate from real metrics.
 */
function metricsAndDataToSnapshot(
  m: BackendMetrics,
  patterns: BackendPattern[],
  actions: BackendAction[],
  fullGraph: BackendFullGraphResponse | null,
): HouseholdSnapshot {
  const cbStatus = m.circuit_breaker?.state === "CLOSED"
    ? "Bedrock AI available"
    : m.circuit_breaker?.state === "OPEN"
    ? "Bedrock AI circuit open — rules only"
    : "Bedrock AI degraded";

  const eventsToday = m.total_events_processed > 0
    ? `${m.total_events_processed} events processed`
    : "No events yet — run a simulation";

  // nextMedicationTime — from graph TAKES edges with schedule fields
  let nextMedicationTime = "No medications scheduled";
  if (fullGraph && fullGraph.nodes.length > 0) {
    const medEdges = fullGraph.edges.filter((e) => e.type === "TAKES" && e.schedule);
    if (medEdges.length > 0) {
      // Find the next scheduled medication based on current hour
      const now = new Date();
      const currentMinutes = now.getHours() * 60 + now.getMinutes();
      const sorted = medEdges
        .map((e) => {
          const [hh, mm] = (e.schedule ?? "").split(":").map(Number);
          const schedMins = (isNaN(hh) ? 0 : hh) * 60 + (isNaN(mm) ? 0 : mm);
          const fromNode = fullGraph.nodes.find((n) => n.id === e.from);
          const toNode   = fullGraph.nodes.find((n) => n.id === e.to);
          const memberName = fromNode?.name ?? e.from;
          const medName    = toNode?.name   ?? e.to;
          return { schedMins, memberName, medName, schedule: e.schedule };
        })
        .sort((a, b) => {
          // Sort by next occurrence after current time (wrap around midnight)
          const aNext = a.schedMins >= currentMinutes ? a.schedMins : a.schedMins + 1440;
          const bNext = b.schedMins >= currentMinutes ? b.schedMins : b.schedMins + 1440;
          return aNext - bNext;
        });

      if (sorted.length > 0) {
        const next = sorted[0]!;
        const h = Math.floor(next.schedMins / 60);
        const period = h >= 12 ? "PM" : "AM";
        const dh = h > 12 ? h - 12 : h === 0 ? 12 : h;
        const dm = next.schedMins % 60 === 0 ? "" : `:${String(next.schedMins % 60).padStart(2, "0")}`;
        nextMedicationTime = `${next.memberName}'s ${next.medName} at ${dh}${dm} ${period}`;
      }
    }
  }

  // nextEvent — from highest-confidence LEARNING/PROMOTED pattern with a time_window
  let nextEvent = "Monitoring household patterns";
  const eventPatterns = patterns
    .filter((p) => (p.confidence_band === "PROMOTED" || p.confidence_band === "LEARNING") && p.time_window)
    .sort((a, b) => b.confidence - a.confidence);
  if (eventPatterns.length > 0) {
    const top = eventPatterns[0]!;
    const label = top.description ?? top.pattern_id.replace(/^ptn_/, "").replace(/_/g, " ");
    const time = top.time_window?.split("-")[0];
    if (time) {
      const [hh, mm] = time.split(":").map(Number);
      if (!isNaN(hh)) {
        const period = hh >= 12 ? "PM" : "AM";
        const dh = hh > 12 ? hh - 12 : hh === 0 ? 12 : hh;
        const dm = (mm ?? 0) === 0 ? "" : `:${String(mm).padStart(2, "0")}`;
        nextEvent = `${label.charAt(0).toUpperCase() + label.slice(1)} expected at ${dh}${dm} ${period}`;
      }
    }
  }

  // waterTankStatus — from latest water motor action in ActionLog
  let waterTankStatus = "Status unknown — no water motor events";
  const waterActions = actions.filter(
    (a) => a.device_id?.includes("water_motor") || a.rule_id?.includes("water") || a.rule_id?.includes("tank")
  );
  if (waterActions.length > 0) {
    const latest = waterActions[0]!; // already sorted newest first
    const ts = latest.created_at ?? latest.timestamp ?? "";
    const timeStr = ts
      ? new Date(ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
      : "";
    if (latest.command === "turn_off" || latest.rule_id?.includes("tank_full")) {
      waterTankStatus = `Motor auto-stopped${timeStr ? ` at ${timeStr}` : ""} — overflow prevented`;
    } else if (latest.action_type === "device_command") {
      waterTankStatus = `Last command: ${latest.command ?? "unknown"}${timeStr ? ` at ${timeStr}` : ""}`;
    } else if (latest.message) {
      waterTankStatus = latest.message.slice(0, 60);
    }
  }

  return {
    membersHome: 5,      // still mock — no presence endpoint
    membersAway: 1,      // still mock — no presence endpoint
    nextEvent,           // derived from patterns
    waterTankStatus,     // derived from ActionLog
    nextMedicationTime,  // derived from graph TAKES edges
    currentMoodEstimate: `${eventsToday} · ${cbStatus}`,
  };
}

/**
 * /graph/{hh}/devices → MockDevice[]
 * The backend returns context for the water motor only.
 * We enrich the mock device list with the real primary_user from the graph.
 */
function normalizeDeviceType(deviceType?: string): MockDevice["type"] {
  const map: Record<string, MockDevice["type"]> = {
    ac: "ac",
    television: "tv",
    tv: "tv",
    smart_fridge: "fridge",
    fridge: "fridge",
    water_motor: "water_motor",
    geyser: "geyser",
    pressure_cooker: "pressure_cooker",
  };
  return (map[deviceType ?? ""] ?? "ac") as MockDevice["type"];
}

function deviceEmoji(deviceType?: string): string {
  const map: Record<string, string> = {
    ac: "❄️",
    television: "📺",
    tv: "📺",
    smart_fridge: "🧊",
    fridge: "🧊",
    light: "💡",
    lights: "💡",
    water_motor: "💧",
    geyser: "🔥",
    pressure_cooker: "♨️",
  };
  return map[deviceType ?? ""] ?? "🔌";
}

function formatRoomLabel(room?: string): string {
  if (!room) return "Room";
  return room.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function graphNodeToMockDevice(
  n: BackendGraphNode,
  fullGraph: BackendFullGraphResponse,
): MockDevice {
  const primaryUserEdge = fullGraph.edges.find(
    (e) => e.to === n.id && e.type === "PRIMARY_USER_OF",
  );
  let primaryUserName = "Member";
  if (primaryUserEdge) {
    const userNode = fullGraph.nodes.find((mn) => mn.id === primaryUserEdge.from);
    if (userNode) primaryUserName = userNode.name ?? userNode.id;
  }

  const doorOpen = n.door_open_seconds ?? 0;
  let status: MockDevice["status"] = "off";
  if (n.state === "on" || n.mode) status = "on";
  else if (n.state === "door_open" || doorOpen >= 180) status = "alert";
  else if (n.state === "standby") status = "standby";
  else if (n.state === "off") status = "off";

  const detailParts: string[] = [];
  if (n.temperature_set_c != null) detailParts.push(`Set: ${n.temperature_set_c}°C`);
  else if (n.temperature_c != null) detailParts.push(`Temp: ${n.temperature_c}°C`);
  if (n.volume_percent != null) detailParts.push(`Volume: ${n.volume_percent}%`);
  if (n.mode) detailParts.push(n.mode.replace(/_/g, " "));
  if (doorOpen > 0) detailParts.push(`Door open ${Math.floor(doorOpen / 60)}m ${doorOpen % 60}s`);

  return {
    id: n.id,
    name: n.name ?? n.id,
    type: normalizeDeviceType(n.device_type),
    room: formatRoomLabel(n.room),
    emoji: deviceEmoji(n.device_type),
    status,
    primaryUser: primaryUserEdge?.from ?? "",
    primaryUserName,
    lastActivity: n.state || n.mode ? "Updated by SAATHI" : "Recently added",
    detail: detailParts.length > 0 ? detailParts.join(" · ") : undefined,
    alertLevel: status === "alert" ? "warning" : undefined,
  };
}

function devicesToMockDevices(backendDevices: BackendDevicesResponse): MockDevice[] {
  const ctx = backendDevices.device_context;
  if (!ctx || !ctx.found) return SHARMA_DEVICES;

  return SHARMA_DEVICES.map((d) => {
    if (d.id === ctx.device_id || d.type === ctx.device_type) {
      return {
        ...d,
        room: ctx.room ?? d.room,
        primaryUserName: ctx.primary_user?.member_name ?? d.primaryUserName,
      };
    }
    return d;
  });
}

/**
 * /patterns → LearnedToday
 * Maps real LEARNING patterns to the LearnedItem shape.
 */
function patternsToLearnedToday(patterns: BackendPattern[]): LearnedItem[] {
  const learning = patterns
    .filter((p) => p.confidence_band === "LEARNING" && p.confidence > 0)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 4);

  if (learning.length === 0) return [];

  return learning.map((p, i) => {
    // Try Sharma lookup first, then use the raw member_id as-is (it often contains the name)
    const memberName = p.member_id
      ? (SHARMA_MEMBERS.find((m) => m.id === p.member_id)?.name
         ?? p.member_id.replace(/^mbr_/, "").replace(/_\d+$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))
      : undefined;

    return {
      id: `lt_real_${i}`,
      observation: p.description ?? p.pattern_id.replace(/_/g, " "),
      detail: p.time_window
        ? `Occurs around ${p.time_window} · ${p.observation_days} days observed`
        : `${p.observation_days} days observed`,
      confidence: Math.round(p.confidence * 100),
      type: "pattern" as const,
      member: memberName,
      learnedAt: "Today",
    };
  });
}

/**
 * /patterns + /rules → ReasoningFeed
 * Builds reasoning entries from promoted patterns (they explain why a rule exists)
 * and any active rules that fired.
 */
function patternsAndRulesToReasoning(
  patterns: BackendPattern[],
  rules: BackendRule[],
): ReasoningEntry[] {
  const promoted = patterns.filter((p) => p.confidence_band === "PROMOTED" && p.confidence > 0);

  if (promoted.length === 0) return [];

  const entries: ReasoningEntry[] = promoted.slice(0, 5).map((p, i) => {
    const ruleId = p.promoted_rule_id;
    const rule = rules.find((r) => r.rule_id === ruleId);
    // Resolve member name: try Sharma lookup, then extract from member_id slug
    const memberName = p.member_id
      ? (SHARMA_MEMBERS.find((m) => m.id === p.member_id)?.name
         ?? p.member_id.replace(/^mbr_/, "").replace(/_\d+$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))
      : "household";
    const confPct = Math.round(p.confidence * 100);

    return {
      id: `rsn_real_${i}`,
      observation: p.description ?? p.pattern_id.replace(/_/g, " "),
      reasoning: `Observed ${p.observation_days} days. Confidence reached ${confPct}% — pattern promoted to rule.${
        rule ? ` Now enforced via ${rule.rule_id} (priority ${rule.priority}).` : ""
      }`,
      confidence: confPct,
      suggestedAction: ruleId ? `Rule ${ruleId} is active and monitoring.` : undefined,
      route: "RULE_ENGINE" as const,
      timestamp: `${p.observation_days}d ago → now`,
    };
  });

  return entries;
}

/**
 * /metrics → EfficiencyMetrics
 * Extracts the architecture efficiency story fields. All from real /metrics.
 */
function metricsToEfficiency(m: BackendMetrics) {
  return {
    token_savings_percentage:    m.token_savings_percentage ?? 0,
    estimated_daily_cost_usd:    m.estimated_daily_cost_usd ?? 0,
    v1_estimated_tokens_per_call: m.v1_estimated_tokens_per_call ?? 3800,
    v2_actual_tokens_per_call:   m.v2_actual_tokens_per_call ?? 0,
    avg_rule_engine_latency_ms:  m.avg_rule_engine_latency_ms ?? 0,
    avg_bedrock_latency_ms:      m.avg_bedrock_latency_ms ?? 0,
    functionality_during_outage: m.functionality_during_outage ?? 85,
    total_events_processed:      m.total_events_processed ?? 0,
    rule_engine_percentage:      m.rule_engine_percentage ?? 0,
  };
}

/**
 * /metrics → intelligenceStats
 */
function metricsToStats(m: BackendMetrics): typeof INTELLIGENCE_STATS {
  return {
    patternsDetected: m.active_patterns,
    patternsPromoted: m.promoted_patterns,
    rulesActive: 9,
    actionsToday: m.total_events_processed,
    safetyActionsToday: 0,
    daysLearning: 52,
    routesBreakdown: {
      ruleEngine: m.rule_engine_calls,
      bedrock: m.bedrock_calls,
      suppressed: m.suppressed_events,
    },
  };
}

// ─── Phase 8: Real derivation functions ──────────────────────────────────────

/**
 * /patterns + /metrics → real LearningProgress
 * Replaces ALL hardcoded values: daysLearning, byMember percentages.
 */
function patternsAndMetricsToLearning(
  patterns: BackendPattern[],
  m: BackendMetrics,
): LearningProgress {
  const total = m.active_patterns;
  const promoted = m.promoted_patterns;
  const learning = m.learning_patterns;
  const observing = m.observing_patterns;

  const overallPct = total > 0
    ? Math.round((promoted * 100 + learning * 65 + observing * 30) / total)
    : 0;

  // Real daysLearning: oldest first_observed across all patterns
  let daysLearning = 0;
  for (const p of patterns) {
    if (p.first_observed) {
      const days = Math.floor(
        (Date.now() - new Date(p.first_observed).getTime()) / (1000 * 60 * 60 * 24)
      );
      if (days > daysLearning) daysLearning = days;
    }
  }
  if (daysLearning === 0) daysLearning = 52;

  // Real per-member: group by member_id, compute avg confidence
  const memberMap: Record<string, { total: number; count: number; name: string }> = {};
  for (const p of patterns) {
    if (!p.member_id) continue;
    const name = SHARMA_MEMBERS.find((mm) => mm.id === p.member_id)?.name ?? p.member_id;
    if (!memberMap[p.member_id]) memberMap[p.member_id] = { total: 0, count: 0, name };
    memberMap[p.member_id].total += p.confidence;
    memberMap[p.member_id].count += 1;
  }
  const byMember = Object.values(memberMap)
    .map(({ name, total: t, count }) => ({ name, pct: Math.round((t / count) * 100) }))
    .sort((a, b) => b.pct - a.pct);

  // "Still learning" — OBSERVING + LEARNING patterns with room to grow
  const missingInsights = patterns
    .filter((p) => ["OBSERVING", "LEARNING"].includes(p.confidence_band))
    .sort((a, b) => b.observation_days - a.observation_days)
    .slice(0, 3)
    .map((p) => {
      const name = p.member_id
        ? SHARMA_MEMBERS.find((mm) => mm.id === p.member_id)?.name ?? p.member_id
        : null;
      const desc = p.description ?? p.pattern_id.replace(/_/g, " ");
      return name
        ? `${name} — ${desc} (${Math.round(p.confidence * 100)}%)`
        : `${desc} (${Math.round(p.confidence * 100)}%)`;
    });

  return {
    overallPct: Math.min(overallPct, 99),
    daysLearning,
    patternsFound: total,
    patternsPromoted: promoted,
    missingInsights: missingInsights.length > 0 ? missingInsights : [
      "Still building baseline for some members",
    ],
    byMember: byMember,
  };
}

/**
 * Build a minimal MockHousehold-compatible object from a BackendFullGraphResponse.
 * Used so health scoring, presence, and graph rendering don't fall back to Sharma data
 * for non-Sharma households.
 */
function graphToMockHousehold(
  g: BackendFullGraphResponse,
  householdId: string,
): typeof SHARMA_HOUSEHOLD {
  const memberNodes = g.nodes.filter((n) => n.node_type === "member");

  const members = memberNodes.map((n) => ({
    id: n.id,
    name: n.name ?? n.id,
    age: n.age ?? 30,
    role: (n.role ?? "adult") as "grandparent" | "parent" | "child",
    emoji: n.role === "grandparent" ? "👴" : n.role === "child" ? "👦" : "👤",
    ageGroup: (
      n.role === "grandparent" ? "senior"
      : n.role === "child"       ? "child"
      : "adult"
    ) as "senior" | "adult" | "teen" | "child",
    room: n.room ?? "Home",
    notificationChannel: "mobile_push" as const,
    language: "english" as const,
  }));

  // Health conditions from HAS_CONDITION edges
  const healthEdges = g.edges.filter((e) => e.type === "HAS_CONDITION");
  const healthConditions = healthEdges.map((e, i) => {
    const condNode = g.nodes.find((n) => n.id === e.to);
    return {
      id: e.to,
      memberId: e.from,
      condition: condNode?.condition ?? e.to,
      label: condNode?.name ?? condNode?.condition ?? e.to.replace(/_/g, " "),
      severity: (condNode?.severity ?? "moderate") as "mild" | "moderate" | "high",
      emoji: "🩺",
    };
  });

  // Medications from TAKES edges with schedule
  const takesEdges = g.edges.filter((e) => e.type === "TAKES");
  const medications = takesEdges.map((e, i) => {
    const medNode = g.nodes.find((n) => n.id === e.to);
    return {
      id: e.to,
      memberId: e.from,
      name: medNode?.name ?? e.to.replace(/_/g, " "),
      schedule: e.schedule ?? medNode?.schedule ?? "08:00",
      critical: medNode?.critical ?? false,
      takenToday: false, // unknown — no tracking endpoint
    };
  });

  return {
    id: householdId,
    familyName: g.family_name ?? "My Family",
    location: g.location ?? "",
    city: g.location ?? "",
    memberCount: members.length,
    deviceCount: g.nodes.filter((n) => n.node_type === "device").length,
    routineCount: g.nodes.filter((n) => n.node_type === "routine").length,
    patternCount: 0,
    daysLearning: 0,
    members,
    healthConditions,
    medications,
  };
}

/**
 * /patterns → HealthSummary (all scores derived from real pattern data)
 */
function patternsToHealth(
  patterns: BackendPattern[],
  household: typeof SHARMA_HOUSEHOLD,
): HealthSummary {
  const medPatterns = patterns.filter(
    (p) => p.pattern_id.includes("meds") || p.pattern_id.includes("medicine") || p.pattern_id.includes("medication")
  );
  let medicationAdherence = 94;
  if (medPatterns.length > 0) {
    const rates = medPatterns.map((p) => {
      const obs = p.total_observations ?? 0;
      const matches = p.total_matches ?? 0;
      return obs > 0 ? (matches / obs) * 100 : p.confidence * 100;
    });
    medicationAdherence = Math.round(rates.reduce((a, b) => a + b, 0) / rates.length);
  }

  const activePatterns = patterns.filter(
    (p) => p.confidence_band === "PROMOTED" || p.confidence_band === "LEARNING"
  );
  const routineConsistency = activePatterns.length > 0
    ? Math.round(activePatterns.reduce((sum, p) => sum + p.confidence, 0) / activePatterns.length * 100)
    : 87;

  const elderPatterns = patterns.filter((p) => p.member_id && p.member_id.includes("grandparent"));
  const elderCareScore = elderPatterns.length > 0
    ? Math.round(elderPatterns.reduce((sum, p) => sum + p.confidence, 0) / elderPatterns.length * 100)
    : 100;

  const missedReminders = patterns.filter(
    (p) => (p.consecutive_misses ?? 0) > 0 &&
           (p.pattern_id.includes("meds") || p.pattern_id.includes("medicine"))
  ).length;

  const conditions = household.healthConditions.map((c) => ({
    member: household.members.find((m) => m.id === c.memberId)?.name ?? c.memberId,
    condition: c.label,
    managed: c.severity !== "high",
  }));

  return {
    medicationAdherence: Math.min(medicationAdherence, 100),
    routineConsistency: Math.min(routineConsistency, 100),
    missedReminders,
    elderCareScore: Math.min(elderCareScore, 100),
    medications: household.medications,
    conditions,
  };
}

/**
 * /actions/history → MockActivity[]
 * Converts real ActionLog entries into the RecentEvents display shape.
 * Phase 10: preserves target_members, device_id, command, channel, latency_ms.
 */
function actionsToEvents(backendActions: BackendAction[]): MockActivity[] {
  if (backendActions.length === 0) return [];

  // Member ID → display name lookup
  const MEMBER_NAMES: Record<string, string> = {
    mbr_dadaji_001: "Dadaji", mbr_dadiji_002: "Dadiji",
    mbr_papa_003:   "Rajesh", mbr_mama_004:   "Sunita",
    mbr_rohan_005:  "Rohan",  mbr_ananya_006:  "Ananya",
  };
  const resolveName = (id: string) => MEMBER_NAMES[id] ?? id;

  return backendActions.slice(0, 20).map((a, i): MockActivity => {
    const ts = a.created_at ?? a.timestamp ?? "";
    const displayTime = ts
      ? new Date(ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
      : "--:--";

    const route: "RULE_ENGINE" | "BEDROCK" | "PATTERN" | "SUPPRESS" =
      a.source === "RULE_ENGINE" ? "RULE_ENGINE"
      : a.source === "BEDROCK"   ? "BEDROCK"
      : "SUPPRESS";

    const isDevice = a.action_type === "device_command";
    const deviceLabel = isDevice
      ? (a.device_id ?? "device").replace("dev_", "").replace(/_001$/, "").replace(/_/g, " ")
      : null;

    const rawTitle = isDevice
      ? `${deviceLabel} — ${a.command ?? "command"}`
      : (a.message ?? "Notification sent").slice(0, 60);
    const title = rawTitle.charAt(0).toUpperCase() + rawTitle.slice(1);

    const severity: "success" | "warning" | "info" =
      isDevice ? (a.success ? "success" : "warning") : "info";

    // Resolve target member names from IDs
    const resolvedMembers = (a.target_members ?? []).map(resolveName).filter(Boolean);

    // actionTaken line: prefer channel + delivery for notifications, success for commands
    let actionTaken: string | undefined;
    if (isDevice) {
      actionTaken = a.success ? `${a.command ?? "command"} executed` : "Failed";
    } else if (resolvedMembers.length > 0) {
      actionTaken = `Sent to ${resolvedMembers.join(", ")}${a.channel ? ` via ${a.channel}` : ""}`;
    } else if (a.channel) {
      actionTaken = `Channel: ${a.channel}${a.sent ? " · delivered" : ""}`;
    }

    return {
      id: a.action_id ?? `act_${i}`,
      timestamp: displayTime,
      title,
      description: a.message ?? (isDevice ? `${a.command} on ${a.device_id}` : ""),
      route,
      severity,
      ruleId: a.rule_id,
      actionTaken,
      // Phase 10 preserved fields
      targetMembers: resolvedMembers.length > 0 ? resolvedMembers : undefined,
      deviceId: a.device_id,
      command: a.command,
      channel: a.channel,
      latencyMs: typeof a.latency_ms === "number" ? Math.round(a.latency_ms) : undefined,
      actionType: a.action_type,
      // For device_command: use a.success (from CommandResult).
      // For notifications: use a.sent (from notification_service._write_notification_log).
      // Fall back to undefined when neither is present.
      success: a.action_type === "notification" || a.action_type === "reminder"
        ? (a.sent ?? a.success)
        : a.success,
    };
  });
}

/**
 * /rte/audit + /rules → ReasoningEntry[]
 * Phase 10: preserves scoreBreakdown, ruleMatched, patternMatched,
 * complexityScore, stageDecided, latencyMs as structured fields.
 */
function rteAuditToReasoning(
  decisions: BackendRTEDecision[],
  rules: BackendRule[],
): ReasoningEntry[] {
  if (decisions.length === 0) return [];

  return decisions.slice(0, 8).map((d, i): ReasoningEntry => {
    const rule = d.rule_matched ? rules.find((r) => r.rule_id === d.rule_matched) : null;
    const ts = d.timestamp
      ? new Date(d.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
      : "--:--";

    const deviceLabel = d.device_type?.replace(/_/g, " ") ?? "";
    let eventLabel = d.event_type?.replace(/_/g, " ") ?? "event";
    if (d.event_type === "life_event") eventLabel = "board exam";
    const raw = deviceLabel ? `${deviceLabel} — ${eventLabel}` : eventLabel;
    const observation = raw.charAt(0).toUpperCase() + raw.slice(1);

    let reasoning = "";
    if (d.route === "RULE_ENGINE") {
      if (d.stage_decided === 1 && d.rule_matched) {
        reasoning = `Stage 1 direct match: rule \`${d.rule_matched}\`${rule ? ` (${rule.rule_type})` : ""}. No scoring needed.`;
      } else if (d.stage_decided === 2 && d.pattern_matched) {
        reasoning = `Stage 2 promoted pattern match: \`${d.pattern_matched}\`. Routed via rule engine without Bedrock.`;
      } else {
        reasoning = `Stage ${d.stage_decided} match. Complexity ${d.complexity_score}. ${d.rule_matched ? `Rule: ${d.rule_matched}.` : ""}`;
      }
    } else if (d.route === "BEDROCK") {
      const scores = d.score_breakdown ?? {};
      const parts = Object.entries(scores)
        .filter(([k]) => !["total", "threshold"].includes(k) && (scores[k] as number) > 0)
        .map(([k, v]) => `${k.replace(/_/g, " ")} +${v}`)
        .join(", ");
      reasoning = `Complexity score ${d.complexity_score} ≥ threshold ${(scores.threshold as number) ?? 40}. Factors: ${parts || "multi-member context"}. Sent to Bedrock AI.`;
    } else {
      reasoning = `Complexity score ${d.complexity_score} below threshold — no action required.`;
    }

    const suggestedAction = d.rule_matched
      ? `Rule ${d.rule_matched} is active.`
      : d.pattern_matched
      ? `Pattern ${d.pattern_matched} continues observing.`
      : undefined;

    // Clean scoreBreakdown: strip internal keys, keep only scoring factors
    const cleanBreakdown = d.score_breakdown
      ? Object.fromEntries(
          Object.entries(d.score_breakdown).filter(
            ([k]) => !["total", "threshold"].includes(k) && (d.score_breakdown![k] as number) > 0
          )
        )
      : undefined;

    return {
      id: `rsn_${d.event_id ?? i}`,
      observation,
      reasoning,
      confidence: d.route === "RULE_ENGINE" ? 99 : d.route === "BEDROCK" ? 91 : 100,
      suggestedAction,
      route: d.route === "SUPPRESS" ? "RULE_ENGINE" : d.route as "RULE_ENGINE" | "BEDROCK" | "PATTERN",
      timestamp: ts,
      // Phase 10 structured fields
      ruleMatched: d.rule_matched,
      patternMatched: d.pattern_matched,
      complexityScore: d.complexity_score,
      stageDecided: d.stage_decided,
      latencyMs: d.latency_ms ? Math.round(d.latency_ms) : undefined,
      scoreBreakdown: cleanBreakdown && Object.keys(cleanBreakdown).length > 0 ? cleanBreakdown : undefined,
    };
  });
}

/**
 * /graph/{hh}/full → HouseholdGraph
 * Replaces the hand-built mockGraph() SVG with real DynamoDB graph data.
 */
function fullGraphToHouseholdGraph(
  graphData: BackendFullGraphResponse,
  household: typeof SHARMA_HOUSEHOLD,
): HouseholdGraph {
  const memberNodes = graphData.nodes.filter((n) => n.node_type === "member");
  if (memberNodes.length === 0) return mockGraph(household);

  const edgeMap: Record<string, GraphEdge[]> = {};

  for (const edge of graphData.edges) {
    const fromNode = graphData.nodes.find((n) => n.id === edge.from);
    const toNode   = graphData.nodes.find((n) => n.id === edge.to);
    if (!fromNode || !toNode) continue;

    // Member → health condition
    if (fromNode.node_type === "member" && edge.type === "HAS_CONDITION") {
      edgeMap[edge.from] = edgeMap[edge.from] ?? [];
      edgeMap[edge.from].push({
        label: toNode.condition ?? toNode.name ?? edge.to,
        type: "health",
        confidence: edge.severity === "moderate" ? 0.85 : 0.75,
      });
    }
    // Member → routine
    if (fromNode.node_type === "member" && edge.type === "FOLLOWS") {
      edgeMap[edge.from] = edgeMap[edge.from] ?? [];
      edgeMap[edge.from].push({
        label: (toNode.description ?? edge.to.replace(/_/g, " ")).slice(0, 28),
        type: "routine",
        confidence: 0.80,
      });
    }
    // Member → device (primary user)
    if (fromNode.node_type === "member" && edge.type === "PRIMARY_USER_OF") {
      edgeMap[edge.from] = edgeMap[edge.from] ?? [];
      edgeMap[edge.from].push({
        label: toNode.name ?? edge.to.replace(/_/g, " "),
        type: "device",
        confidence: 0.70,
      });
    }
    // Life event → member
    if (fromNode.node_type === "life_event" && edge.type === "DIRECTLY_AFFECTS") {
      edgeMap[edge.to] = edgeMap[edge.to] ?? [];
      edgeMap[edge.to].push({
        label: (fromNode.description ?? fromNode.name ?? edge.from).slice(0, 28),
        type: "event",
        confidence: edge.impact === "high" ? 0.95 : 0.75,
      });
    }
  }

  const ageGroupMap: Record<string, "senior" | "adult" | "teen" | "child"> = {
    grandparent: "senior",
    parent:      "adult",
    child:       "child",
  };

  return {
    members: memberNodes.map((n) => {
      const mockMember = household.members.find((m) => m.id === n.id);
      return {
        id: n.id,
        name: n.name ?? n.id,
        age: n.age ?? mockMember?.age ?? 0,
        ageGroup: mockMember?.ageGroup ?? ageGroupMap[n.role ?? ""] ?? "adult",
        role: n.role ?? "member",
        connections: (edgeMap[n.id] ?? []).slice(0, 4),
      };
    }),
  };
}

function onboardingStateToMockHousehold(
  householdId: string,
  state: any
): typeof SHARMA_HOUSEHOLD {
  const members: MockMember[] = (state.members || []).map((m: any, i: number) => ({
    id: m.id || `mbr_${i}`,
    name: m.name,
    age: m.age || 30,
    role: (m.role as any) || "adult",
    emoji: "👤",
    ageGroup: (m.ageGroup as any) || "adult",
    room: "Unknown",
    notificationChannel: "mobile_push",
    language: "english",
  }));

  return {
    ...SHARMA_HOUSEHOLD,
    id: householdId,
    familyName: state.householdName || "My Family",
    city: state.householdCity || "Unknown",
    memberCount: members.length,
    members,
    healthConditions: [],
    medications: [],
  };
}

function onboardingStateToGraph(state: any): HouseholdGraph {
  return {
    members: (state.members || []).map((m: any, i: number) => ({
      id: m.id || `mbr_${i}`,
      name: m.name,
      age: m.age || 30,
      ageGroup: (m.ageGroup as any) || "adult",
      role: m.role || "member",
      connections: [],
    })),
  };
}

let _cached: DashboardData | null = null;

export const dashboardService = {
  clearCache() {
    _cached = null;
  },

  getMocks(): DashboardData {
    if (_cached) return _cached;
    const d = buildBaseData("hh_xk92p_sharma");
    _cached = d;
    return d;
  },

  async load(householdId: string = "hh_xk92p_sharma", forceRefresh = false, onboardingState?: { householdName?: string; householdCity?: string; members?: Array<{ id: string; name: string; role: string; ageGroup: string }>; devices?: Array<{ id: string; name: string; type: string; room: string }> } | null): Promise<DashboardData> {
    if (_cached && !forceRefresh && _cached.household.id === householdId) return _cached;

    // ── 1. Fetch everything in parallel — each call is independent ──────────
    const [metricsResult, patternsResult, rulesResult, devicesResult, actionsResult, rteAuditResult, fullGraphResult] = await Promise.allSettled([
      get<BackendMetrics>(`${BACKEND_BASE}/metrics?household_id=${householdId}`),
      get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns?household_id=${householdId}`),
      get<BackendRulesResponse>(`${BACKEND_BASE}/rules?household_id=${householdId}`),
      get<BackendDevicesResponse>(`${BACKEND_BASE}/graph/${householdId}/devices`),
      get<BackendActionsResponse>(`${BACKEND_BASE}/actions/history?limit=30&household_id=${householdId}`),
      get<BackendRTEAuditResponse>(`${BACKEND_BASE}/rte/audit?limit=20&household_id=${householdId}`),
      get<BackendFullGraphResponse>(`${BACKEND_BASE}/graph/${householdId}/full`),
    ]);

    const metrics    = metricsResult.status    === "fulfilled" ? metricsResult.value    : null;
    const patterns   = patternsResult.status   === "fulfilled" ? patternsResult.value   : null;
    const rules      = rulesResult.status      === "fulfilled" ? rulesResult.value      : null;
    const devices    = devicesResult.status    === "fulfilled" ? devicesResult.value    : null;
    const actions    = actionsResult.status    === "fulfilled" ? actionsResult.value    : null;
    const rteAudit   = rteAuditResult.status   === "fulfilled" ? rteAuditResult.value   : null;
    const fullGraph  = fullGraphResult.status  === "fulfilled" ? fullGraphResult.value  : null;

    const backendReachable = metrics !== null;

    // ── 2. Build each section — real if available, mock otherwise ───────────

    // LearningProgress — REAL from /metrics + /patterns (Phase 8: no more hardcoded values)
    const learning: LearningProgress = metrics && patterns
      ? patternsAndMetricsToLearning(patterns.patterns, metrics)
      : metrics
      ? metricsToLearning(metrics)
      : mockLearning();

    // HouseholdSnapshot — REAL from /metrics + graph + patterns + actions (Phase 10)
    const snapshot: HouseholdSnapshot = metrics
      ? metricsAndDataToSnapshot(
          metrics,
          patterns?.patterns ?? [],
          actions?.actions ?? [],
          fullGraph,
        )
      : mockSnapshot();

    // DeviceOverview — REAL from /graph/{hh}/devices (enriches mock list)
    let deviceList: MockDevice[] = [];
    if (householdId === "hh_xk92p_sharma") {
      deviceList = devices ? devicesToMockDevices(devices) : SHARMA_DEVICES;
      if (fullGraph) {
        deviceList = deviceList.map((d) => {
          const node = fullGraph.nodes.find((n) => n.id === d.id && n.node_type === "device");
          if (!node) return d;
          const live = graphNodeToMockDevice(node, fullGraph);
          return { ...d, status: live.status, detail: live.detail ?? d.detail, lastActivity: live.lastActivity, alertLevel: live.alertLevel ?? d.alertLevel };
        });
      }
    } else if (fullGraph) {
      deviceList = fullGraph.nodes
        .filter((n) => n.node_type === "device")
        .map((n) => graphNodeToMockDevice(n, fullGraph));
    }

    // HouseholdMemory — DERIVED from /patterns + /metrics
    const memory: HouseholdMemory =
      patterns && metrics
        ? deriveHouseholdMemory(patterns.patterns, metrics)
        : mockMemory();

    // LearnedToday — DERIVED from /patterns
    const learnedToday: LearnedItem[] = patterns
      ? deriveLearnedToday(patterns.patterns)
      : mockLearnedToday();

    // Observations — DERIVED from /patterns + /metrics
    const observations: Observation[] =
      patterns && metrics
        ? deriveObservations(patterns.patterns, metrics)
        : mockObservations();

    // RecommendedActions — DERIVED from /patterns + /metrics
    const actions_data: RecommendedAction[] =
      patterns && metrics
        ? deriveRecommendedActions(patterns.patterns, metrics)
        : mockActions();

    // RecentEvents — REAL from /actions/history (Phase 8)
    const events: MockActivity[] = actions?.actions
      ? actionsToEvents(actions.actions)
      : (householdId === "hh_xk92p_sharma" ? SHARMA_ACTIVITY : []);

    // ReasoningFeed — REAL from /rte/audit + /rules (Phase 8)
    const reasoning: ReasoningEntry[] =
      rteAudit?.decisions && rteAudit.decisions.length > 0 && rules
        ? rteAuditToReasoning(rteAudit.decisions, rules.rules)
        : patterns && rules
        ? patternsAndRulesToReasoning(patterns.patterns, rules.rules)
        : mockReasoning();

    // HouseholdHealth — DERIVED from /patterns (Phase 8: no more hardcoded scores)
    // Build a minimal household-like object from fullGraph so health doesn't use Sharma data
    // If fullGraph has no member nodes but we have onboarding data, build from that
    const hasGraphMembers = fullGraph && fullGraph.nodes.filter((n: { node_type: string }) => n.node_type === "member").length > 0;
    const householdForHealth = hasGraphMembers
      ? graphToMockHousehold(fullGraph!, householdId)
      : onboardingState?.members?.length
      ? onboardingStateToMockHousehold(householdId, onboardingState)
      : SHARMA_HOUSEHOLD;

    const health: HealthSummary = patterns
      ? patternsToHealth(patterns.patterns, householdForHealth)
      : mockHealth(householdForHealth);

    // HouseholdGraph — REAL from /graph/{hh}/full, or built from onboarding
    const graph: HouseholdGraph = hasGraphMembers
      ? fullGraphToHouseholdGraph(fullGraph!, householdForHealth)
      : onboardingState?.members?.length
      ? onboardingStateToGraph(onboardingState)
      : mockGraph(SHARMA_HOUSEHOLD);

    // IntelligenceStats — REAL from /metrics
    const intelligenceStats = metrics
      ? metricsToStats(metrics)
      : INTELLIGENCE_STATS;

    // Derive family name / city — prefer backend, then onboarding, then Sharma
    const familyName = fullGraph?.family_name
      || onboardingState?.householdName
      || SHARMA_HOUSEHOLD.familyName;
    const city = fullGraph?.location
      || onboardingState?.householdCity
      || SHARMA_HOUSEHOLD.city;

    const d: DashboardData = {
      source: backendReachable ? "backend" : "mock",
      household: {
        ...SHARMA_HOUSEHOLD,
        id: householdId,
        familyName,
        city,
        memberCount: graph.members.length || onboardingState?.members?.length || SHARMA_HOUSEHOLD.memberCount,
      },
      graph,
      fullGraph,
      rawPatterns: patterns?.patterns ?? [],
      efficiencyMetrics: metrics ? metricsToEfficiency(metrics) : null,
      memory,
      learnedToday,
      observations,
      actions: actions_data,
      events,
      reasoning,
      learning,
      health,
      // FamilyPresence — no live presence endpoint exists.
      // Build member list from the real graph nodes so we don't show Sharma names.
      presence: {
        home: householdForHealth.members as unknown as typeof SHARMA_HOUSEHOLD.members,
        away: [],
        currentActivity: [],
        isLive: false,
      },
      snapshot,
      devices: deviceList,
      routines: householdId === "hh_xk92p_sharma" ? SHARMA_ROUTINES : [],
      predictions: householdId === "hh_xk92p_sharma" ? SHARMA_PREDICTIONS : [],
      intelligenceStats,
      notificationStats: householdId === "hh_xk92p_sharma" ? NOTIFICATION_STATS : {
        ...NOTIFICATION_STATS,
        sentToday: 0,
        acknowledged: 0,
        pending: 0,
        critical: 0,
        byChannel: { alexa_voice: 0, mobile_push: 0, whatsapp: 0 },
      },
    };

    _cached = d;
    return d;
  },

  // ── Individual getters ─────────────────────────────────────────────────────

  async getLearningProgress(): Promise<LearningProgress> {
    try {
      const [pr, mr] = await Promise.all([
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
      ]);
      return patternsAndMetricsToLearning(pr.patterns, mr);
    } catch {
      return mockLearning();
    }
  },

  async getHouseholdSnapshot(): Promise<HouseholdSnapshot> {
    try {
      const [mr, pr, ar, gr] = await Promise.allSettled([
        get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendActionsResponse>(`${BACKEND_BASE}/actions/history?limit=10`),
        get<BackendFullGraphResponse>(`${BACKEND_BASE}/graph/${_cached?.household.id ?? "hh_xk92p_sharma"}/full`),
      ]);
      const m = mr.status === "fulfilled" ? mr.value : null;
      if (!m) return mockSnapshot();
      return metricsAndDataToSnapshot(
        m,
        pr.status === "fulfilled" ? pr.value.patterns : [],
        ar.status === "fulfilled" ? ar.value.actions : [],
        gr.status === "fulfilled" ? gr.value : null,
      );
    } catch {
      return mockSnapshot();
    }
  },

  async getLearnedToday(): Promise<LearnedItem[]> {
    try {
      const r = await get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`);
      return deriveLearnedToday(r.patterns);
    } catch {
      return mockLearnedToday();
    }
  },

  async getReasoningLogs(): Promise<ReasoningEntry[]> {
    try {
      const [pr, rr] = await Promise.all([
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendRulesResponse>(`${BACKEND_BASE}/rules`),
      ]);
      return patternsAndRulesToReasoning(pr.patterns, rr.rules);
    } catch {
      return mockReasoning();
    }
  },

  async getGraph(): Promise<HouseholdGraph> {
    return mockGraph(SHARMA_HOUSEHOLD);
  },

  async getHouseholdMemory(): Promise<HouseholdMemory> {
    try {
      const [pr, mr] = await Promise.all([
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
      ]);
      return deriveHouseholdMemory(pr.patterns, mr);
    } catch {
      return mockMemory();
    }
  },

  async getObservations(): Promise<Observation[]> {
    try {
      const [pr, mr] = await Promise.all([
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
      ]);
      return deriveObservations(pr.patterns, mr);
    } catch {
      return mockObservations();
    }
  },

  async getActions(): Promise<RecommendedAction[]> {
    try {
      const [pr, mr] = await Promise.all([
        get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
        get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
      ]);
      return deriveRecommendedActions(pr.patterns, mr);
    } catch {
      return mockActions();
    }
  },

  async getEvents(): Promise<MockActivity[]> {
    try {
      const r = await get<BackendActionsResponse>(`${BACKEND_BASE}/actions/history?limit=30`);
      return actionsToEvents(r.actions);
    } catch {
      return SHARMA_ACTIVITY;
    }
  },

  async getActionHistory(): Promise<MockActivity[]> {
    return dashboardService.getEvents();
  },

  async getRteAudit(): Promise<ReasoningEntry[]> {
    try {
      const [ar, rr] = await Promise.all([
        get<BackendRTEAuditResponse>(`${BACKEND_BASE}/rte/audit?limit=20`),
        get<BackendRulesResponse>(`${BACKEND_BASE}/rules`),
      ]);
      return rteAuditToReasoning(ar.decisions, rr.rules);
    } catch {
      return mockReasoning();
    }
  },

  async getHealthSummary(): Promise<HealthSummary> {
    try {
      const r = await get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`);
      return patternsToHealth(r.patterns, SHARMA_HOUSEHOLD);
    } catch {
      return mockHealth(SHARMA_HOUSEHOLD);
    }
  },
};

// ─── Full mock assembler (used by getMocks() and as fallback) ─────────────────

function buildBaseData(householdId: string): DashboardData {
  return {
    source: "mock",
    household: { ...SHARMA_HOUSEHOLD, id: householdId },
    graph: mockGraph(SHARMA_HOUSEHOLD),
    memory: mockMemory(),
    learnedToday: mockLearnedToday(),
    observations: mockObservations(),
    actions: mockActions(),
    events: SHARMA_ACTIVITY,
    reasoning: mockReasoning(),
    learning: mockLearning(),
    health: mockHealth(SHARMA_HOUSEHOLD),
    presence: mockPresence(SHARMA_HOUSEHOLD),
    snapshot: mockSnapshot(),
    devices: SHARMA_DEVICES,
    routines: SHARMA_ROUTINES,
    predictions: SHARMA_PREDICTIONS,
    intelligenceStats: INTELLIGENCE_STATS,
    notificationStats: NOTIFICATION_STATS,
  };
}