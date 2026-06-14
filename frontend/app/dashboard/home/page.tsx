"use client";

import { motion } from "framer-motion";
import { useDashboard } from "@/components/dashboard/DashboardProvider";
import { FamilyPresence } from "@/components/dashboard/FamilyPresence";
import { DeviceOverview } from "@/components/dashboard/DeviceOverview";
import { HouseholdHealth } from "@/components/dashboard/HouseholdHealth";
import { RecentEvents } from "@/components/dashboard/RecentEvents";

export default function HomeDashboard() {
  const { data } = useDashboard();

  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left column (Presence & Devices) */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          {/* Member Presence Strip */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <h2 className="text-xl font-bold text-[#111827] mb-4" style={{ fontFamily: "var(--font-space-grotesk)" }}>
              Household Presence
            </h2>
            <FamilyPresence presence={data.presence} />
          </motion.div>

          {/* Active Devices Strip */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <h2 className="text-xl font-bold text-[#111827] mb-4" style={{ fontFamily: "var(--font-space-grotesk)" }}>
              Active Devices
            </h2>
            <DeviceOverview devices={data.devices} />
          </motion.div>

          {/* Today's predictions (Currently mapped to actions/observations in old UI) */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <h2 className="text-xl font-bold text-[#111827] mb-4" style={{ fontFamily: "var(--font-space-grotesk)" }}>
              Today's Intelligence
            </h2>
            {/* We will map the recent events here to fulfill Recent Actions Feed */}
            <RecentEvents events={data.events.slice(0, 5)} />
          </motion.div>
        </div>

        {/* Right column (Score & Feed) */}
        <div className="flex flex-col gap-6 lg:col-span-1">
          {/* Readiness Score / Health */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <HouseholdHealth health={data.health} />
          </motion.div>
        </div>

      </div>
    </div>
  );
}
