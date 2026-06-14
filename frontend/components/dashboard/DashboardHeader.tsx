"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Sparkles, MapPin, Clock, Trash2 } from "lucide-react";
import { AnimatePresence } from "framer-motion";
import type { DashboardData } from "@/services/dashboard.service";
import { DeleteHouseholdModal } from "./DeleteHouseholdModal";

function useGreeting() {
  const h = new Date().getHours();

  if (h < 5) return "Good night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";

  return "Good evening";
}

export function DashboardHeader({
  data,
  wsConnected,
}: {
  data: DashboardData;
  wsConnected?: boolean;
}) {
  const greeting = useGreeting();
  const { intelligenceStats, household } = data;

  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const time = new Date().toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });

  return (
    <>
      <header className="sticky top-0 z-30 bg-[#faf7f3]/96 backdrop-blur-md border-b border-[#e5e7eb]">
        <div className="max-w-[1600px] mx-auto px-5 sm:px-8 h-[60px] flex items-center justify-between gap-6">
          {/* Left */}
          <div className="flex items-center gap-4 min-w-0">
            <Link
              href="/"
              className="shrink-0 text-[#9ca3af] hover:text-[#374151] transition-colors"
            >
              <ArrowLeft size={15} strokeWidth={2} />
            </Link>

            <div className="w-px h-4 bg-[#e5e7eb] shrink-0" />

            <div className="min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap leading-tight">
                <span
                  className="text-[15px] font-semibold text-[#111827]"
                  style={{ fontFamily: "var(--font-space-grotesk)" }}
                >
                  {greeting}, {household.familyName} Family.
                </span>

                <span className="text-[13px] text-[#6b7280] hidden sm:inline">
                  SAATHI observed {intelligenceStats.actionsToday} household
                  events today.
                  {intelligenceStats.patternsDetected > 0 && (
                    <>
                      {" "}
                      {intelligenceStats.patternsDetected} patterns currently
                      being learned.
                    </>
                  )}
                </span>
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-2 shrink-0">
            {/* City */}
            <div className="hidden sm:flex items-center gap-1.5 text-[12px] text-[#9ca3af]">
              <MapPin size={11} />
              <span>{household.city}</span>
            </div>

            {/* Members */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#e5e7eb] bg-white text-[11px] text-[#6b7280] font-mono">
              {household.memberCount} members
            </div>

            {/* Time */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#e5e7eb] bg-white text-[11px] text-[#6b7280] font-mono">
              <Clock size={10} />
              <span>{time}</span>
            </div>

            {/* Learning Badge */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#ede9fe] bg-[#f5f3ff]">
              <Sparkles size={10} className="text-[#8b5cf6]" />
              <span className="font-mono text-[11px] text-[#8b5cf6] font-semibold">
                {household.daysLearning}d learning
              </span>
            </div>

            {/* WebSocket Status */}
            {wsConnected !== undefined && (
              <div
                className="flex items-center gap-1 px-2 py-1 rounded-full border bg-white"
                style={{
                  borderColor: wsConnected ? "#d1fae5" : "#e5e7eb",
                }}
                title={
                  wsConnected
                    ? "Live WebSocket connected — dashboard updates automatically"
                    : "WebSocket disconnected — polling mode"
                }
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    wsConnected
                      ? "bg-[#10b981] animate-pulse"
                      : "bg-[#d1d5db]"
                  }`}
                />
                <span className="font-mono text-[10px] text-[#9ca3af]">
                  {wsConnected ? "Live" : "Polling"}
                </span>
              </div>
            )}

            {/* Data Source */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-full border border-[#e5e7eb] bg-white">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  data.source === "backend"
                    ? "bg-[#10b981]"
                    : "bg-[#f59e0b]"
                } animate-pulse`}
              />
              <span className="font-mono text-[10px] text-[#9ca3af]">
                {data.source === "backend" ? "Backend" : "Demo"}
              </span>
            </div>

            {/* Delete Household */}
            <button
              onClick={() => setShowDeleteModal(true)}
              className="w-8 h-8 rounded-lg border border-[#e5e7eb] bg-white flex items-center justify-center text-[#9ca3af] hover:text-[#ef4444] hover:border-[#fca5a5] hover:bg-[#fef2f2] transition-colors"
              title="Delete this household and start over"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {showDeleteModal && (
          <DeleteHouseholdModal
            householdId={household.id}
            familyName={household.familyName}
            onClose={() => setShowDeleteModal(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
}