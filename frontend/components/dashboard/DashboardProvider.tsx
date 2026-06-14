"use client";

import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname, useRouter } from "next/navigation";
import { dashboardService, type DashboardData } from "@/services/dashboard.service";
import { onboardingStore, type OnboardingState } from "@/lib/onboarding-store";
import { useHouseholdSocket } from "@/hooks/useHouseholdSocket";
import { DashboardHeader } from "./DashboardHeader";

const HH_ID = "hh_xk92p_sharma";
const REFRESH_DEBOUNCE_MS = 2000;

interface DashboardContextType {
  data: DashboardData | null;
  onboardingState: OnboardingState | null;
  wsConnected: boolean;
}

const DashboardContext = createContext<DashboardContextType>({
  data: null,
  onboardingState: null,
  wsConnected: false,
});

export function useDashboard() {
  return useContext(DashboardContext);
}

const TABS = [
  { name: "Home", path: "/dashboard/home" },
  { name: "Household", path: "/dashboard/household" },
  { name: "SAATHI Chat", path: "/dashboard/chat" },
  { name: "Routines", path: "/dashboard/routines" },
  { name: "Devices", path: "/dashboard/devices" },
];

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);
  const [hhId, setHhId] = useState<string>(HH_ID);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { connected, lastEvent } = useHouseholdSocket(hhId);
  const pathname = usePathname();
  const router = useRouter();

  // Initial load
  useEffect(() => {
    const state = onboardingStore.getState();
    // Use householdId from onboarding if it exists, otherwise fallback to demo
    const currentHhId = state.householdId || HH_ID;
    setHhId(currentHhId);
    setOnboarding(state);

    dashboardService.load(currentHhId, false, state).then(setData);

    return onboardingStore.subscribe((s) => {
      setOnboarding(s);
      // If the householdId just changed (onboarding just completed), reload
      if (s.householdId && s.householdId !== currentHhId) {
        dashboardService.clearCache();
        dashboardService.load(s.householdId, true, s).then(setData);
      }
    });
  }, []);

  // Live refresh
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

    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(async () => {
      dashboardService.clearCache();
      const fresh = await dashboardService.load(hhId, true);
      setData(fresh);
    }, REFRESH_DEBOUNCE_MS);

    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [lastEvent, hhId]);

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
          <p className="text-[13px] text-[#9ca3af] font-mono tracking-wide">Loading live household data…</p>
        </motion.div>
      </div>
    );
  }

  return (
    <DashboardContext.Provider value={{ data, onboardingState: onboarding, wsConnected: connected }}>
      <div className="min-h-screen bg-[#faf7f3] flex flex-col">
        <DashboardHeader data={data} wsConnected={connected} />
        
        {/* Tab Navigation */}
        <div className="bg-white border-b border-[#e5e7eb] sticky top-[60px] z-20 shadow-sm">
          <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8">
            <nav className="flex gap-6 overflow-x-auto scrollbar-hide">
              {TABS.map((tab) => {
                const isActive = pathname === tab.path;
                return (
                  <button
                    key={tab.path}
                    onClick={() => router.push(tab.path)}
                    className={`relative py-4 text-[14px] font-medium transition-colors whitespace-nowrap ${
                      isActive ? "text-[#111827]" : "text-[#6b7280] hover:text-[#374151]"
                    }`}
                  >
                    {tab.name}
                    {isActive && (
                      <motion.div
                        layoutId="activeTab"
                        className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#8b5cf6]"
                      />
                    )}
                  </button>
                );
              })}
            </nav>
          </div>
        </div>

        {/* Main Content Area */}
        <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </DashboardContext.Provider>
  );
}
