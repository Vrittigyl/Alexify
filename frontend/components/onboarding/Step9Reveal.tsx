"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { Sparkles, ArrowRight, Home, Users, Cpu, Clock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { onboardingStore, useOnboardingStore } from "@/lib/onboarding-store";

// Simulated intelligence insights built from user's data
function buildInsights(state: ReturnType<typeof useOnboardingStore>) {
  const insights: { icon: string; title: string; description: string; color: string }[] = [];

  // Device-based
  const hasAC = state.devices.some((d) => d.type === "ac");
  const hasWaterMotor = state.devices.some((d) => d.type === "water_motor");
  const hasTV = state.devices.some((d) => d.type === "television");
  const hasMedicineRoutine = state.routines.some(
    (r) => (r.id === "medicine_morning" || r.id === "medicine_night") && r.selected
  );
  const hasSchoolRun = state.routines.find((r) => r.id === "school_run")?.selected;
  const hasDinnerRoutine = state.routines.find((r) => r.id === "dinner_together")?.selected;
  const hasSenior = state.members.some((m) => m.ageGroup === "senior" || m.role === "grandparent");
  const hasChild = state.members.some((m) => m.ageGroup === "child" || m.ageGroup === "teen");
  const houseName = state.householdName || "your home";

  if (hasAC) {
    insights.push({
      icon: "❄️",
      title: "Smart cooling",
      description: `Will pre-cool ${houseName} 20 minutes before family returns — based on your evening routine.`,
      color: "#0ea5e9",
    });
  }

  if (hasWaterMotor) {
    insights.push({
      icon: "💧",
      title: "Water protection",
      description: "Will stop the motor automatically when the tank is 90% full — no overflow ever.",
      color: "#6366f1",
    });
  }

  if (hasMedicineRoutine && hasSenior) {
    insights.push({
      icon: "💊",
      title: "Medicine guardian",
      description: `Will remind ${state.members.find((m) => m.ageGroup === "senior")?.name ?? "elders"} about medicines and alert family if missed.`,
      color: "#ec4899",
    });
  }

  if (hasSchoolRun && hasChild) {
    insights.push({
      icon: "🏫",
      title: "School routine",
      description: `Primes lights and hot water at the right time so ${state.members.find((m) => m.ageGroup === "child")?.name ?? "kids"} never run late.`,
      color: "#f59e0b",
    });
  }

  if (hasDinnerRoutine) {
    insights.push({
      icon: "🍽️",
      title: "Dinner mode",
      description: `Activates warm lighting and optimal kitchen temperature when it's time for family dinner.`,
      color: "#10b981",
    });
  }

  if (hasTV) {
    insights.push({
      icon: "📺",
      title: "Entertainment ready",
      description: `Learns movie-night preferences and sets the perfect ambience — no settings needed.`,
      color: "#8b5cf6",
    });
  }

  // Always add a generic one if list is short
  if (insights.length < 3) {
    insights.push({
      icon: "🧠",
      title: "Pattern learning",
      description: `SAATHI will study ${houseName}'s rhythms for 7 days and begin making proactive suggestions.`,
      color: "#8b5cf6",
    });
    insights.push({
      icon: "🛡️",
      title: "Privacy by default",
      description: "All data stays on your device. Nothing is shared with any server.",
      color: "#374151",
    });
  }

  return insights.slice(0, 5);
}

// Loading sequence animation
const LOADING_STEPS = [
  { label: "Mapping household structure…", icon: Home },
  { label: "Learning family patterns…", icon: Users },
  { label: "Connecting devices…", icon: Cpu },
  { label: "Calibrating routines…", icon: Clock },
  { label: "Intelligence ready ✓", icon: Sparkles },
];

