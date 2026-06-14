"use client";

/**
 * ReasoningFeed — Phase 9
 *
 * Structured reasoning cards. Each RTE decision is rendered as a
 * 5-step story: Observation → Decision → Context → Action → Outcome.
 *
 * Route-specific visual treatment:
 *   RULE_ENGINE — purple, deterministic, shows matched rule
 *   BEDROCK     — blue, AI-assisted, shows complexity score
 *   PATTERN     — amber, learned behaviour
 *   SUPPRESS    — grey, below threshold
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ReasoningEntry } from "@/services/dashboard.service";

// ─── Route config ─────────────────────────────────────────────────────────────

const ROUTE_CONFIG: Record<string, {
  label: string;
  shortLabel: string;
  color: string;
  bg: string;
  borderColor: string;
  description: string;
}> = {
  RULE_ENGINE: {
    label: "Rule Engine",
    shortLabel: "Rule",
    color: "#7c3aed",
    bg: "#f5f3ff",
    borderColor: "#ede9fe",
    description: "Deterministic — matched a household rule",
  },
  BEDROCK: {
    label: "Bedrock AI",
    shortLabel: "AI",
    color: "#0284c7",
    bg: "#e0f2fe",
    borderColor: "#bae6fd",
    description: "Context-aware — AI reasoning required",
  },
  PATTERN: {
    label: "Learned Pattern",
    shortLabel: "Pattern",
    color: "#b45309",
    bg: "#fef9c3",
    borderColor: "#fde68a",
    description: "Behaviour-based — promoted from observations",
  },
};

// ─── Parse reasoning text into structured steps ───────────────────────────────

interface ReasoningSteps {
  observation: string;
  decision: string;
  context: string[];
  actions: string[];
  outcome: string;
  latency?: string;
  ruleId?: string;
  complexityScore?: number;
  stage?: number;
}

function parseReasoningEntry(entry: ReasoningEntry): ReasoningSteps {
  const text = entry.reasoning;

  // Extract latency if present (e.g. "1969ms")
  const latencyMatch = text.match(/(\d+(?:\.\d+)?)\s*ms/);
  const latency = latencyMatch ? `${Math.round(parseFloat(latencyMatch[1]))}ms` : undefined;

  // Extract rule id
  const ruleMatch = text.match(/`([^`]+)`|rule\s+(\w+)/i);
  const ruleId = ruleMatch ? (ruleMatch[1] ?? ruleMatch[2]) : undefined;

  // Extract stage
  const stageMatch = text.match(/stage\s+(\d)/i);
  const stage = stageMatch ? parseInt(stageMatch[1]) : undefined;

  // Extract complexity score
  const scoreMatch = text.match(/score\s+(\d+)/i);
  const complexityScore = scoreMatch ? parseInt(scoreMatch[1]) : undefined;

  // Build context bullets from REAL structured data only — no fabrication
  const context: string[] = [];
  if (entry.route === "BEDROCK") {
    // Use real score breakdown keys as context factors
    if (entry.scoreBreakdown && Object.keys(entry.scoreBreakdown).length > 0) {
      Object.keys(entry.scoreBreakdown).forEach((k) =>
        context.push(`Factor: ${k.replace(/_/g, " ")} (+${entry.scoreBreakdown![k]})`)
      );
    }
    if (complexityScore) context.push(`Complexity score: ${complexityScore}`);
    if (context.length === 0) context.push("Multi-factor household context evaluated");
  } else if (entry.route === "RULE_ENGINE") {
    const stageText = stage === 1 ? "Stage 1 — direct rule registry match" : `Stage ${stage ?? 2} — promoted pattern match`;
    context.push(stageText);
    if (entry.ruleMatched) context.push(`Matched rule: ${entry.ruleMatched}`);
    if (entry.patternMatched) context.push(`Promoted pattern: ${entry.patternMatched}`);
  } else {
    // PATTERN route
    if (entry.patternMatched) context.push(`Pattern: ${entry.patternMatched}`);
    else context.push("Observation history and pattern confidence evaluated");
  }

  // Build action bullets
  const actions: string[] = [];
  if (entry.suggestedAction) {
    // Split on ·, ✓, or newline
    entry.suggestedAction
      .split(/[·✓\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((a) => actions.push(a));
  }
  if (actions.length === 0) {
    actions.push(
      entry.route === "RULE_ENGINE" ? "Rule dispatched action" :
      entry.route === "BEDROCK"     ? "AI planned multi-step response" :
      "Pattern reinforced"
    );
  }

  // Outcome
    const outcome = latency
    ? `Completed in ${latency}`
    : (entry.route as string) === "SUPPRESS"
    ? "Below complexity threshold — no action taken"
    : "Dispatched successfully";

  // Decision text
  const decision =
    entry.route === "RULE_ENGINE" ? `${ROUTE_CONFIG.RULE_ENGINE.description}${stage ? ` (Stage ${stage})` : ""}` :
    entry.route === "BEDROCK"     ? `${ROUTE_CONFIG.BEDROCK.description}${complexityScore ? ` · Score ${complexityScore}` : ""}` :
    ROUTE_CONFIG.PATTERN?.description ?? "Pattern matched";

  return {
    observation: entry.observation,
    decision,
    context,
    actions,
    outcome,
    latency,
    ruleId,
    complexityScore,
    stage,
  };
}

// ─── Single card ─────────────────────────────────────────────────────────────

function ReasoningCard({ entry, index }: { entry: ReasoningEntry; index: number }) {
  const [expanded, setExpanded] = useState(index === 0); // first card open by default
  const cfg = ROUTE_CONFIG[entry.route] ?? ROUTE_CONFIG.RULE_ENGINE;
  const steps = parseReasoningEntry(entry);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: cfg.borderColor }}
    >
      {/* Header — always visible */}
      <button
        className="w-full text-left px-4 py-3 flex items-start justify-between gap-3 hover:bg-[#fafafa] transition-colors"
        style={{ backgroundColor: index === 0 && !expanded ? cfg.bg : "white" }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold shrink-0"
              style={{ color: cfg.color, backgroundColor: cfg.bg }}
            >
              {cfg.shortLabel}
            </span>
            <span className="text-[12px] font-semibold text-[#111827] leading-tight">{entry.observation}</span>
          </div>
          {!expanded && (
            <p className="text-[11px] text-[#9ca3af] font-mono">{entry.timestamp}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-[10px]" style={{ color: cfg.color }}>{entry.confidence}%</span>
          <span className="text-[10px] text-[#d1d5db]">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Steps — collapsible */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 border-t flex flex-col gap-3" style={{ borderColor: cfg.borderColor }}>

              {/* Timestamp */}
              <p className="font-mono text-[10px] text-[#9ca3af] pt-2">{entry.timestamp}</p>

              {/* Step 1: Observation */}
              <Step
                label="Observation"
                color={cfg.color}
                content={<p className="text-[12px] text-[#374151]">{steps.observation}</p>}
              />

              {/* Step 2: Decision */}
              <Step
                label="Decision"
                color={cfg.color}
                content={
                  <div className="flex flex-col gap-1.5">
                    <p className="text-[12px] text-[#374151]">{steps.decision}</p>

                    {/* Rule ID chip */}
                    {(entry.ruleMatched ?? steps.ruleId) && (
                      <code className="text-[11px] bg-[#f5f3ff] text-[#7c3aed] px-1.5 py-0.5 rounded font-mono w-fit">
                        {entry.ruleMatched ?? steps.ruleId}
                      </code>
                    )}

                    {/* Pattern matched chip */}
                    {entry.patternMatched && (
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[10px] text-[#9ca3af]">Pattern</span>
                        <code className="text-[11px] bg-[#fef9c3] text-[#b45309] px-1.5 py-0.5 rounded font-mono">{entry.patternMatched}</code>
                      </div>
                    )}

                    {/* Structured score breakdown — only for BEDROCK */}
                    {entry.scoreBreakdown && Object.keys(entry.scoreBreakdown).length > 0 && (
                      <div className="mt-1">
                        <p className="font-mono text-[9px] uppercase tracking-wider text-[#9ca3af] mb-1.5">Complexity factors</p>
                        <div className="flex flex-col gap-1">
                          {Object.entries(entry.scoreBreakdown).map(([key, val]) => {
                            const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                            const maxVal = 100;
                            const pct = Math.min((val / maxVal) * 100, 100);
                            return (
                              <div key={key} className="flex items-center gap-2">
                                <span className="text-[11px] text-[#374151] w-32 shrink-0 capitalize">{label}</span>
                                <div className="flex-1 h-[3px] bg-[#e0f2fe] rounded-full overflow-hidden">
                                  <div
                                    className="h-full rounded-full"
                                    style={{ width: `${pct}%`, backgroundColor: cfg.color }}
                                  />
                                </div>
                                <span className="font-mono text-[11px] font-semibold w-8 text-right shrink-0" style={{ color: cfg.color }}>+{val}</span>
                              </div>
                            );
                          })}
                          {/* Total */}
                          <div className="flex items-center gap-2 border-t border-[#e0f2fe] pt-1 mt-0.5">
                            <span className="text-[11px] font-semibold text-[#374151] w-32 shrink-0">Total score</span>
                            <div className="flex-1" />
                            <span className="font-mono text-[12px] font-bold w-8 text-right shrink-0" style={{ color: cfg.color }}>
                              {entry.complexityScore ?? Object.values(entry.scoreBreakdown).reduce((a, b) => a + b, 0)}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Complexity bar for simple cases without breakdown */}
                    {!entry.scoreBreakdown && (entry.complexityScore ?? steps.complexityScore) && (
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="font-mono text-[10px] text-[#9ca3af]">Complexity</span>
                        <div className="flex-1 h-[3px] bg-[#e0f2fe] rounded-full overflow-hidden max-w-[80px]">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.min(((entry.complexityScore ?? steps.complexityScore ?? 0) / 200) * 100, 100)}%`,
                              backgroundColor: cfg.color
                            }}
                          />
                        </div>
                        <span className="font-mono text-[10px]" style={{ color: cfg.color }}>
                          {entry.complexityScore ?? steps.complexityScore}
                        </span>
                      </div>
                    )}

                    {/* Latency */}
                    {entry.latencyMs && entry.latencyMs > 0 && (
                      <span className="font-mono text-[11px] text-[#9ca3af]">{entry.latencyMs}ms</span>
                    )}
                  </div>
                }
              />

              {/* Step 3: Context */}
              <Step
                label="Context used"
                color={cfg.color}
                content={
                  <ul className="flex flex-col gap-1">
                    {steps.context.map((c, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="text-[#c4b5fd] mt-0.5 shrink-0">·</span>
                        <span className="text-[12px] text-[#374151]">{c}</span>
                      </li>
                    ))}
                  </ul>
                }
              />

              {/* Step 4: Actions */}
              <Step
                label="Actions"
                color={cfg.color}
                content={
                  <ul className="flex flex-col gap-1">
                    {steps.actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="text-[#10b981] mt-0.5 shrink-0 text-[11px]">✓</span>
                        <span className="text-[12px] text-[#374151]">{a}</span>
                      </li>
                    ))}
                  </ul>
                }
              />

              {/* Step 5: Outcome */}
              <Step
                label="Outcome"
                color={cfg.color}
                content={
                  <p className="text-[12px] font-medium" style={{ color: cfg.color }}>{steps.outcome}</p>
                }
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Step({ label, color, content }: { label: string; color: string; content: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center shrink-0" style={{ minWidth: 8 }}>
        <span className="w-2 h-2 rounded-full shrink-0 mt-1" style={{ backgroundColor: color, opacity: 0.5 }} />
        <span className="flex-1 w-px bg-[#f3f4f6] mt-1" />
      </div>
      <div className="flex-1 min-w-0 pb-1">
        <p className="font-mono text-[9px] uppercase tracking-wider text-[#9ca3af] mb-1">{label}</p>
        {content}
      </div>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ReasoningFeed({ entries }: { entries: ReasoningEntry[] }) {
  // Summary counters
  const routeCounts = entries.reduce(
    (acc, e) => { acc[e.route] = (acc[e.route] ?? 0) + 1; return acc; },
    {} as Record<string, number>
  );

  return (
    <div className="bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-[#f3f4f6]">
        <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-[#9ca3af] font-semibold mb-1">How SAATHI reasoned</p>
        <div className="flex items-center gap-3 flex-wrap">
          {Object.entries(routeCounts).map(([route, n]) => {
            const cfg = ROUTE_CONFIG[route];
            if (!cfg) return null;
            return (
              <div key={route} className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: cfg.color }} />
                <span className="text-[11px] font-mono" style={{ color: cfg.color }}>{n} {cfg.shortLabel}</span>
              </div>
            );
          })}
          {entries.length === 0 && (
            <span className="text-[11px] text-[#9ca3af]">No decisions yet — fire a simulation</span>
          )}
        </div>
      </div>

      {/* Cards */}
      <div className="px-3 py-3 flex flex-col gap-2">
        {entries.map((entry, i) => (
          <ReasoningCard key={entry.id} entry={entry} index={i} />
        ))}
      </div>
    </div>
  );
}
