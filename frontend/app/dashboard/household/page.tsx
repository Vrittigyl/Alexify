"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDashboard } from "@/components/dashboard/DashboardProvider";
import { User, Activity, Clock, Cpu, X } from "lucide-react";

export default function HouseholdPage() {
  const { data } = useDashboard();
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);

  if (!data) return null;

  const members = data.graph.members;
  const selectedMember = members.find((m) => m.id === selectedMemberId);

  return (
    <div className="flex flex-col gap-6 relative">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-[28px] font-bold text-[#111827]" style={{ fontFamily: "var(--font-space-grotesk)" }}>
          Household Members
        </h2>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {members.map((member) => (
          <motion.button
            key={member.id}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setSelectedMemberId(member.id)}
            className="flex flex-col items-center bg-white rounded-2xl border border-[#e5e7eb] p-6 text-center shadow-sm hover:shadow-md transition-all"
          >
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-[#f3e8ff] to-[#e9d5ff] flex items-center justify-center mb-4">
              <span className="text-2xl font-bold text-[#9333ea]">
                {member.name.charAt(0).toUpperCase()}
              </span>
            </div>
            <h3 className="text-[16px] font-bold text-[#111827]">{member.name}</h3>
            <p className="text-[13px] text-[#6b7280] capitalize mt-1">
              {member.role} • {member.ageGroup}
            </p>
          </motion.button>
        ))}
      </div>

      {/* Detail Drawer Sidebar overlay */}
      <AnimatePresence>
        {selectedMember && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedMemberId(null)}
              className="fixed inset-0 bg-black z-40"
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="fixed top-0 right-0 bottom-0 w-full max-w-md bg-white z-50 shadow-2xl border-l border-[#e5e7eb] flex flex-col"
            >
              <div className="flex items-center justify-between p-6 border-b border-[#f3f4f6]">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#f3e8ff] to-[#e9d5ff] flex items-center justify-center">
                    <span className="text-xl font-bold text-[#9333ea]">
                      {selectedMember.name.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-[#111827]">{selectedMember.name}</h3>
                    <p className="text-sm text-[#6b7280] capitalize">{selectedMember.role}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedMemberId(null)}
                  className="p-2 rounded-full hover:bg-[#f3f4f6] text-[#6b7280] transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-8">
                {/* Connections (Routines/Health/Devices) */}
                <div>
                  <h4 className="text-[12px] font-bold uppercase tracking-wider text-[#9ca3af] mb-4 flex items-center gap-2">
                    <Activity size={14} /> Profile Connections
                  </h4>
                  {selectedMember.connections.length > 0 ? (
                    <div className="flex flex-col gap-3">
                      {selectedMember.connections.map((conn, i) => (
                        <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-[#f9fafb] border border-[#f3f4f6]">
                          {conn.type === "health" && <Activity size={16} className="text-rose-500" />}
                          {conn.type === "routine" && <Clock size={16} className="text-blue-500" />}
                          {conn.type === "device" && <Cpu size={16} className="text-violet-500" />}
                          {conn.type === "event" && <User size={16} className="text-amber-500" />}
                          <div className="flex-1 min-w-0">
                            <p className="text-[14px] font-medium text-[#374151] truncate">{conn.label}</p>
                            <p className="text-[12px] text-[#9ca3af] capitalize">{conn.type}</p>
                          </div>
                          {conn.confidence && (
                            <span className="text-[11px] font-mono text-[#8b5cf6] bg-[#f5f3ff] px-2 py-0.5 rounded-full">
                              {Math.round(conn.confidence * 100)}%
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-[#9ca3af]">No specific patterns or connections discovered yet.</p>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
