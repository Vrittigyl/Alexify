"use client";

import { motion } from "framer-motion";
import { Users, Smartphone, Heart, Sparkles } from "lucide-react";
import { PROCESS_STEPS } from "@/lib/constants";

const iconMap: Record<string, React.ReactNode> = {
  Users: <Users size={22} strokeWidth={1.8} />,
  Smartphone: <Smartphone size={22} strokeWidth={1.8} />,
  Heart: <Heart size={22} strokeWidth={1.8} />,
  Sparkles: <Sparkles size={22} strokeWidth={1.8} />,
};

function DashedConnector() {
  return (
    <div className="hidden sm:flex flex-1 items-center justify-center px-2">
      <div
        className="w-full"
        style={{
          borderTop: "1.5px dashed #d1d5db",
          opacity: 0.8,
        }}
      />
    </div>
  );
}

export function ProcessSteps() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.7, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className="w-full flex justify-center"
    >
      <div className="bg-[#fcfcfb] border border-[#e5e7eb]/80 rounded-[36px] px-8 py-8 sm:px-16 sm:py-10 shadow-sm w-full max-w-[1000px]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 sm:gap-0">
          {PROCESS_STEPS.map((step, index) => (
            <div key={step.id} className="flex items-center flex-1">
              {/* Step card */}
              <div className="flex flex-col items-center gap-4 flex-shrink-0 w-full sm:w-auto">
                {/* Icon container */}
                <motion.div
                  whileHover={{ scale: 1.1, y: -2 }}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                  className="w-16 h-16 rounded-full bg-[#f3f0ff] flex items-center justify-center text-[#6b21a8]"
                >
                  {iconMap[step.icon]}
                </motion.div>

                {/* Text */}
                <div className="text-center">
                  <p className="text-[14px] font-semibold text-[#111827] leading-tight font-heading tracking-wide">
                    {step.title}
                  </p>
                  <p className="text-[12px] text-[#9ca3af] leading-tight mt-0.5">
                    {step.subtitle}
                  </p>
                </div>
              </div>

              {/* Connector — after each step except last */}
              {index < PROCESS_STEPS.length - 1 && <DashedConnector />}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
