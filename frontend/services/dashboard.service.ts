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

// ─── Domain types ─────────────────────────────────────────────────────────────

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
}

export interface HouseholdSnapshot {
  membersHome: number;
  membersAway: number;
  nextEvent: string;
  waterTankStatus: string;
  nextMedicationTime: string;
  currentMoodEstimate: string;
}

export interface DashboardData {
  source: "backend" | "mock";
  household: MockHousehold;
  graph: HouseholdGraph;
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
 * /metrics → HouseholdSnapshot
 * Adds real circuit breaker and event counts.
 */
function metricsToSnapshot(m: BackendMetrics): HouseholdSnapshot {
  const cbStatus = m.circuit_breaker?.state === "CLOSED"
    ? "Bedrock AI available"
    : m.circuit_breaker?.state === "OPEN"
    ? "Bedrock AI circuit open — rules only"
    : "Bedrock AI degraded";

  const eventsToday = m.total_events_processed > 0
    ? `${m.total_events_processed} events processed today`
    : "No events processed yet — fire a simulation to start";

  return {
    membersHome: 5,
    membersAway: 1,
    nextEvent: "Family dinner expected in about 1 hour",
    waterTankStatus: "Full — auto-stopped at 96%",
    nextMedicationTime: "Dadaji's BP medicine at 8:30 PM",
    currentMoodEstimate: `${eventsToday} · ${cbStatus}`,
  };
}

/**
 * /graph/{hh}/devices → MockDevice[]
 * The backend returns context for the water motor only.
 * We enrich the mock device list with the real primary_user from the graph.
 */
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

  if (learning.length === 0) return mockLearnedToday();

