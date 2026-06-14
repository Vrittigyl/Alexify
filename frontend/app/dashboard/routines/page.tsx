"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useDashboard } from "@/components/dashboard/DashboardProvider";
import { Clock, Check, X, Edit2, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { BACKEND_BASE } from "@/services/api.config";

type FilterTab = "All" | "Morning" | "Evening" | "Night" | "Weekend";

export default function RoutinesPage() {
  const { data } = useDashboard();
  const [filter, setFilter] = useState<FilterTab>("All");
  const [promotingId, setPromotingId] = useState<string | null>(null);

  if (!data) return null;

  const patterns = data.rawPatterns || [];

  const filteredPatterns = patterns.filter(p => {
    if (filter === "All") return true;
    // Simple mock filtering based on description or time_window
    const text = `${p.description} ${p.time_window}`.toLowerCase();
    if (filter === "Morning") return text.includes("morning") || text.includes("am");
    if (filter === "Evening") return text.includes("evening") || text.includes("pm");
    if (filter === "Night") return text.includes("night");
    if (filter === "Weekend") return text.includes("weekend") || text.includes("sunday") || text.includes("saturday");
    return true;
  });

  const handlePromote = async (patternId: string) => {
    setPromotingId(patternId);
    try {
      await fetch(`${BACKEND_BASE}/patterns/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pattern_id: patternId, priority: "medium" })
      });
      // the websocket will trigger a refresh in DashboardProvider
    } catch (e) {
      console.error(e);
    } finally {
      setPromotingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-2">
        <h2 className="text-[28px] font-bold text-[#111827]" style={{ fontFamily: "var(--font-space-grotesk)" }}>
          Household Routines
        </h2>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-2 sm:pb-0">
          {(["All", "Morning", "Evening", "Night", "Weekend"] as FilterTab[]).map(tab => (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-colors shrink-0 ${
                filter === tab ? "bg-[#111827] text-white" : "bg-white border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f9fafb]"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredPatterns.map(pattern => {
          const isPromoted = pattern.confidence_band === "PROMOTED";
          return (
            <motion.div
              key={pattern.pattern_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-2xl border border-[#e5e7eb] p-5 shadow-sm flex flex-col gap-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isPromoted ? "bg-emerald-100 text-emerald-600" : "bg-violet-100 text-violet-600"}`}>
                    <Clock size={16} />
                  </div>
                  <div>
                    <p className="text-[12px] font-mono font-semibold text-[#6b7280]">
                      {pattern.confidence_band}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[12px] font-bold text-[#111827]">{Math.round(pattern.confidence * 100)}%</span>
                  <span className="text-[10px] text-[#9ca3af] uppercase tracking-wider font-mono">Conf</span>
                </div>
              </div>

              <div>
                <h3 className="text-[15px] font-bold text-[#111827] leading-snug">{pattern.description || pattern.pattern_id}</h3>
                {pattern.time_window && (
                  <p className="text-[13px] text-[#6b7280] mt-1">Expected around {pattern.time_window}</p>
                )}
              </div>

              <div className="flex items-center gap-3 mt-auto pt-4 border-t border-[#f3f4f6]">
                {!isPromoted ? (
                  <>
                    <Button 
                      variant="primary" 
                      className="flex-1 justify-center py-1.5 text-[12px]" 
                      icon={<Check size={14} />}
                      onClick={() => handlePromote(pattern.pattern_id)}
                      disabled={promotingId === pattern.pattern_id}
                    >
                      {promotingId === pattern.pattern_id ? "Approving..." : "Approve"}
                    </Button>
                    <button className="p-2 text-[#9ca3af] hover:text-[#374151] hover:bg-[#f3f4f6] rounded-lg transition-colors">
                      <X size={16} />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="flex-1 flex items-center gap-1.5 text-[12px] font-medium text-emerald-600">
                      <PlayCircle size={14} /> Active Rule
                    </div>
                    <button className="p-2 text-[#9ca3af] hover:text-[#374151] hover:bg-[#f3f4f6] rounded-lg transition-colors">
                      <Edit2 size={14} />
                    </button>
                  </>
                )}
              </div>
            </motion.div>
          );
        })}
        
        {filteredPatterns.length === 0 && (
          <div className="col-span-full py-12 text-center border-2 border-dashed border-[#e5e7eb] rounded-2xl">
            <p className="text-[#6b7280] text-[14px]">No routines found for this filter.</p>
          </div>
        )}
      </div>
    </div>
  );
}
