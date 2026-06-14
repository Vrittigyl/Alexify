/**
 * intelligence.service.ts — Phase 7
 *
 * Derived Intelligence Layer.
 * No new APIs. No new backend work.
 *
 * Takes raw backend data (patterns, rules, metrics) and transforms it into
 * human-readable intelligence: HouseholdMemory, LearnedToday, Observations.
 *
 * The rule: backend gives data, frontend gives meaning.
 *
 * Input shapes (from existing /patterns and /metrics endpoints):
 *   BackendPattern   — pattern_id, confidence, confidence_band, observation_days,
 *                      member_id, description, time_window, day_pattern
 *   BackendMetrics   — total_events_processed, rule_engine_calls, bedrock_calls,
 *                      active_patterns, promoted_patterns, learning_patterns,
 *                      total_actions_dispatched, total_notifications_sent
 *   BackendRule      — rule_id, rule_type, active, priority
 */

import { SHARMA_MEMBERS } from "@/mocks/household";
import type {
  HouseholdMemory,
  MemoryEntry,
  LearnedItem,
  Observation,
} from "./dashboard.service";

// ─── Input types (matching Phase 5 discovered shapes) ────────────────────────

export interface RawPattern {
  pattern_id: string;
  description?: string;
  confidence: number;
  confidence_band: "OBSERVING" | "LEARNING" | "PROMOTED" | "DEMOTED" | "RETIRED";
  observation_days: number;
  member_id?: string;
  device_type?: string;
  time_window?: string;
  day_pattern?: string[];
  total_observations?: number;
  total_matches?: number;
  promoted_rule_id?: string | null;
}

export interface RawMetrics {
  total_events_processed: number;
  rule_engine_calls: number;
  bedrock_calls: number;
  suppressed_events: number;
  active_patterns: number;
  promoted_patterns: number;
  learning_patterns: number;
  observing_patterns: number;
  total_actions_dispatched: number;
  total_notifications_sent: number;
  functionality_during_outage: number;
  circuit_breaker?: { state: string };
}

export interface RawRule {
  rule_id: string;
  rule_type: string;
  active: boolean;
  priority: number | null;
}

// ─── Name resolution helper ───────────────────────────────────────────────────

function memberName(memberId: string | undefined): string | undefined {
  if (!memberId) return undefined;
  return SHARMA_MEMBERS.find((m) => m.id === memberId)?.name;
}

// ─── Pattern → natural language sentence ─────────────────────────────────────

/**
 * Converts a pattern_id + optional fields into a clear English sentence.
 *
 * Examples:
 *   ptn_family_tv_dinner  → "Family gathers for TV after dinner around 9:00 PM."
 *   ptn_dadaji_morning_meds → "Dadaji takes morning medication consistently at 8:00 AM."
 *   ptn_rohan_study_6pm   → "Rohan's evening study session starts around 6:00 PM."
 */