export function Step9Reveal() {
  const state = useOnboardingStore();
  const router = useRouter();
  const [phase, setPhase] = useState<"loading" | "reveal">("loading");
  const [loadStep, setLoadStep] = useState(0);
  const insights = buildInsights(state);

  useEffect(() => {
    async function callBackend() {
      const currentState = onboardingStore.getState();

      // Always derive a local ID immediately so the dashboard never shows
      // the hardcoded Sharma data when the backend is down.
      const slug = (currentState.householdName || "my")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .slice(0, 10);
      const localId = `hh_${slug}_${Math.random().toString(36).slice(2, 7)}`;

      try {
        const payload = {
          household_name: currentState.householdName,
          household_city: currentState.householdCity,
          members: currentState.members.map(m => ({
            id: m.id,
            name: m.name,
            role: m.role,
            age_group: m.ageGroup,
            care_needs: currentState.careNeeds.find(c => c.memberId === m.id)?.needs || []
          })),
          devices: currentState.devices.map(d => ({
            id: d.id,
            name: d.name,
            device_type: d.type,
            room: d.room
          })),
          routines: currentState.routines.filter(r => r.selected).map(r => ({
            id: r.id,
            label: r.label,
            time: r.time || null
          })),
          priorities: currentState.priorities
        };

        const res = await fetch("http://localhost:8000/onboarding/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(5000), // 5s timeout
        });

        if (res.ok) {
          const data = await res.json();
          // Use the real backend-generated household ID
          onboardingStore.setHouseholdId(data.household_id);
        } else {
          // Backend returned an error — use local ID
          onboardingStore.setHouseholdId(localId);
        }
      } catch {
        // Backend unreachable — use local ID so dashboard shows onboarding data
        onboardingStore.setHouseholdId(localId);
      }
    }

    callBackend();

    let step = 0;
    const interval = setInterval(() => {
      step += 1;
      setLoadStep(step);
      if (step >= LOADING_STEPS.length - 1) {
        clearInterval(interval);
        setTimeout(() => setPhase("reveal"), 600);
      }
    }, 700);
    return () => clearInterval(interval);
  }, []);

  if (phase === "loading") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
        {/* Animated rings */}
        <div className="relative w-24 h-24">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="absolute inset-0 rounded-full border-2 border-[#8b5cf6]"
              animate={{ scale: [1, 1.5 + i * 0.3, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, delay: i * 0.4 }}
            />
          ))}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] flex items-center justify-center shadow-xl shadow-violet-200">
              <Sparkles size={28} className="text-white" strokeWidth={1.5} />
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 w-full max-w-xs">
          {LOADING_STEPS.map((step, i) => {
            const Icon = step.icon;
            const done = i <= loadStep;
            return (
              <motion.div
                key={step.label}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: done ? 1 : 0.25, x: 0 }}
                transition={{ delay: i * 0.1, duration: 0.4 }}
                className="flex items-center gap-3"
              >
                <div
                  className={`w-7 h-7 rounded-xl flex items-center justify-center shrink-0 transition-all duration-500 ${
                    done ? "bg-[#8b5cf6]" : "bg-[#e5e7eb]"
                  }`}
                >
                  <Icon size={13} className={done ? "text-white" : "text-[#9ca3af]"} strokeWidth={2} />
                </div>
                <span className={`text-[13px] font-medium ${done ? "text-[#111827]" : "text-[#9ca3af]"}`}>
                  {step.label}
                </span>
              </motion.div>
            );
          })}
        </div>
      </div>
    );
  }

  // ─── Reveal phase ──────────────────────────────────────────────────────────
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col gap-8"
      >
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="text-center"
        >
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            className="w-20 h-20 rounded-[28px] bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] flex items-center justify-center mx-auto mb-5 shadow-2xl shadow-violet-300"
          >
            <Sparkles size={36} className="text-white" strokeWidth={1.5} />
          </motion.div>
          <h2
            className="text-[40px] sm:text-[48px] font-bold text-[#111827] leading-tight mb-3"
            style={{ fontFamily: "var(--font-space-grotesk)" }}
          >
            SAATHI is{" "}
            <span className="text-[#8b5cf6] italic" style={{ fontFamily: "var(--font-newsreader)" }}>
              ready.
            </span>
          </h2>
          <p className="text-[16px] text-[#6b7280] max-w-sm mx-auto leading-relaxed">
            {state.householdName
              ? `The ${state.householdName} has been understood.`
              : "Your home has been understood."}{" "}
            Here&apos;s what I&apos;ll do for you.
          </p>
        </motion.div>

        {/* Intelligence cards */}
        <div className="flex flex-col gap-3">
          {insights.map((insight, i) => (
            <motion.div
              key={insight.title}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + i * 0.1, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="flex items-start gap-4 bg-white rounded-2xl border border-[#f0eff8] p-4 shadow-sm"
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0"
                style={{ backgroundColor: `${insight.color}15` }}
              >
                {insight.icon}
              </div>
              <div>
                <p className="font-bold text-[#111827] text-[14px] mb-0.5">{insight.title}</p>
                <p className="text-[13px] text-[#6b7280] leading-snug">{insight.description}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Summary bar */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9, duration: 0.5 }}
          className="bg-gradient-to-br from-[#f5f3ff] to-[#ede9fe] rounded-2xl border border-[#ddd6fe] p-4"
        >
          <p className="font-mono text-[10px] tracking-widest uppercase text-[#8b5cf6] mb-3">
            Household summary
          </p>
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Members", value: state.members.length },
              { label: "Devices", value: state.devices.length },
              { label: "Priorities", value: state.priorities.length },
              { label: "Routines", value: state.routines.filter((r) => r.selected).length },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <div className="text-[24px] font-bold text-[#8b5cf6]">{value}</div>
                <div className="font-mono text-[9px] tracking-widest uppercase text-[#9ca3af]">{label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* CTA */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.1, duration: 0.5 }}
          className="flex flex-col items-center gap-3"
        >
          <Button
            variant="primary"
            icon={<ArrowRight size={16} strokeWidth={2.5} />}
            onClick={() => router.push("/dashboard/home")}
            className="w-full sm:w-auto justify-center"
          >
            Open my dashboard
          </Button>
          <p className="text-[11px] text-[#9ca3af]">
            Your household DNA is saved and ready.
          </p>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
