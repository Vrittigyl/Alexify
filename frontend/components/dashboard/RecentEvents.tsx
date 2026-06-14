"use client";

/**
 * RecentEvents — Phase 9
 *
 * Rich event log that surfaces the full intelligence stored in each ActionLog
 * entry: route, source, action type, target members, device + command,
 * latency, channel, and delivery status.
 *
 * Severity colour coding:
 *   Safety / critical → red ring
 *   Health            → orange ring
 *   Routine/success   → purple ring
 *   Informational     → neutral
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { MockActivity } from "@/mocks/activity";
import type { BackendAction } from "@/services/dashboard.service";

// ─── Route badge ────────────────────────────────────────────────────────────

const ROUTE_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  RULE_ENGINE: { label: "Rule",    color: "#7c3aed", bg: "#f5f3ff" },
  BEDROCK:     { label: "AI",      color: "#0284c7", bg: "#e0f2fe" },
  SUPPRESS:    { label: "Skip",    color: "#9ca3af", bg: "#f3f4f6" },
  PATTERN:     { label: "Pattern", color: "#b45309", bg: "#fef9c3" },
};

const SEV_COLOR: Record<string, string> = {
  success:  "#10b981",
  warning:  "#f59e0b",
  critical: "#ef4444",
  info:     "#8b5cf6",
};

const ACTION_TYPE_ICON: Record<string, string> = {
  device_command: "⚡",
  notification:   "🔔",
  reminder:       "💊",
};

// ─── Derive action category for colour ring ─────────────────────────────────

function actionCategory(ev: MockActivity, raw?: BackendAction): "safety" | "health" | "routine" | "info" {
  if (ev.ruleId?.includes("safety") || ev.ruleId?.includes("tank") || ev.ruleId?.includes("whistle") || ev.ruleId?.includes("fridge")) return "safety";
  if (ev.ruleId?.includes("meds") || ev.ruleId?.includes("medicine") || ev.ruleId?.includes("health") || ev.ruleId?.includes("dadaji")) return "health";
  if (ev.severity === "success" || ev.severity === "warning") return "routine";
  return "info";
}

const CAT_RING: Record<string, string> = {
  safety:  "border-[#fca5a5] bg-[#fef2f2]",
  health:  "border-[#fdba74] bg-[#fff7ed]",
  routine: "border-[#c4b5fd] bg-[#f5f3ff]",
  info:    "border-[#e5e7eb] bg-white",
};

const CAT_DOT: Record<string, string> = {
  safety:  "#ef4444",
  health:  "#f97316",
  routine: "#8b5cf6",
  info:    "#9ca3af",
};

// ─── Single event row ────────────────────────────────────────────────────────

function EventRow({ ev }: { ev: MockActivity }) {
  const [expanded, setExpanded] = useState(false);
  const rs = ROUTE_STYLE[ev.route] ?? ROUTE_STYLE.SUPPRESS;
  const cat = actionCategory(ev);
  const typeIcon = ACTION_TYPE_ICON[ev.route === "RULE_ENGINE" || ev.route === "SUPPRESS" ? "device_command" : "notification"] ?? "⚡";

  return (
    <div
      className={`border rounded-xl overflow-hidden transition-all cursor-pointer ${CAT_RING[cat]}`}
      onClick={() => setExpanded((e) => !e)}
    >
      {/* Collapsed row */}
      <div className="px-4 py-3 flex items-start gap-3">
        <div className="flex items-center gap-2 shrink-0 pt-0.5">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: CAT_DOT[cat] }} />
          <span className="font-mono text-[10px] text-[#9ca3af] w-[52px] shrink-0">{ev.timestamp}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold text-[#111827] leading-tight">{ev.title}</span>
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold shrink-0"
              style={{ color: rs.color, backgroundColor: rs.bg }}
            >
              {rs.label}
            </span>
          </div>
          {!expanded && ev.actionTaken && (
            <p className="text-[11px] text-[#6b7280] mt-0.5 truncate">{ev.actionTaken}</p>
          )}
        </div>

        <span className="text-[10px] text-[#d1d5db] shrink-0 mt-0.5">{expanded ? "▲" : "▼"}</span>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 border-t border-[#f3f4f6] pt-2.5 flex flex-col gap-2">

              {/* Description */}
              {ev.description && (
                <p className="text-[12px] text-[#374151] leading-relaxed">{ev.description}</p>
              )}

              {/* Recipients — notification target members */}
              {ev.targetMembers && ev.targetMembers.length > 0 && (
                <div className="flex items-start gap-2">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0 pt-0.5">
                    {ev.actionType === "notification" || ev.actionType === "reminder" ? "Notified" : "Affected"}
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {ev.targetMembers.map((name) => (
                      <span key={name} className="text-[11px] bg-[#f5f3ff] text-[#7c3aed] px-1.5 py-0.5 rounded font-medium">
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Device command detail */}
              {ev.actionType === "device_command" && ev.deviceId && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Command</span>
                  <code className="text-[11px] bg-[#f0f9ff] text-[#0284c7] px-1.5 py-0.5 rounded font-mono">{ev.command ?? "—"}</code>
                  <span className="text-[11px] font-mono text-[#9ca3af]">on</span>
                  <code className="text-[11px] bg-[#f3f4f6] text-[#374151] px-1.5 py-0.5 rounded font-mono">
                    {ev.deviceId.replace("dev_", "").replace(/_001$/, "").replace(/_/g, " ")}
                  </code>
                  {ev.success !== undefined && (
                    <span className={`text-[11px] font-mono font-semibold ${ev.success ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                      {ev.success ? "✓ Success" : "✗ Failed"}
                    </span>
                  )}
                </div>
              )}

              {/* Channel */}
              {ev.channel && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Channel</span>
                  <span className="text-[11px] text-[#374151] capitalize">{ev.channel.replace(/_/g, " ")}</span>
                </div>
              )}

              {/* Latency */}
              {ev.latencyMs !== undefined && ev.latencyMs > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Latency</span>
                  <span className="font-mono text-[11px] text-[#374151]">{ev.latencyMs}ms</span>
                </div>
              )}

              {/* Notification delivery status */}
              {(ev.actionType === "notification" || ev.actionType === "reminder") && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Delivery</span>
                  {ev.success !== false ? (
                    <span className="text-[11px] font-mono font-semibold text-[#10b981] bg-[#f0fdf4] px-1.5 py-0.5 rounded">
                      ✓ Delivered
                    </span>
                  ) : (
                    <span className="text-[11px] font-mono font-semibold text-[#9ca3af] bg-[#f3f4f6] px-1.5 py-0.5 rounded">
                      ○ Pending
                    </span>
                  )}
                </div>
              )}

              {/* Rule ID */}
              {ev.ruleId && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Rule</span>
                  <code className="text-[11px] bg-[#f5f3ff] text-[#7c3aed] px-1.5 py-0.5 rounded font-mono">{ev.ruleId}</code>
                </div>
              )}

              {/* Route label */}
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Route</span>
                <span
                  className="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded"
                  style={{ color: rs.color, backgroundColor: rs.bg }}
                >
                  {ev.route === "RULE_ENGINE" ? "Rule Engine — deterministic" :
                   ev.route === "BEDROCK"     ? "Bedrock AI — context-aware" :
                   ev.route === "PATTERN"     ? "Promoted pattern — learned" :
                   "Suppressed — below threshold"}
                </span>
              </div>

              {/* Severity */}
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-[#9ca3af] shrink-0">Category</span>
                <span className="text-[11px] text-[#374151] capitalize">{cat}</span>
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: SEV_COLOR[ev.severity] }} />
                <span className="text-[11px] text-[#9ca3af] capitalize">{ev.severity}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function RecentEvents({ events }: { events: MockActivity[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? events : events.slice(0, 6);

  // Route breakdown summary
  const counts = events.reduce(
    (acc, ev) => { acc[ev.route] = (acc[ev.route] ?? 0) + 1; return acc; },
    {} as Record<string, number>
  );

  return (
    <div className="bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-[#f3f4f6] flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-[#9ca3af] font-semibold">Recent events</p>
          {events.length > 0 && (
            <div className="flex items-center gap-3 mt-1">
              {Object.entries(counts).map(([route, n]) => {
                const rs = ROUTE_STYLE[route] ?? ROUTE_STYLE.SUPPRESS;
                return (
                  <span key={route} className="text-[11px] font-mono" style={{ color: rs.color }}>
                    {n} {rs.label}
                  </span>
                );
              })}
            </div>
          )}
        </div>
        <span className="font-mono text-[10px] text-[#9ca3af]">{events.length} total</span>
      </div>

      {/* Event list */}
      <div className="px-3 py-3 flex flex-col gap-2">
        {visible.length === 0 && (
          <p className="text-[13px] text-[#9ca3af] text-center py-6">No events yet — fire a simulation to start.</p>
        )}
        {visible.map((ev) => (
          <EventRow key={ev.id} ev={ev} />
        ))}
      </div>

      {/* Show more */}
      {events.length > 6 && (
        <div className="px-5 py-3 border-t border-[#f3f4f6]">
          <button
            className="text-[12px] text-[#8b5cf6] font-semibold hover:underline"
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll ? "Show less ↑" : `Show all ${events.length} events ↓`}
          </button>
        </div>
      )}
    </div>
  );
}
