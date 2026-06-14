"use client";

import { useEffect, useState, useCallback } from "react";
import { BACKEND_BASE, DEFAULT_HOUSEHOLD_ID, type ProbeResult } from "@/services/api.config";
import { householdService } from "@/services/household.service";
import { patternService } from "@/services/pattern.service";
import { ruleService } from "@/services/rule.service";
import { eventService } from "@/services/event.service";
import { reasoningService } from "@/services/reasoning.service";

// ─── Types ────────────────────────────────────────────────────────────────────

interface EndpointResult {
  label: string;
  method: "GET" | "POST";
  url: string;
  status: "pending" | "ok" | "error";
  latencyMs?: number;
  data?: unknown;
  error?: string;
}

// ─── Endpoint manifest — every route from main.py docstring ───────────────────

const ENDPOINTS = [
  // System
  { group: "System",    label: "Health",               method: "GET"  as const, url: `${BACKEND_BASE}/health` },
  // Graph
  { group: "Graph",     label: "Get Graph",            method: "GET"  as const, url: `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}` },
  { group: "Graph",     label: "Get Members",          method: "GET"  as const, url: `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}/members` },
  { group: "Graph",     label: "Get Devices",          method: "GET"  as const, url: `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}/devices` },
  // Rules
  { group: "Rules",     label: "List Rules",           method: "GET"  as const, url: `${BACKEND_BASE}/rules` },
  // Patterns
  { group: "Patterns",  label: "List Patterns",        method: "GET"  as const, url: `${BACKEND_BASE}/patterns` },
  // Metrics
  { group: "Metrics",   label: "Dashboard Metrics",    method: "GET"  as const, url: `${BACKEND_BASE}/metrics` },
  { group: "Metrics",   label: "Circuit Breaker",      method: "GET"  as const, url: `${BACKEND_BASE}/metrics/circuit-breaker` },
  // RTE
  { group: "Reasoning", label: "RTE Decision (probe)", method: "GET"  as const, url: `${BACKEND_BASE}/rte/decision/__probe__` },
  // Simulate — POST-only, shown but not auto-triggered
  { group: "Simulate",  label: "Simulate: water_tank_full",            method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/water_tank_full` },
  { group: "Simulate",  label: "Simulate: pressure_cooker_5_whistles", method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/pressure_cooker_5_whistles` },
  { group: "Simulate",  label: "Simulate: dadaji_medicine",            method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/dadaji_medicine` },
  { group: "Simulate",  label: "Simulate: guest_arrival",              method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/guest_arrival` },
  { group: "Simulate",  label: "Simulate: fridge_door_open",           method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/fridge_door_open` },
  { group: "Simulate",  label: "Simulate: board_exam",                 method: "POST" as const, url: `${BACKEND_BASE}/simulate/event/board_exam` },
  // Admin — POST-only, shown but not auto-triggered
  { group: "Admin",     label: "Seed Database",        method: "POST" as const, url: `${BACKEND_BASE}/admin/seed` },
  // Events
  { group: "Events",    label: "Ingest Event (POST)",  method: "POST" as const, url: `${BACKEND_BASE}/events/ingest` },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status, latencyMs }: { status: EndpointResult["status"]; latencyMs?: number }) {
  if (status === "pending") return <span className="font-mono text-[11px] text-[#9ca3af]">probing…</span>;
  if (status === "ok") {
    return (
      <span className="flex items-center gap-1.5">
        <span className="text-[#10b981] font-mono text-[11px] font-bold">✓ OK</span>
        {latencyMs !== undefined && <span className="font-mono text-[10px] text-[#9ca3af]">{latencyMs}ms</span>}
      </span>
    );
  }
  return <span className="text-[#ef4444] font-mono text-[11px] font-bold">✗ Error</span>;
}

function JsonBlock({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="font-mono text-[10px] text-[#8b5cf6] hover:underline"
      >
        {open ? "▾ hide response" : "▸ show response"}
      </button>
      {open && (
        <pre className="mt-1.5 p-3 bg-[#0f0f0f] text-[#e2e8f0] rounded-xl text-[11px] leading-relaxed overflow-auto max-h-[300px]">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function BackendDebugPage() {
  const [results, setResults] = useState<Record<string, EndpointResult>>({});
  const [probing, setProbing] = useState(false);
  const [lastProbed, setLastProbed] = useState<string | null>(null);

  // Detailed probe results from services
  const [detailedResults, setDetailedResults] = useState<{
    health?: ProbeResult;
    graph?: ProbeResult;
    members?: ProbeResult;
    devices?: ProbeResult;
    rules?: ProbeResult;
    patterns?: ProbeResult;
    metrics?: ProbeResult;
    circuitBreaker?: ProbeResult;
    rte?: ProbeResult;
  }>({});

  function setResult(label: string, partial: Partial<EndpointResult>) {
    setResults((prev) => ({ ...prev, [label]: { ...prev[label], ...partial } as EndpointResult }));
  }

  const runProbes = useCallback(async () => {
    setProbing(true);

    // Initialise all as pending
    const initial: Record<string, EndpointResult> = {};
    ENDPOINTS.forEach((ep) => {
      initial[ep.label] = { label: ep.label, method: ep.method, url: ep.url, status: "pending" };
    });
    setResults(initial);

    // ── GET endpoints via service layer ──────────────────────────────────────
    const [health, graph, members, devices, rules, patterns, metrics, cb] = await Promise.all([
      householdService.getHealth(),
      householdService.getGraph(),
      householdService.getMembers(),
      householdService.getDevices(),
      ruleService.getRules(),
      patternService.getPatterns(),
      eventService.getMetrics(),
      eventService.getCircuitBreaker(),
    ]);

    // RTE probe (404 = reachable)
    const rteProbe = await reasoningService.probeEndpoints();
    const rteResult = rteProbe["rte_decision"];

    setDetailedResults({ health, graph, members, devices, rules, patterns, metrics, circuitBreaker: cb, rte: rteResult });

    function toResult(label: string, url: string, method: "GET" | "POST", r: ProbeResult): EndpointResult {
      return { label, method, url, status: r.status, latencyMs: r.latencyMs, data: r.data, error: r.error };
    }

    setResults((prev) => ({
      ...prev,
      "Health": toResult("Health", `${BACKEND_BASE}/health`, "GET", health),
      "Get Graph": toResult("Get Graph", `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}`, "GET", graph),
      "Get Members": toResult("Get Members", `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}/members`, "GET", members),
      "Get Devices": toResult("Get Devices", `${BACKEND_BASE}/graph/${DEFAULT_HOUSEHOLD_ID}/devices`, "GET", devices),
      "List Rules": toResult("List Rules", `${BACKEND_BASE}/rules`, "GET", rules),
      "List Patterns": toResult("List Patterns", `${BACKEND_BASE}/patterns`, "GET", patterns),
      "Dashboard Metrics": toResult("Dashboard Metrics", `${BACKEND_BASE}/metrics`, "GET", metrics),
      "Circuit Breaker": toResult("Circuit Breaker", `${BACKEND_BASE}/metrics/circuit-breaker`, "GET", cb),
      "RTE Decision (probe)": toResult("RTE Decision (probe)", `${BACKEND_BASE}/rte/decision/__probe__`, "GET", rteResult),
      // POST endpoints — mark as known but not auto-fired
      ...Object.fromEntries(
        ENDPOINTS.filter((e) => e.method === "POST").map((e) => [
          e.label,
          { label: e.label, method: e.method, url: e.url, status: "pending" as const, data: null, error: "Not auto-fired — POST endpoint" },
        ])
      ),
    }));

    setLastProbed(new Date().toLocaleTimeString());
    setProbing(false);
  }, []);

  useEffect(() => {
    runProbes();
  }, [runProbes]);

  // Group results
  const groups = Array.from(new Set(ENDPOINTS.map((e) => e.group)));

  const okCount = Object.values(results).filter((r) => r.status === "ok").length;
  const errCount = Object.values(results).filter((r) => r.status === "error").length;
  const pendCount = Object.values(results).filter((r) => r.status === "pending").length;

  const getCount = ENDPOINTS.filter((e) => e.method === "GET").length;
  const postCount = ENDPOINTS.filter((e) => e.method === "POST").length;

  return (
    <div className="min-h-screen bg-[#faf7f3]">
      {/* Header */}
      <header className="border-b border-[#e5e7eb] bg-[#faf7f3] px-6 py-4 flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#9ca3af] mb-0.5">SAATHI · Phase 5</p>
          <h1 className="text-[18px] font-bold text-[#111827]" style={{ fontFamily: "var(--font-space-grotesk)" }}>
            Backend API Inventory
          </h1>
          <p className="text-[12px] text-[#6b7280] mt-0.5">
            {BACKEND_BASE} · {ENDPOINTS.length} endpoints documented
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastProbed && (
            <span className="font-mono text-[11px] text-[#9ca3af]">Last probed: {lastProbed}</span>
          )}
          <button
            onClick={runProbes}
            disabled={probing}
            className="px-4 py-2 bg-[#111827] text-white text-[12px] font-semibold rounded-xl hover:bg-[#374151] transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-mono"
          >
            {probing ? "Probing…" : "↻ Re-probe"}
          </button>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-6">

        {/* Summary bar */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-8">
          {[
            { label: "Total endpoints",    value: ENDPOINTS.length, color: "#111827" },
            { label: "GET (auto-probed)",  value: getCount,         color: "#8b5cf6" },
            { label: "POST (not fired)",   value: postCount,        color: "#6b7280" },
            { label: "✓ Reachable",        value: okCount,          color: "#10b981" },
            { label: "✗ Errors",           value: errCount,         color: "#ef4444" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white border border-[#e5e7eb] rounded-xl px-4 py-3">
              <div className="text-[22px] font-bold" style={{ color }}>{value}</div>
              <div className="font-mono text-[10px] uppercase tracking-wide text-[#9ca3af] mt-0.5">{label}</div>
            </div>
          ))}
        </div>

        {/* Endpoint groups */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {groups.map((group) => {
            const groupEndpoints = ENDPOINTS.filter((e) => e.group === group);
            return (
              <div key={group} className="bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#f3f4f6] flex items-center justify-between">
                  <p className="font-mono text-[11px] tracking-[0.15em] uppercase text-[#9ca3af] font-semibold">{group}</p>
                  <div className="flex items-center gap-2">
                    {groupEndpoints.filter((e) => results[e.label]?.status === "ok").length > 0 && (
                      <span className="font-mono text-[10px] text-[#10b981]">
                        {groupEndpoints.filter((e) => results[e.label]?.status === "ok").length}/{groupEndpoints.length} ok
                      </span>
                    )}
                  </div>
                </div>
                <div className="divide-y divide-[#f9f9f9]">
                  {groupEndpoints.map((ep) => {
                    const result = results[ep.label];
                    return (
                      <div key={ep.label} className="px-5 py-3.5">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded font-bold ${ep.method === "GET" ? "bg-[#eff6ff] text-[#2563eb]" : "bg-[#f0fdf4] text-[#16a34a]"}`}>
                              {ep.method}
                            </span>
                            <span className="text-[13px] font-semibold text-[#111827]">{ep.label}</span>
                          </div>
                          <StatusBadge status={result?.status ?? "pending"} latencyMs={result?.latencyMs} />
                        </div>
                        <p className="font-mono text-[10px] text-[#9ca3af] mt-1 truncate">{ep.url}</p>
                        {result?.error && !result.error.startsWith("Not auto-fired") && (
                          <p className="text-[11px] text-[#ef4444] mt-1 font-mono">{result.error}</p>
                        )}
                        {result?.error?.startsWith("Not auto-fired") && (
                          <p className="text-[11px] text-[#9ca3af] mt-1 italic">POST — not auto-fired in discovery mode</p>
                        )}
                        {result?.status === "ok" && result.data !== undefined && ep.method === "GET" && (
                          <JsonBlock data={result.data as unknown} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Full API inventory dump */}
        <div className="mt-8 bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-[#f3f4f6]">
            <p className="font-mono text-[11px] tracking-[0.15em] uppercase text-[#9ca3af] font-semibold">Full endpoint inventory</p>
          </div>
          <div className="px-5 py-4">
            <pre className="bg-[#0f0f0f] text-[#e2e8f0] rounded-xl p-4 text-[11px] leading-relaxed overflow-auto max-h-[400px]">
              {JSON.stringify(
                {
                  backend_url: BACKEND_BASE,
                  household_id: DEFAULT_HOUSEHOLD_ID,
                  total_endpoints: ENDPOINTS.length,
                  probed_at: lastProbed,
                  inventory: ENDPOINTS.map((ep) => ({
                    group: ep.group,
                    label: ep.label,
                    method: ep.method,
                    url: ep.url,
                    status: results[ep.label]?.status ?? "pending",
                    latency_ms: results[ep.label]?.latencyMs ?? null,
                    error: results[ep.label]?.error ?? null,
                  })),
                },
                null,
                2,
              )}
            </pre>
          </div>
        </div>

        {/* Response shapes — detailed dumps */}
        <div className="mt-6 bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-[#f3f4f6]">
            <p className="font-mono text-[11px] tracking-[0.15em] uppercase text-[#9ca3af] font-semibold">Response shapes (GET endpoints only)</p>
          </div>
          <div className="px-5 py-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[
              { label: "GET /health",                              data: detailedResults.health?.data },
              { label: "GET /graph/{hh}",                         data: detailedResults.graph?.data },
              { label: "GET /graph/{hh}/members",                 data: detailedResults.members?.data },
              { label: "GET /graph/{hh}/devices",                 data: detailedResults.devices?.data },
              { label: "GET /rules",                              data: detailedResults.rules?.data },
              { label: "GET /patterns",                           data: detailedResults.patterns?.data },
              { label: "GET /metrics",                            data: detailedResults.metrics?.data },
              { label: "GET /metrics/circuit-breaker",            data: detailedResults.circuitBreaker?.data },
            ].map(({ label, data }) => (
              <div key={label}>
                <p className="font-mono text-[10px] tracking-wide text-[#8b5cf6] mb-1.5">{label}</p>
                {data ? (
                  <pre className="bg-[#0f0f0f] text-[#e2e8f0] rounded-xl p-3 text-[10px] leading-relaxed overflow-auto max-h-[200px]">
                    {JSON.stringify(data, null, 2)}
                  </pre>
                ) : (
                  <div className="bg-[#f9fafb] border border-[#f3f4f6] rounded-xl p-3">
                    <p className="font-mono text-[10px] text-[#d1d5db]">
                      {pendCount > 0 ? "Probing…" : "Backend unavailable or endpoint not found"}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Notes */}
        <div className="mt-6 bg-[#f5f3ff] border border-[#ddd6fe] rounded-2xl px-5 py-4">
          <p className="font-mono text-[10px] tracking-[0.15em] uppercase text-[#8b5cf6] mb-3">Discovery notes</p>
          <div className="flex flex-col gap-1.5">
            {[
              "POST endpoints are documented but NOT auto-fired. Trigger manually from this page or use the simulate service.",
              "GET /rte/decision/{event_id} exists per backend docs — probe uses sentinel event_id; 404 = endpoint reachable.",
              "No dedicated GET /reasoning endpoint exists. Reasoning data lives inside pipeline results + RTEAuditLog (DynamoDB).",
              "WebSocket: WS /ws/{household_id} — connect via browser DevTools for live event streaming.",
              "/admin/seed seeds DynamoDB with the Sharma family knowledge graph. Run once on fresh deploy.",
              "All GET endpoints are safe to probe repeatedly. POST endpoints mutate state — use with intention.",
            ].map((note, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-[#c4b5fd] text-[11px] shrink-0 mt-0.5">·</span>
                <span className="text-[12px] text-[#6b7280]">{note}</span>
              </div>
            ))}
          </div>
        </div>

      </main>
    </div>
  );
}