  return learning.map((p, i) => {
    const memberName = p.member_id
      ? SHARMA_MEMBERS.find((m) => m.id === p.member_id)?.name
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

  if (promoted.length === 0) return mockReasoning();

  const entries: ReasoningEntry[] = promoted.slice(0, 5).map((p, i) => {
    const ruleId = p.promoted_rule_id;
    const rule = rules.find((r) => r.rule_id === ruleId);
    const memberName = p.member_id
      ? SHARMA_MEMBERS.find((m) => m.id === p.member_id)?.name ?? p.member_id
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
 * /metrics → intelligenceStats
 */
function metricsToStats(m: BackendMetrics): typeof INTELLIGENCE_STATS {
  return {
    patternsDetected: m.active_patterns,
    patternsPromoted: m.promoted_patterns,
    rulesActive: 9,
    actionsToday: m.total_events_processed,   // ← use events processed, not actions dispatched
    safetyActionsToday: 0,
    daysLearning: 52,
    routesBreakdown: {
      ruleEngine: m.rule_engine_calls,
      bedrock: m.bedrock_calls,
      suppressed: m.suppressed_events,
    },
  };
}

// ─── Main loader ──────────────────────────────────────────────────────────────

let _cached: DashboardData | null = null;

export const dashboardService = {
  clearCache() {
    _cached = null;
  },

  getMocks(): DashboardData {
    if (_cached) return _cached;
    const d = buildAllMock();
    _cached = d;
    return d;
  },

  async load(forceRefresh = false): Promise<DashboardData> {
    if (_cached && !forceRefresh) return _cached;

    // ── 1. Fetch everything in parallel — each call is independent ──────────
    const [metricsResult, patternsResult, rulesResult, devicesResult] = await Promise.allSettled([
      get<BackendMetrics>(`${BACKEND_BASE}/metrics`),
      get<BackendPatternsResponse>(`${BACKEND_BASE}/patterns`),
      get<BackendRulesResponse>(`${BACKEND_BASE}/rules`),
      get<BackendDevicesResponse>(`${BACKEND_BASE}/graph/hh_xk92p_sharma/devices`),
    ]);

    const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : null;
    const patterns = patternsResult.status === "fulfilled" ? patternsResult.value : null;
    const rules = rulesResult.status === "fulfilled" ? rulesResult.value : null;
    const devices = devicesResult.status === "fulfilled" ? devicesResult.value : null;

    const backendReachable = metrics !== null;

    // ── 2. Build each section — real if available, mock otherwise ───────────

    // LearningProgress — REAL from /metrics
    const learning: LearningProgress = metrics
      ? metricsToLearning(metrics)
      : mockLearning();

    // HouseholdSnapshot — REAL from /metrics
    const snapshot: HouseholdSnapshot = metrics
      ? metricsToSnapshot(metrics)
      : mockSnapshot();

    // DeviceOverview — REAL from /graph/{hh}/devices (enriches mock list)
    const deviceList: MockDevice[] = devices
      ? devicesToMockDevices(devices)
      : SHARMA_DEVICES;

    // HouseholdMemory — DERIVED from /patterns + /metrics  [Phase 7]
    const memory: HouseholdMemory =
      patterns && metrics
        ? deriveHouseholdMemory(patterns.patterns, metrics)
        : mockMemory();

    // LearnedToday — DERIVED from /patterns  [Phase 7]
    const learnedToday: LearnedItem[] = patterns
      ? deriveLearnedToday(patterns.patterns)
      : mockLearnedToday();

    // Observations — DERIVED from /patterns + /metrics  [Phase 7]
    const observations: Observation[] =
      patterns && metrics
        ? deriveObservations(patterns.patterns, metrics)
        : mockObservations();

    // RecommendedActions — DERIVED from /patterns + /metrics  [Phase 7]
    const actions: RecommendedAction[] =
      patterns && metrics
        ? deriveRecommendedActions(patterns.patterns, metrics)
        : mockActions();

    // ReasoningFeed — REAL from /patterns (PROMOTED) + /rules
    const reasoning: ReasoningEntry[] =
      patterns && rules
        ? patternsAndRulesToReasoning(patterns.patterns, rules.rules)
        : mockReasoning();

    // IntelligenceStats — REAL from /metrics
    const intelligenceStats = metrics
      ? metricsToStats(metrics)
      : INTELLIGENCE_STATS;

    // Everything else stays mock
    const d: DashboardData = {
      source: backendReachable ? "backend" : "mock",
      household: SHARMA_HOUSEHOLD,
      graph: mockGraph(SHARMA_HOUSEHOLD),
      memory,         // DERIVED Phase 7
      learnedToday,   // DERIVED Phase 7
      observations,   // DERIVED Phase 7
      actions,        // DERIVED Phase 7
      events: SHARMA_ACTIVITY,
      reasoning,
      learning,
      health: mockHealth(SHARMA_HOUSEHOLD),
      presence: mockPresence(SHARMA_HOUSEHOLD),
      snapshot,
      devices: deviceList,
      routines: SHARMA_ROUTINES,
      predictions: SHARMA_PREDICTIONS,
      intelligenceStats,
      notificationStats: NOTIFICATION_STATS,
    };

    _cached = d;
    return d;
  },

  // ── Individual getters ─────────────────────────────────────────────────────

  async getLearningProgress(): Promise<LearningProgress> {
    try {
      const m = await get<BackendMetrics>(`${BACKEND_BASE}/metrics`);
      return metricsToLearning(m);
    } catch {
      return mockLearning();
    }
  },

  async getHouseholdSnapshot(): Promise<HouseholdSnapshot> {
    try {
      const m = await get<BackendMetrics>(`${BACKEND_BASE}/metrics`);
      return metricsToSnapshot(m);
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
    return SHARMA_ACTIVITY;
  },

  async getHealthSummary(): Promise<HealthSummary> {
    return mockHealth(SHARMA_HOUSEHOLD);
  },
};

// ─── Full mock assembler (used by getMocks() and as fallback) ─────────────────

function buildAllMock(): DashboardData {
  return {
    source: "mock",
    household: SHARMA_HOUSEHOLD,
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
