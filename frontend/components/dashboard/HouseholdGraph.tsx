"use client";

/**
 * HouseholdGraph — Phase 9
 *
 * Interactive force-directed graph built on react-force-graph-2d.
 * Click any node to zoom into its local neighbourhood.
 * Escape or click background to reset.
 *
 * Node types and colours:
 *   member          — large, age-coloured ring
 *   health_condition — red
 *   medication      — purple
 *   routine         — green
 *   device          — blue
 *   life_event      — gold
 *
 * Edge types: HAS_CONDITION, TAKES, FOLLOWS, PRIMARY_USER_OF,
 *             DIRECTLY_AFFECTS, CONFLICTS_WITH, LOCATED_IN
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { BackendFullGraphResponse, BackendGraphNode, BackendGraphEdge, HouseholdGraph as HouseholdGraphLegacy } from "@/services/dashboard.service";

// ── dynamic import avoids SSR issues with canvas APIs ──────────────────────
const ForceGraph2D = dynamic(
  () => import("react-force-graph-2d"),
  { ssr: false }
);

// ─── Colours ───────────────────────────────────────────────────────────────────

const NODE_COLORS: Record<string, string> = {
  member:           "#111827",
  health_condition: "#ef4444",
  medication:       "#8b5cf6",
  routine:          "#10b981",
  device:           "#0ea5e9",
  life_event:       "#f59e0b",
  household:        "#6b7280",
  rule:             "#ec4899",
  pattern:          "#a78bfa",
};

const AGE_COLORS: Record<string, string> = {
  senior: "#8b5cf6",
  adult:  "#374151",
  teen:   "#0ea5e9",
  child:  "#10b981",
};

const EDGE_COLORS: Record<string, string> = {
  HAS_CONDITION:    "#ef4444",
  TAKES:            "#8b5cf6",
  FOLLOWS:          "#10b981",
  PRIMARY_USER_OF:  "#0ea5e9",
  DIRECTLY_AFFECTS: "#f59e0b",
  CONFLICTS_WITH:   "#f97316",
  LOCATED_IN:       "#d1d5db",
};

const NODE_SIZE: Record<string, number> = {
  member:           8,
  health_condition: 4,
  medication:       4,
  routine:          3.5,
  device:           4,
  life_event:       6,
  household:        2,
};

// ─── Types ─────────────────────────────────────────────────────────────────────

interface FGNode {
  id: string;
  label: string;
  type: string;
  role?: string;
  age?: number;
  severity?: string;
  critical?: boolean;
  time_window?: string;
  schedule?: string;
  description?: string;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
  __visible?: boolean;
}

interface FGLink {
  source: string;
  target: string;
  type: string;
  reason?: string;
}

interface GraphData {
  nodes: FGNode[];
  links: FGLink[];
}

// ─── Legend ────────────────────────────────────────────────────────────────────

const LEGEND = [
  { color: "#111827", label: "Member" },
  { color: "#ef4444", label: "Condition" },
  { color: "#8b5cf6", label: "Medication" },
  { color: "#10b981", label: "Routine" },
  { color: "#0ea5e9", label: "Device" },
  { color: "#f59e0b", label: "Life event" },
];

// ─── Build graph data from backend response ─────────────────────────────────

function buildGraphData(
  fullGraph: BackendFullGraphResponse | null,
  legacy: HouseholdGraphLegacy,
): GraphData {
  if (!fullGraph || fullGraph.nodes.length === 0) {
    // Fallback: render legacy member ring as flat nodes
    return {
      nodes: legacy.members.map((m) => ({
        id: m.id,
        label: m.name,
        type: "member",
        role: m.role,
        age: m.age,
      })),
      links: [],
    };
  }

  // Filter out household meta node and room nodes (no node_type or type "household")
  const nodes: FGNode[] = fullGraph.nodes
    .filter((n) => n.node_type && n.node_type !== "household")
    .map((n): FGNode => ({
      id: n.id,
      label: n.name ?? n.condition ?? n.description?.slice(0, 32) ?? n.id.replace(/_/g, " "),
      type: n.node_type,
      role: n.role,
      age: n.age,
      severity: n.severity,
      critical: n.critical,
      time_window: n.time_window,
      schedule: n.schedule,
      description: n.description,
    }));

  // Only keep edges where both endpoints are in our node set
  const nodeIds = new Set(nodes.map((n) => n.id));
  const links: FGLink[] = fullGraph.edges
    .filter((e) => e.type !== "LOCATED_IN") // hide room edges — visual clutter
    .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to))
    .map((e): FGLink => ({
      source: e.from,
      target: e.to,
      type: e.type,
      reason: e.reason,
    }));

  return { nodes, links };
}

// ─── Component ────────────────────────────────────────────────────────────────

interface HouseholdGraphProps {
  graph: HouseholdGraphLegacy;
  fullGraph?: BackendFullGraphResponse | null;
}

export function HouseholdGraph({ graph, fullGraph = null }: HouseholdGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(340);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ node: FGNode; x: number; y: number } | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const { nodes, links } = buildGraphData(fullGraph, graph);

  // Measure container width
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.floor(w));
    });
    ro.observe(containerRef.current);
    setWidth(containerRef.current.offsetWidth || 340);
    return () => ro.disconnect();
  }, []);

  // Visible nodes: if something selected, show only local neighbourhood
  const visibleNodes = selectedId
    ? (() => {
        const neighbourIds = new Set<string>([selectedId]);
        for (const l of links) {
          const src = typeof l.source === "object" ? (l.source as FGNode).id : l.source;
          const tgt = typeof l.target === "object" ? (l.target as FGNode).id : l.target;
          if (src === selectedId) neighbourIds.add(tgt);
          if (tgt === selectedId) neighbourIds.add(src);
        }
        return new Set(neighbourIds);
      })()
    : null;

  const filteredData: GraphData = {
    nodes: visibleNodes
      ? nodes.filter((n) => visibleNodes.has(n.id))
      : nodes,
    links: visibleNodes
      ? links.filter((l) => {
          const src = typeof l.source === "object" ? (l.source as FGNode).id : l.source;
          const tgt = typeof l.target === "object" ? (l.target as FGNode).id : l.target;
          return visibleNodes.has(src) && visibleNodes.has(tgt);
        })
      : links,
  };

  // Custom node painter
  const paintNode = useCallback((node: FGNode, ctx: CanvasRenderingContext2D, scale: number) => {
    const r = (NODE_SIZE[node.type] ?? 4);
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    const isSelected = node.id === selectedId;
    const isMember = node.type === "member";

    // Glow for selected
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, 2 * Math.PI);
      ctx.fillStyle = "rgba(139, 92, 246, 0.2)";
      ctx.fill();
    }

    // Node circle
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    const baseColor = isMember
      ? (node.role === "grandparent" ? AGE_COLORS.senior
        : node.role === "parent" ? AGE_COLORS.adult
        : node.age && node.age >= 13 ? AGE_COLORS.teen
        : AGE_COLORS.child)
      : (NODE_COLORS[node.type] ?? "#6b7280");

    if (isMember) {
      ctx.fillStyle = "white";
      ctx.fill();
      ctx.strokeStyle = baseColor;
      ctx.lineWidth = isSelected ? 2.5 : 1.5;
      ctx.stroke();
    } else {
      ctx.fillStyle = baseColor;
      ctx.globalAlpha = isSelected ? 1 : 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    // Critical/severity indicator ring
    if (node.critical || node.severity === "moderate" || node.severity === "high") {
      ctx.beginPath();
      ctx.arc(x, y, r + 2, 0, 2 * Math.PI);
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 0.8;
      ctx.setLineDash([2, 2]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Label (only when scaled up enough or is member)
    const minScale = isMember ? 0.3 : 1.0;
    if (scale > minScale) {
      const label = node.label.length > 18 ? node.label.slice(0, 16) + "…" : node.label;
      ctx.font = isMember
        ? `bold ${Math.max(10, 12 / scale)}px system-ui`
        : `${Math.max(8, 9 / scale)}px ui-monospace, monospace`;
      ctx.fillStyle = isMember ? baseColor : "#374151";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (isMember) {
        // Initial inside circle
        ctx.font = `bold ${r * 0.9}px system-ui`;
        ctx.fillStyle = baseColor;
        ctx.fillText(node.label[0]?.toUpperCase() ?? "?", x, y);
        // Name below
        ctx.font = `bold ${Math.max(9, 10 / scale)}px system-ui`;
        ctx.fillStyle = "#111827";
        ctx.fillText(label, x, y + r + 8 / scale);
        if (node.age) {
          ctx.font = `${Math.max(7, 8 / scale)}px ui-monospace`;
          ctx.fillStyle = "#9ca3af";
          ctx.fillText(String(node.age), x, y + r + 17 / scale);
        }
      } else {
        ctx.fillText(label, x, y + r + 7 / scale);
      }
    }
  }, [selectedId]);

// ─── Link painter
  const paintLink = useCallback((link: FGLink, ctx: CanvasRenderingContext2D) => {
    const color = EDGE_COLORS[link.type] ?? "#d1d5db";
    const src = typeof link.source === "object" ? link.source as FGNode : null;
    const tgt = typeof link.target === "object" ? link.target as FGNode : null;
    if (!src?.x || !src?.y || !tgt?.x || !tgt?.y) return;

    ctx.beginPath();
    ctx.moveTo(src.x, src.y);
    ctx.lineTo(tgt.x, tgt.y);
    ctx.strokeStyle = color;
    ctx.lineWidth = link.type === "CONFLICTS_WITH" ? 1.5 : 0.8;
    if (link.type === "CONFLICTS_WITH") ctx.setLineDash([3, 3]);
    else ctx.setLineDash([]);
    ctx.globalAlpha = 0.7;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
  }, []);

  const handleNodeClick = useCallback((node: FGNode) => {
    setSelectedId((prev) => prev === node.id ? null : node.id);
    setTooltip(null);
  }, []);

  const mousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const handleNodeHover = useCallback((node: FGNode | null) => {
    if (!node) { setTooltip(null); return; }
    // Use live mouse position tracked by the container's onMouseMove
    setTooltip({ node, x: mousePosRef.current.x, y: mousePosRef.current.y });
  }, []);

  const handleBackgroundClick = useCallback(() => {
    setSelectedId(null);
    setTooltip(null);
  }, []);

  const selectedNode = selectedId ? nodes.find((n) => n.id === selectedId) : null;

  return (
    <div className="w-full flex flex-col gap-0">
      {/* Graph stats header */}
      <div className="px-4 py-2 border-b border-[#f3f4f6] bg-white flex items-center gap-3">
        <span className="text-[11px] font-mono text-[#9ca3af]">
          {nodes.length} nodes
        </span>
        <span className="text-[10px] text-[#e5e7eb]">·</span>
        <span className="text-[11px] font-mono text-[#9ca3af]">
          {links.length} edges
        </span>
        {fullGraph && (
          <span className="ml-auto text-[10px] font-mono bg-[#f0fdf4] text-[#059669] px-1.5 py-0.5 rounded">
            Live graph
          </span>
        )}
      </div>
      {/* Graph canvas */}
      <div
        ref={containerRef}
        className="w-full relative"
        style={{ height: 380, background: "#fafafa", borderRadius: "0 0 0 0" }}
        onMouseMove={(e) => {
          const rect = containerRef.current?.getBoundingClientRect();
          if (rect) {
            const pos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
            mousePosRef.current = pos;
            setMousePos(pos);
          }
          // Update tooltip position if already open
          if (tooltip) {
            const rect2 = containerRef.current?.getBoundingClientRect();
            if (rect2) setTooltip((prev) => prev ? { ...prev, x: e.clientX - rect2.left, y: e.clientY - rect2.top } : null);
          }
        }}
      >
        {width > 0 && (
          <ForceGraph2D
            graphData={filteredData as { nodes: object[]; links: object[] }}
            width={width}
            height={380}
            backgroundColor="#fafafa"
            nodeId="id"
            linkSource="source"
            linkTarget="target"
            nodeCanvasObject={paintNode as (node: object, ctx: CanvasRenderingContext2D, scale: number) => void}
            nodeCanvasObjectMode={() => "replace"}
            linkCanvasObject={paintLink as (link: object, ctx: CanvasRenderingContext2D) => void}
            linkCanvasObjectMode={() => "replace"}
            nodeLabel={() => ""}
            onNodeClick={handleNodeClick as (node: object) => void}
            onNodeHover={handleNodeHover as (node: object | null, prevNode: object | null) => void}
            onBackgroundClick={handleBackgroundClick}
            cooldownTicks={80}
            nodeRelSize={4}
            d3AlphaDecay={0.04}
            d3VelocityDecay={0.3}
          />
        )}

        {/* Click-to-reset hint */}
        {selectedId && (
          <button
            onClick={handleBackgroundClick}
            className="absolute top-2 right-2 text-[10px] font-mono text-[#9ca3af] bg-white border border-[#e5e7eb] px-2 py-1 rounded-full hover:text-[#374151] transition-colors"
          >
            Show all ×
          </button>
        )}

        {/* Hover tooltip */}
        {tooltip && (
          <div
            className="absolute pointer-events-none bg-white border border-[#e5e7eb] rounded-xl shadow-sm px-3 py-2 max-w-[200px] z-10"
            style={{ left: tooltip.x + 12, top: tooltip.y - 10 }}
          >
            <p className="font-mono text-[9px] tracking-wide uppercase text-[#9ca3af] mb-0.5">{tooltip.node.type.replace(/_/g, " ")}</p>
            <p className="text-[12px] font-semibold text-[#111827]">{tooltip.node.label}</p>
            {tooltip.node.time_window && <p className="text-[11px] text-[#6b7280]">{tooltip.node.time_window}</p>}
            {tooltip.node.schedule && <p className="text-[11px] text-[#6b7280]">{tooltip.node.schedule}</p>}
          </div>
        )}
      </div>

      {/* Selected node detail panel */}
      {selectedNode && (
        <div className="border-t border-[#f3f4f6] px-4 py-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: NODE_COLORS[selectedNode.type] ?? "#6b7280" }}
            />
            <span className="font-mono text-[9px] uppercase tracking-wider text-[#9ca3af]">{selectedNode.type.replace(/_/g, " ")}</span>
          </div>
          <p className="text-[13px] font-semibold text-[#111827] mb-1">{selectedNode.label}</p>
          {selectedNode.description && (
            <p className="text-[12px] text-[#6b7280] mb-1">{selectedNode.description}</p>
          )}
          <div className="flex flex-wrap gap-2 mt-1.5">
            {selectedNode.time_window && (
              <span className="text-[11px] bg-[#f0fdf4] text-[#059669] px-2 py-0.5 rounded-full font-mono">{selectedNode.time_window}</span>
            )}
            {selectedNode.schedule && (
              <span className="text-[11px] bg-[#f5f3ff] text-[#7c3aed] px-2 py-0.5 rounded-full font-mono">{selectedNode.schedule}</span>
            )}
            {selectedNode.severity && (
              <span className="text-[11px] bg-[#fef2f2] text-[#dc2626] px-2 py-0.5 rounded-full font-mono">{selectedNode.severity}</span>
            )}
            {selectedNode.critical && (
              <span className="text-[11px] bg-[#fffbeb] text-[#d97706] px-2 py-0.5 rounded-full font-mono">Critical</span>
            )}
          </div>
          {/* Neighbours summary */}
          {visibleNodes && visibleNodes.size > 1 && (
            <p className="text-[11px] text-[#9ca3af] mt-2">
              {visibleNodes.size - 1} connected node{visibleNodes.size > 2 ? "s" : ""}
            </p>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="px-4 py-3 flex flex-wrap items-center gap-3 border-t border-[#f3f4f6] bg-white">
        {LEGEND.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-[#9ca3af]">{label}</span>
          </div>
        ))}
        <span className="text-[10px] text-[#c4b5fd] ml-auto">Tap node to explore</span>
      </div>
    </div>
  );
}