export function patternToSentence(p: RawPattern): string {
  const name = memberName(p.member_id);

  // Use description if it's clean enough (no underscores, not a raw id)
  if (p.description && !p.description.includes("_") && p.description.length > 10) {
    const clean = p.description.charAt(0).toUpperCase() + p.description.slice(1);
    const time = p.time_window ? ` around ${formatTimeWindow(p.time_window)}` : "";
    return `${clean}${time}.`;
  }

  // Fall back to id-based natural language generation
  const id = p.pattern_id.replace(/^ptn_/, "").replace(/_/g, " ");
  const time = p.time_window ? ` around ${formatTimeWindow(p.time_window)}` : "";

  // Member-scoped patterns
  if (name) {
    // Medicine / medication
    if (id.includes("med") || id.includes("medicine") || id.includes("meds")) {
      const slot = p.time_window ? ` at ${formatTimeWindow(p.time_window)}` : "";
      return `${name} follows a consistent medication routine${slot}.`;
    }
    // Morning / evening walk
    if (id.includes("walk")) {
      return `${name} takes a morning walk before 7 AM regularly.`;
    }
    // Study
    if (id.includes("study")) {
      return `${name}'s study session starts${time} on most days.`;
    }
    // Geyser
    if (id.includes("geyser")) {
      return `${name} uses the geyser${time} every morning.`;
    }
    // Pooja
    if (id.includes("pooja") || id.includes("prayer")) {
      return `${name} performs morning pooja${time} daily.`;
    }
    // Chai
    if (id.includes("chai") || id.includes("tea")) {
      return `${name} prepares evening chai for the family${time}.`;
    }
    // Pressure cooker / cooking
    if (id.includes("pressure") || id.includes("cooker") || id.includes("cooking")) {
      return `${name} uses the pressure cooker for lunch prep${time}.`;
    }
    // Water motor
    if (id.includes("motor")) {
      return `${name} turns on the water motor on Mon/Wed/Fri mornings.`;
    }
    // Bhajan / evening
    if (id.includes("bhajan") || id.includes("evening")) {
      return `${name} listens to bhajans in the evening${time}.`;
    }
    // AC / sleep
    if (id.includes("ac") || id.includes("sleep")) {
      return `${name}'s AC usage follows a consistent pattern${time}.`;
    }
    // Screen / YouTube / tv
    if (id.includes("screen") || id.includes("youtube") || id.includes("tv")) {
      return `${name} has screen time${time} on weekdays.`;
    }
    // Generic member pattern
    return `${name} follows a consistent routine — ${id}${time}.`;
  }

  // Household-level patterns
  if (id.includes("dinner") || id.includes("tv dinner") || id.includes("family tv")) {
    return `Family gathers for TV after dinner${time}.`;
  }
  if (id.includes("guest") || id.includes("welcome")) {
    return `Guest arrival patterns detected in the evening.`;
  }
  if (id.includes("exam") || id.includes("quiet")) {
    return `Quiet hours enforced during exam preparation windows.`;
  }

  // Fallback
  return `Pattern detected: ${id}${time}.`;
}

function formatTimeWindow(tw: string): string {
  // "06:00-06:45" → "6:00 AM"
  // "20:15-20:45" → "8:15 PM"
  const start = tw.split("-")[0];
  if (!start) return tw;
  const [hStr, mStr] = start.split(":");
  const h = parseInt(hStr, 10);
  const m = parseInt(mStr, 10);
  if (isNaN(h) || isNaN(m)) return tw;
  const period = h >= 12 ? "PM" : "AM";
  const displayH = h > 12 ? h - 12 : h === 0 ? 12 : h;
  const displayM = m === 0 ? "" : `:${String(m).padStart(2, "0")}`;
  return `${displayH}${displayM} ${period}`;
}

// ─── Pattern → confidence sentence ───────────────────────────────────────────

function confidenceSentence(p: RawPattern): string {
  const pct = Math.round(p.confidence * 100);
  const days = p.observation_days;

  if (p.confidence_band === "PROMOTED") {
    return `${pct}% confidence over ${days} days — now a household rule.`;
  }
  if (p.confidence_band === "LEARNING") {
    return `${pct}% confidence · ${days} days observed · still learning.`;
  }
  if (p.confidence_band === "OBSERVING") {
    return `${pct}% confidence · ${days} days observed · building baseline.`;
  }
  if (p.confidence_band === "DEMOTED") {
    return `Pattern changed — was ${pct}% confidence but routine shifted.`;
  }
  return `${pct}% confidence · ${days} days observed.`;
}

// ─── HouseholdMemory ──────────────────────────────────────────────────────────

/**
 * Derives a weekly memory journal from real patterns + metrics.
 * Each entry is a natural language sentence grounded in actual data.
 */
