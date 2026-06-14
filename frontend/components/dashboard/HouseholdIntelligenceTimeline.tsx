"use client";

/**
 * HouseholdIntelligenceTimeline — Phase 9
 *
 * A chronological story of what SAATHI learned, acted on, and remembered.
 * Combines patterns, actions, and RTE decisions into one unified timeline.
 *
 * Three types of timeline moments:
 *   LEARNED — a pattern reached a new confidence milestone
 *   ACTED   — an action was dispatched (from ActionLog)
 *   REASONED — an RTE decision was made (from RTEAuditLog)
 *   REMINDED — a medication or health reminder was sent
 */

import { motion } from "framer-motion";
import type { MockActivity } from "@/mocks/activity";
import type { ReasoningEntry, LearnedItem } from "@/services/dashboard.service";

type MomentType = "learned" | "acted" | "reasoned" | "reminded";

interface TimelineMoment {
  id: string;
  type: MomentType;
  time: string;
  headline: string;
  detail: string;
  member?: string;
  route?: string;
}

const MOMENT_CONFIG: Record<MomentType, { verb: string; color: string; bg: string; dotColor: string }> = {
  learned:  { verb: "SAATHI learned",   color: "#8b5cf6", bg: "#f5f3ff", dotColor: "#8b5cf6" },
  acted:    { verb: "SAATHI acted",     color: "#0ea5e9", bg: "#e0f2fe", dotColor: "#0ea5e9" },
  reasoned: { verb: "SAATHI reasoned",  color: "#374151", bg: "#f9fafb", dotColor: "#374151" },
  reminded: { verb: "SAATHI reminded",  color: "#10b981", bg: "#f0fdf4", dotColor: "#10b981" },
};

// ─── Build timeline from data ─────────────────────────────────────────────────

