"use client";

import { motion } from "framer-motion";
import { Lock, ShieldCheck, Database, SlidersHorizontal, Ban } from "lucide-react";

const privacyPoints = [
  {
    title: "No ads",
    icon: Ban,
    description: "Your data is never monetized or shared with advertisers.",
  },
  {
    title: "No data selling",
    icon: ShieldCheck,
    description: "We don't broker your habits. Your privacy is absolute.",
  },
  {
    title: "Household-owned intelligence",
    icon: Database,
    description: "The AI models learn locally and belong entirely to you.",
  },
  {
    title: "Full control",
    icon: SlidersHorizontal,
    description: "Granular permissions for every device and family member.",
  },
];

export function PrivacySection() {
  return (
    <section className="relative px-8 md:px-12 lg:px-20 py-28 overflow-hidden bg-transparent">
      <div className="relative z-10 max-w-5xl mx-auto flex flex-col items-center">
        {/* Section label */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="flex items-center gap-3 font-mono text-[12px] font-bold tracking-widest uppercase mb-8"
        >
          <span className="text-[#3b82f6]">{"< 04 >"}</span>
          <span className="text-[#9ca3af]">·</span>
          <span className="text-[#4b5563]">PRIVACY</span>
        </motion.div>

        {/* Lock Icon */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ type: "spring", stiffness: 200, damping: 20, delay: 0.1 }}
          className="mb-8 relative"
        >
          <div className="w-24 h-24 rounded-full bg-white border border-[#e5e7eb] flex items-center justify-center shadow-[0_8px_32px_rgba(139,92,246,0.12)]">
            <Lock size={36} className="text-[#8b5cf6]" strokeWidth={1.5} />
          </div>
          {/* Subtle ping animation circle */}
          <div className="absolute inset-0 rounded-full border border-[#8b5cf6]/30 animate-[ping_3s_ease-in-out_infinite]" />
        </motion.div>

        {/* Title */}
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="font-heading text-[40px] md:text-[52px] lg:text-[58px] font-bold text-[#111827] leading-[1.08] tracking-tight mb-16 text-center"
        >
          Your household stays{" "}
          <span className="italic font-serif font-normal text-[#8b5cf6]">
            yours.
          </span>
        </motion.h2>

        {/* Points Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl">
          {privacyPoints.map((point, index) => {
            const Icon = point.icon;
            return (
              <motion.div
                key={point.title}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: 0.3 + index * 0.1 }}
                whileHover={{ y: -4, transition: { duration: 0.2 } }}
                className="bg-white border border-[#e5e7eb] rounded-[28px] p-8 flex items-start gap-6 shadow-[0_4px_24px_rgba(0,0,0,0.04)]"
              >
                <div className="w-14 h-14 rounded-2xl bg-[#f5f3ff] border border-[#ddd6fe]/50 flex items-center justify-center flex-shrink-0">
                  <Icon size={24} className="text-[#8b5cf6]" strokeWidth={1.8} />
                </div>
                <div className="pt-1">
                  <h3 className="font-heading text-[20px] font-bold text-[#111827] mb-2">
                    {point.title}
                  </h3>
                  <p className="text-[15px] text-[#6b7280] leading-relaxed">
                    {point.description}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