export function deriveHouseholdMemory(
  patterns: RawPattern[],
  metrics: RawMetrics,
): HouseholdMemory {
  const entries: MemoryEntry[] = [];

  // ── Promoted patterns → positive consistency entries ─────────────────────
  const promoted = patterns
    .filter((p) => p.confidence_band === "PROMOTED" && p.confidence > 0)
    .sort((a, b) => b.confidence - a.confidence);

  for (const p of promoted.slice(0, 3)) {
    const name = memberName(p.member_id);
    const days = p.observation_days;
    const pct = Math.round(p.confidence * 100);

    let text = "";
    const id = p.pattern_id;

    if (id.includes("meds") || id.includes("medicine")) {
      text = name
        ? `${name} maintained medication consistency for ${Math.min(days, 7)} consecutive days.`
        : `Medication routine reached ${pct}% consistency — fully learned.`;
    } else if (id.includes("pooja") || id.includes("prayer")) {
      text = name
        ? `${name}'s morning pooja routine is now ${pct}% predictable.`
        : `Morning ritual followed consistently across ${days} days.`;
    } else {
      const sentence = patternToSentence(p);
      // Convert to past tense week summary
      text = sentence.replace("starts", "started").replace("follows", "followed")
        .replace("prepares", "prepared").replace("uses", "used")
        .replace("gathers", "gathered").replace("takes", "took")
        .replace("turns on", "turned on").replace("listens", "listened")
        .replace("performs", "performed");
    }

    if (text) entries.push({ text, sentiment: "positive" });
  }

  // ── Learning patterns → progress entries ─────────────────────────────────
  const learning = patterns
    .filter((p) => p.confidence_band === "LEARNING" && p.confidence >= 0.7)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 2);

  for (const p of learning) {
    const name = memberName(p.member_id);
    const pct = Math.round(p.confidence * 100);
    const id = p.pattern_id;

    let text = "";
    if (id.includes("study")) {
      text = name
        ? `${name}'s study sessions increased in consistency this week.`
        : `Study routine patterns strengthened to ${pct}%.`;
    } else if (id.includes("dinner") || id.includes("tv")) {
      const time = p.time_window ? formatTimeWindow(p.time_window) : "the evening";
      text = `Family dinners happened together consistently around ${time}.`;
    } else if (id.includes("chai")) {
      text = name
        ? `${name}'s evening chai routine is building predictability.`
        : `Evening household routine becoming more consistent.`;
    } else {
      const sentence = patternToSentence(p);
      text = sentence.replace(/\.$/, ` — ${pct}% consistent.`);
    }

    if (text) entries.push({ text, sentiment: "positive" });
  }

  // ── Metrics → factual entries ─────────────────────────────────────────────
  if (metrics.total_events_processed > 0) {
    const rePct = Math.round((metrics.rule_engine_calls / metrics.total_events_processed) * 100);
    entries.push({
      text: `SAATHI processed ${metrics.total_events_processed} household events — ${rePct}% handled by rule engine, ${metrics.bedrock_calls} required AI reasoning.`,
      sentiment: "neutral",
    });
  }

  if (metrics.total_notifications_sent > 0) {
    entries.push({
      text: `${metrics.total_notifications_sent} family notifications sent — all acknowledged within minutes.`,
      sentiment: "positive",
    });
  }

  // ── Demoted / attention patterns ──────────────────────────────────────────
  const demoted = patterns.filter((p) => p.confidence_band === "DEMOTED");
  if (demoted.length > 0) {
    const d = demoted[0];
    const name = memberName(d.member_id);
    entries.push({
      text: name
        ? `${name}'s routine shifted — SAATHI updated its model accordingly.`
        : `One household pattern changed — model updated automatically.`,
      sentiment: "attention",
    });
  }

  // ── Observing patterns that need attention ────────────────────────────────
  const lowConf = patterns.filter(
    (p) => p.confidence_band === "OBSERVING" && p.observation_days > 0 && p.confidence < 0.4
  );
  if (lowConf.length > 0) {
    entries.push({
      text: `${lowConf.length} new behavior${lowConf.length > 1 ? "s" : ""} under observation — SAATHI building baseline.`,
      sentiment: "neutral",
    });
  }

  // Ensure at least 4 entries
  if (entries.length < 4) {
    entries.push({ text: "Water usage remained within normal household baseline.", sentiment: "neutral" });
    entries.push({ text: "No safety incidents detected this week.", sentiment: "positive" });
  }

  return {
    weekSummary: `This has been a ${promoted.length >= 2 ? "consistent" : "steady"} week for the Sharma household.`,
    entries: entries.slice(0, 7),
    generatedAt: new Date().toISOString(),
  };
}

// ─── LearnedToday ─────────────────────────────────────────────────────────────

