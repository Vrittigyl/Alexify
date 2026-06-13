"use client";

import { motion } from "framer-motion";
import { Home, BrainCircuit, Sparkles } from "lucide-react";

const timeline = [
  {
    phase: "Today",
    title: "Smart Home",
    icon: Home,
    description: "Devices you control manually via apps and voice commands.",
    color: "#6b7280", // Gray
    bg: "#f3f4f6",
  },
  {
    phase: "Tomorrow",
    title: "Household Intelligence",
    icon: BrainCircuit,
    description: "Systems that learn your routines and anticipate your needs.",
    color: "#8b5cf6", // Purple
    bg: "#f5f3ff",
  },
  {
    phase: "Future",
    title: "Autonomous Household",
    icon: Sparkles,
    description: "A home that seamlessly manages itself around your family's life.",
    color: "#3b82f6", // Blue
    bg: "#eff6ff",
  },
];

export function FutureVision() {
  return (
    <section className="relative px-8 md:px-12 lg:px-20 py-32 bg-[#faf7f3] overflow-hidden">
      <div className="max-w-6xl mx-auto flex flex-col items-center text-center">
        {/* Section label */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="flex items-center gap-3 font-mono text-[12px] font-bold tracking-widest uppercase mb-6"
        >
          <span className="text-[#3b82f6]">{"< 05 >"}</span>
          <span className="text-[#9ca3af]">·</span>
          <span className="text-[#4b5563]">FUTURE VISION</span>
        </motion.div>

        {/* Title */}
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="font-heading text-[40px] md:text-[52px] lg:text-[58px] font-bold text-[#111827] leading-[1.08] tracking-tight mb-24 max-w-4xl"
        >
          The operating system for{" "}
          <span className="italic font-serif font-normal text-[#8b5cf6]">
            family life.
          </span>
        </motion.h2>

        {/* Timeline container */}
        <div className="w-full relative flex flex-col lg:flex-row gap-8 lg:gap-0 mt-8 mb-24">
          {/* Horizontal connecting line (Desktop only) */}
          <div className="hidden lg:block absolute top-[48px] left-[10%] right-[10%] h-[2px] bg-[#e5e7eb] z-0" />
          
          {/* Vertical connecting line (Mobile only) */}
          <div className="block lg:hidden absolute top-[48px] bottom-[48px] left-[48px] w-[2px] bg-[#e5e7eb] z-0" />

          {timeline.map((item, index) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.phase}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7, delay: 0.2 + index * 0.2 }}
                className="relative z-10 flex-1 flex flex-col lg:items-center text-left lg:text-center group"
              >
                {/* Mobile horizontal layout wrapper */}
                <div className="flex flex-row lg:flex-col items-center lg:items-center gap-6 lg:gap-6 w-full">
                  {/* Icon Node */}
                  <div
                    className="w-24 h-24 rounded-full flex items-center justify-center flex-shrink-0 bg-white border-4 border-[#faf7f3] shadow-sm relative transition-transform duration-500 group-hover:scale-110"
                    style={{ zIndex: 10 }}
                  >
                    <div
                      className="w-16 h-16 rounded-full flex items-center justify-center"
                      style={{ backgroundColor: item.bg }}
                    >
                      <Icon size={28} strokeWidth={1.5} style={{ color: item.color }} />
                    </div>
                  </div>

                  {/* Content */}
                  <div className="flex flex-col gap-2">
                    <span className="font-mono text-[11px] font-bold tracking-widest uppercase text-[#9ca3af]">
                      {item.phase}
                    </span>
                    <h3 className="font-heading text-[22px] font-bold text-[#111827]">
                      {item.title}
                    </h3>
                    <p className="text-[15px] text-[#6b7280] leading-relaxed max-w-[260px] mx-auto lg:mx-0">
                      {item.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Closing Quote */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="mt-12"
        >
          <div className="inline-block relative">
            <Sparkles 
              size={20} 
              className="absolute -top-6 -left-6 text-[#a78bfa] opacity-60" 
            />
            <p className="font-serif italic text-[28px] md:text-[36px] text-[#111827] leading-relaxed px-8">
              "It doesn't feel like technology.{" "}
              <br className="block sm:hidden" />
              <span className="text-[#8b5cf6]">It feels like home."</span>
            </p>
            <Sparkles 
              size={20} 
              className="absolute -bottom-6 -right-6 text-[#a78bfa] opacity-60" 
            />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