function buildTimeline(
  learnedItems: LearnedItem[],
  events: MockActivity[],
  reasoning: ReasoningEntry[],
): TimelineMoment[] {
  const moments: TimelineMoment[] = [];

  // Learned items → "SAATHI learned" moments
  for (const item of learnedItems) {
    moments.push({
      id: `learn_${item.id}`,
      type: "learned",
      time: item.learnedAt,
      headline: item.observation,
      detail: item.detail,
      member: item.member,
    });
  }

  // Recent events → acted / reminded
  for (const ev of events.slice(0, 8)) {
    const isReminder =
      ev.ruleId?.includes("meds") ||
      ev.ruleId?.includes("medicine") ||
      ev.actionType === "reminder" ||
      ev.title?.toLowerCase().includes("medication") ||
      ev.title?.toLowerCase().includes("medicine");
    const type: MomentType = isReminder ? "reminded" : "acted";

    // For "acted" events, prefer showing the rule + device context
    let detail = ev.actionTaken ?? ev.description ?? "";
    if (ev.ruleId && !detail.includes(ev.ruleId)) {
      detail = detail ? `${detail} · Rule: ${ev.ruleId}` : `Rule: ${ev.ruleId}`;
    }
    if (ev.targetMembers && ev.targetMembers.length > 0) {
      detail = detail
        ? `${detail} · Notified: ${ev.targetMembers.join(", ")}`
        : `Notified: ${ev.targetMembers.join(", ")}`;
    }

    moments.push({
      id: `evt_${ev.id}`,
      type,
      time: ev.timestamp,
      headline: ev.title,
      detail,
      route: ev.route,
    });
  }

  // Reasoning decisions — ALL routes, not just BEDROCK
  for (const r of reasoning.slice(0, 6)) {
    const type: MomentType = r.route === "BEDROCK" ? "reasoned" : "acted";

    let detail = "";
    if (r.route === "BEDROCK") {
      detail = r.suggestedAction
        ? r.suggestedAction
        : `Complexity score: ${r.complexityScore ?? "–"}. AI reasoning applied.`;
    } else if (r.route === "RULE_ENGINE") {
      const rulePart = r.ruleMatched ? `Rule: ${r.ruleMatched}` : "";
      const stagePart = r.stageDecided ? `Stage ${r.stageDecided}` : "";
      const latencyPart = r.latencyMs ? `${r.latencyMs}ms` : "";
      detail = [rulePart, stagePart, latencyPart].filter(Boolean).join(" · ");
    } else {
      detail = r.suggestedAction ?? "Pattern applied";
    }

    moments.push({
      id: `rsn_${r.id}`,
      type,
      time: r.timestamp,
      headline: r.observation,
      detail,
      route: r.route,
    });
  }

  // Sort by time tier:
  //   Tier 0 — live events & reasoning (have HH:MM AM/PM or HH:MM) → sort by time descending newest first
  //   Tier 1 — learned items (relative strings like "Today", "28 days ago") → sort last as background context
  moments.sort((a, b) => {
    const parseTime = (t: string): { tier: number; minutes: number } => {
      // HH:MM AM/PM format
      const ampm = t.match(/(\d+):(\d+)\s*(AM|PM)/i);
      if (ampm) {
        let h = parseInt(ampm[1]);
        const min = parseInt(ampm[2]);
        if (ampm[3].toUpperCase() === "PM" && h !== 12) h += 12;
        if (ampm[3].toUpperCase() === "AM" && h === 12) h = 0;
        return { tier: 0, minutes: h * 60 + min };
      }
      // HH:MM 24h format (no AM/PM)
      const h24 = t.match(/^(\d{1,2}):(\d{2})$/);
      if (h24) {
        return { tier: 0, minutes: parseInt(h24[1]) * 60 + parseInt(h24[2]) };
      }
      // Relative text ("Today", "28 days ago", etc.) → background tier
      return { tier: 1, minutes: 0 };
    };
    const pa = parseTime(a.time);
    const pb = parseTime(b.time);
    if (pa.tier !== pb.tier) return pa.tier - pb.tier;
    // Within the same tier: sort newest first (descending)
    return pb.minutes - pa.minutes;
  });

  // Deduplicate by headline (events and reasoning may overlap)
  const seen = new Set<string>();
  return moments.filter((m) => {
    const key = m.headline.slice(0, 40);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 12);
}

// ─── Component ────────────────────────────────────────────────────────────────

interface HouseholdIntelligenceTimelineProps {
  learnedItems: LearnedItem[];
  events: MockActivity[];
  reasoning: ReasoningEntry[];
}

export function HouseholdIntelligenceTimeline({
  learnedItems,
  events,
  reasoning,
}: HouseholdIntelligenceTimelineProps) {
  const timeline = buildTimeline(learnedItems, events, reasoning);

  return (
    <div className="bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[#f3f4f6]">
        <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-[#9ca3af] font-semibold">Intelligence timeline</p>
        <p className="text-[12px] text-[#6b7280] mt-0.5">What SAATHI learned, did, and understood today</p>
      </div>

      <div className="px-5 py-4">
        {timeline.length === 0 && (
          <p className="text-[13px] text-[#9ca3af] py-4 text-center">No activity yet — fire a simulation to see the household come alive.</p>
        )}

        <div className="relative">
          {/* Vertical line */}
          {timeline.length > 0 && (
            <div className="absolute left-[7px] top-2 bottom-2 w-px bg-[#f3f4f6]" />
          )}

          <div className="flex flex-col gap-0">
            {timeline.map((moment, i) => {
              const cfg = MOMENT_CONFIG[moment.type];
              const isLast = i === timeline.length - 1;

              return (
                <motion.div
                  key={moment.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06, duration: 0.3 }}
                  className={`flex gap-3 ${isLast ? "" : "pb-4"}`}
                >
                  {/* Dot */}
                  <div className="flex flex-col items-center shrink-0 z-10" style={{ width: 16 }}>
                    <span
                      className="w-3.5 h-3.5 rounded-full border-2 border-white mt-0.5 shrink-0"
                      style={{ backgroundColor: cfg.dotColor }}
                    />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0 pb-1">
                    {/* Time + verb */}
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-mono text-[10px] text-[#9ca3af] shrink-0">{moment.time}</span>
                      <span
                        className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded shrink-0"
                        style={{ color: cfg.color, backgroundColor: cfg.bg }}
                      >
                        {cfg.verb}
                      </span>
                      {moment.member && (
                        <span className="text-[10px] text-[#9ca3af] truncate">{moment.member}</span>
                      )}
                    </div>

                    {/* Headline */}
                    <p className="text-[13px] font-semibold text-[#111827] leading-tight mb-0.5">{moment.headline}</p>

                    {/* Detail */}
                    {moment.detail && (
                      <p className="text-[12px] text-[#6b7280] leading-relaxed">{moment.detail}</p>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