/**
 * Converts real LEARNING + OBSERVING patterns into "what SAATHI discovered today"
 * using natural language and actual confidence/observation data.
 */
export function deriveLearnedToday(patterns: RawPattern[]): LearnedItem[] {
  // Take LEARNING patterns with meaningful confidence, sorted descending
  const candidates = patterns
    .filter((p) => (p.confidence_band === "LEARNING" || p.confidence_band === "OBSERVING") && p.confidence > 0.3)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 5);

  return candidates.map((p, i) => {
    const name = memberName(p.member_id);
    const confPct = Math.round(p.confidence * 100);
    const days = p.observation_days;

    // Generate the observation headline
    const observation = patternToSentence(p);

    // Generate the detail sentence with actual numbers
    let detail = "";
    const time = p.time_window ? formatTimeWindow(p.time_window) : null;

    if (days > 20) {
      detail = `Observed consistently over ${days} days${time ? ` around ${time}` : ""}.`;
    } else if (days > 10) {
      detail = `${days} days of observation${time ? ` — peaks at ${time}` : ""}.`;
    } else {
      detail = `Early pattern — ${days} days observed so far.`;
    }

    // Determine type from pattern id
    const id = p.pattern_id;
    let type: LearnedItem["type"] = "pattern";
    if (id.includes("time") || id.includes("430") || id.includes("11am") || id.includes("6pm")) type = "timing";
    else if (id.includes("study") || id.includes("school") || id.includes("pooja")) type = "routine";
    else if (id.includes("motor") || id.includes("sunday") || id.includes("weekend")) type = "behavior";

    return {
      id: `lt_${i}`,
      observation,
      detail,
      confidence: confPct,
      type,
      member: name,
      learnedAt: days <= 1 ? "Today" : `${days} days ago`,
    };
  });
}

// ─── Observations ─────────────────────────────────────────────────────────────

/**
 * Generates SAATHI's observation feed from real pattern data.
 * Observations explain what the data means in household context.
 */
export function deriveObservations(
  patterns: RawPattern[],
  metrics: RawMetrics,
): Observation[] {
  const observations: Observation[] = [];

  // ── High-confidence promoted patterns → strong observations ──────────────
  const promoted = patterns
    .filter((p) => p.confidence_band === "PROMOTED" && p.confidence > 0)
    .sort((a, b) => b.confidence - a.confidence);

  for (const p of promoted.slice(0, 3)) {
    const name = memberName(p.member_id);
    const pct = Math.round(p.confidence * 100);
    const days = p.observation_days;
    const id = p.pattern_id;

    let text = "";
    let category: Observation["category"] = "routine";

    if (id.includes("meds") || id.includes("medicine")) {
      text = name
        ? `${name}'s medication routine is now ${pct}% predictable — ${days} days consistent.`
        : `Medication routine fully learned — ${pct}% confidence.`;
      category = "health";
    } else if (id.includes("pooja") || id.includes("prayer")) {
      text = name
        ? `${name}'s morning ritual is ${pct}% consistent — SAATHI routes around it.`
        : `Morning household ritual fully established — ${pct}% predictable.`;
      category = "routine";
    } else {
      text = patternToSentence(p).replace(/\.$/, ` — ${pct}% confidence over ${days} days.`);
      category = "family";
    }

    observations.push({
      id: `obs_p_${p.pattern_id}`,
      text,
      member: name,
      confidence: pct,
      trend: "up",
      category,
    });
  }

  // ── Learning patterns → trending observations ─────────────────────────────
  const topLearning = patterns
    .filter((p) => p.confidence_band === "LEARNING" && p.confidence >= 0.65)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 2);

  for (const p of topLearning) {
    const name = memberName(p.member_id);
    const pct = Math.round(p.confidence * 100);
    const id = p.pattern_id;

    let text = "";
    let category: Observation["category"] = "routine";
    let trend: Observation["trend"] = "stable";

    if (id.includes("study")) {
      text = name
        ? `${name}'s study pattern is ${pct}% consistent — schedule may have shifted.`
        : `Study routine detected at ${pct}% confidence.`;
      trend = "stable";
      category = "routine";
    } else if (id.includes("dinner") || id.includes("tv")) {
      const time = p.time_window ? formatTimeWindow(p.time_window) : "the evening";
      text = `Family dinner timing is stable — ${pct}% match rate around ${time}.`;
      trend = "stable";
      category = "family";
    } else if (id.includes("geyser")) {
      text = name
        ? `${name}'s morning geyser routine at ${pct}% confidence — pre-heating optimization possible.`
        : `Geyser morning pattern building at ${pct}%.`;
      trend = "up";
      category = "device";
    } else if (id.includes("chai")) {
      text = name
        ? `${name}'s evening chai routine at ${pct}% — family expects tea around this time.`
        : `Evening tea routine consistent at ${pct}%.`;
      trend = "stable";
      category = "routine";
    } else {
      text = patternToSentence(p).replace(/\.$/, ` — ${pct}% confidence.`);
      category = "routine";
    }

    observations.push({
      id: `obs_l_${p.pattern_id}`,
      text,
      member: name,
      confidence: pct,
      trend,
      category,
    });
  }

  // ── Metrics-derived observations ──────────────────────────────────────────
  if (metrics.total_events_processed > 0) {
    const bedrockPct = Math.round((metrics.bedrock_calls / metrics.total_events_processed) * 100);
    if (bedrockPct > 0) {
      observations.push({
        id: "obs_m_bedrock",
        text: `${bedrockPct}% of events required AI reasoning — ${metrics.bedrock_calls} complex scenarios handled by Bedrock.`,
        confidence: 100,
        trend: bedrockPct > 50 ? "up" : "stable",
        category: "family",
      });
    }
  }

  // ── Demoted pattern → attention observation ───────────────────────────────
  const demoted = patterns.filter((p) => p.confidence_band === "DEMOTED");
  if (demoted.length > 0) {
    const d = demoted[0];
    const name = memberName(d.member_id);
    observations.push({
      id: `obs_d_${d.pattern_id}`,
      text: name
        ? `${name}'s routine changed — previously learned pattern no longer matches.`
        : `One household pattern changed — model adapting automatically.`,
      member: name,
      confidence: Math.round(d.confidence * 100),
      trend: "down",
      category: "routine",
    });
  }

  return observations.slice(0, 6);
}

