"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { dashboardService, type DashboardData } from "@/services/dashboard.service";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { onboardingStore, type OnboardingState } from "@/lib/onboarding-store";
import { useHouseholdSocket } from "@/hooks/useHouseholdSocket";

const HH_ID = "hh_xk92p_sharma";

// How long to wait after a live WS event before refreshing dashboard data (ms).
// Debounced so rapid pipeline events don't flood the backend.
const REFRESH_DEBOUNCE_MS = 2000;

export default function DashboardPage() {
  const [data, setData]           = useState<DashboardData | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);
  const [hhId, setHhId] = useState<string>(HH_ID);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── WebSocket connection ───────────────────────────────────────────────────
  const { connected, lastEvent } = useHouseholdSocket(hhId);

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    const state = onboardingStore.getState();
    const currentHhId = state.householdId || HH_ID;
    setHhId(currentHhId);
    
    dashboardService.load(currentHhId).then(setData);
    
    setOnboarding(state);
    return onboardingStore.subscribe((s) => setOnboarding(s));
  }, []);

  // ── Live refresh on WebSocket events ──────────────────────────────────────
  // When the backend broadcasts an action_planned, notification_sent,
  // command_dispatched, or metrics_update event, refresh dashboard data
  // so RecentEvents, ReasoningFeed, and LearningProgress update without
  // the user having to refresh.
  useEffect(() => {
    if (!lastEvent) return;

    const triggerTypes = new Set([
      "action_planned",
      "command_dispatched",
      "notification_sent",
      "metrics_update",
      "pattern_update",
    ]);

    if (!triggerTypes.has(lastEvent.type)) return;

    // Debounce — wait until the pipeline settles before fetching fresh data
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(async () => {
      dashboardService.clearCache();
      const fresh = await dashboardService.load(hhId, true);
      setData(fresh);
    }, REFRESH_DEBOUNCE_MS);

    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [lastEvent]);

  // ── Loading skeleton ───────────────────────────────────────────────────────
  if (!data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#faf7f3] gap-5">
        <motion.div
          className="flex flex-col items-center gap-3"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <div className="relative">
            {[0, 1].map((i) => (
              <motion.div
                key={i}
                className="absolute inset-0 rounded-2xl border border-[#8b5cf6]"
                animate={{ scale: [1, 1.5 + i * 0.2], opacity: [0.4, 0] }}
                transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.4 }}
              />
            ))}
            <div className="w-14 h-14 rounded-2xl bg-[#111827] flex items-center justify-center">
              <span className="font-mono text-[11px] font-bold text-white tracking-widest">S</span>
            </div>
          </div>
          <p className="text-[13px] text-[#9ca3af] font-mono tracking-wide">Loading household…</p>
        </motion.div>
      </div>
    );
  }

  return (
    <DashboardLayout
      data={data}
      onboardingState={onboarding}
      wsConnected={connected}
    />
  );
}
