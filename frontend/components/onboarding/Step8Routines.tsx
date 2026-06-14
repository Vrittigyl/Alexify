"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft, Clock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { onboardingStore, useOnboardingStore } from "@/lib/onboarding-store";

const ROUTINE_EMOJIS: Record<string, string> = {
  morning_tea: "☕",
  school_run: "🏫",
  medicine_morning: "💊",
  work_from_home: "💻",
  afternoon_nap: "😴",
  evening_walk: "🚶",
  dinner_together: "🍽️",
  medicine_night: "💊",
  movie_night: "🎬",
  prayer_time: "🙏",
};

const TIME_OPTIONS = [
  "Select time",
  "5:00 AM", "5:30 AM", "6:00 AM", "6:30 AM", "7:00 AM", "7:30 AM", 
  "8:00 AM", "8:30 AM", "9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", 
  "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM", "1:00 PM", "1:30 PM", 
  "2:00 PM", "2:30 PM", "3:00 PM", "3:30 PM", "4:00 PM", "4:30 PM", 
  "5:00 PM", "5:30 PM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM", 
  "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM", "10:00 PM", "10:30 PM", 
  "11:00 PM", "11:30 PM"
];

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as [number,number,number,number] } },
};
const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};

export function Step8Routines() {
  const state = useOnboardingStore();

  const selectedCount = state.routines.filter((r) => r.selected).length;

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-8">
      {/* Header */}
      <motion.div variants={item}>
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#f97316] to-[#ea580c] flex items-center justify-center mb-4">
          <Clock size={22} strokeWidth={1.8} className="text-white" />
        </div>
        <h2 className="text-[32px] font-bold text-[#111827] leading-tight mb-2" style={{ fontFamily: "var(--font-space-grotesk)" }}>
          Daily routines
        </h2>
        <p className="text-[15px] text-[#6b7280]">
          Select the routines that are part of your household&apos;s day. SAATHI will learn around them.
        </p>
      </motion.div>

      {/* Routine list */}
      <motion.div variants={item} className="flex flex-col gap-2">
        {state.routines.map((routine) => {
          const emoji = ROUTINE_EMOJIS[routine.id] ?? "⏰";
          return (
            <motion.button
              key={routine.id}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => onboardingStore.toggleRoutine(routine.id)}
              className={`w-full flex items-center gap-4 p-4 rounded-2xl border-2 text-left transition-all duration-200 ${
                routine.selected
                  ? "border-[#f97316] bg-gradient-to-r from-[#fff7ed] to-[#ffedd5]"
                  : "border-[#e5e7eb] bg-white hover:border-[#fed7aa]"
              }`}
            >
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0 transition-all ${
                  routine.selected ? "bg-[#f97316]" : "bg-[#f3f4f6]"
                }`}
              >
                {routine.selected ? (
                  <svg width="14" height="11" viewBox="0 0 14 11" fill="none">
                    <path d="M1 5.5L5 9.5L13 1.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  <span>{emoji}</span>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`font-semibold text-[14px] ${routine.selected ? "text-[#c2410c]" : "text-[#374151]"}`}>
                  {routine.label}
                </p>
                {routine.selected && (
                  <select
                    className="mt-1 bg-white border border-[#fed7aa] rounded px-2 py-0.5 text-[12px] text-[#c2410c] outline-none"
                    value={routine.time || "Select time"}
                    onChange={(e) => onboardingStore.updateRoutineTime(routine.id, e.target.value === "Select time" ? "" : e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {TIME_OPTIONS.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                )}
                {!routine.selected && routine.time && (
                  <p className="text-[12px] text-[#9ca3af] mt-0.5">Usually around {routine.time}</p>
                )}
              </div>
              <div
                className={`w-5 h-5 rounded-full border-2 shrink-0 flex items-center justify-center transition-all ${
                  routine.selected
                    ? "border-[#f97316] bg-[#f97316]"
                    : "border-[#d1d5db]"
                }`}
              >
                {routine.selected && (
                  <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
                    <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            </motion.button>
          );
        })}
      </motion.div>

      {selectedCount > 0 && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[13px] text-[#f97316] font-semibold text-center"
        >
          {selectedCount} routine{selectedCount !== 1 ? "s" : ""} selected
        </motion.p>
      )}

      {/* Nav */}
      <motion.div variants={item} className="flex gap-3 pt-2">
        <Button variant="secondary" icon={<ArrowLeft size={15} />} onClick={() => onboardingStore.back()}>
          Back
        </Button>
        <Button
          variant="primary"
          icon={<ArrowRight size={16} strokeWidth={2.5} />}
          onClick={() => {
            onboardingStore.complete();
            onboardingStore.next();
          }}
        >
          Build my intelligence →
        </Button>
      </motion.div>
    </motion.div>
  );
}