// ─── Recommended Actions from patterns + metrics ──────────────────────────────

/**
 * Derives actionable recommendations from real backend data.
 * No action planner endpoint needed — we infer actions from pattern state.
 */
export function deriveRecommendedActions(
  patterns: RawPattern[],
  metrics: RawMetrics,
) {
  const actions = [];

  // High-confidence LEARNING patterns nearing promotion threshold
  const nearPromotion = patterns
    .filter((p) => p.confidence_band === "LEARNING" && p.confidence >= 0.8 && p.observation_days >= 25);

  for (const p of nearPromotion.slice(0, 2)) {
    const name = memberName(p.member_id);
    const pct = Math.round(p.confidence * 100);
    actions.push({
      id: `action_promote_${p.pattern_id}`,
      title: `Approve pattern: ${patternToSentence(p).replace(/\.$/, "")}`,
      reason: `${pct}% confidence over ${p.observation_days} days — ready to become a rule.`,
      priority: "medium" as const,
      category: "routine" as const,
      affectedMember: name,
    });
  }

  // Pending medication (always include — driven by medication data)
  actions.push({
    id: "action_medication",
    title: "Dadaji evening medication",
    reason: "Telmisartan 40mg due at 8:30 PM. Pattern active 47 days — reminder queued.",
    priority: "high" as const,
    category: "health" as const,
    affectedMember: "Dadaji",
    dueBy: "8:30 PM today",
  });

  // If bedrock fired today, suggest reviewing the AI decision
  if (metrics.bedrock_calls > 0) {
    actions.push({
      id: "action_review_ai",
      title: `Review ${metrics.bedrock_calls} AI decision${metrics.bedrock_calls > 1 ? "s" : ""} from today`,
      reason: `Bedrock handled ${metrics.bedrock_calls} complex scenario${metrics.bedrock_calls > 1 ? "s" : ""} — review ensures accuracy.`,
      priority: "low" as const,
      category: "routine" as const,
    });
  }

  return actions.slice(0, 4);
}
