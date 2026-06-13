"use client";

import { motion } from "framer-motion";
import { Users, Pill, Droplets } from "lucide-react";

const stories = [
  {
    id: "guests",
    icon: Users,
    iconColor: "#8b5cf6",
    iconBg: "#f3f0ff",
    tag: "Smart Hosting",
    tagColor: "#8b5cf6",
    tagBg: "#f3f0ff",
    headline: "Guests arriving at 7 PM",
    items: [
      "Notices extended family is visiting",
      "Cools the living room automatically",
      "Suggests extra seating arrangement",
      "Reminds everyone via their phones",
    ],
    accent: "#8b5cf6",
  },
  {
    id: "medicine",
    icon: Pill,
    iconColor: "#f59e0b",
    iconBg: "#fffbeb",
    tag: "Elder Care",
    tagColor: "#d97706",
    tagBg: "#fef3c7",
    headline: "Dadaji missed his medicine",
    items: [
      "Detects disruption in daily routine",
      "Notifies Mama immediately",
      "Follows up again 30 minutes later",
    ],
    accent: "#f59e0b",
  },
  {
    id: "water",
    icon: Droplets,
    iconColor: "#0ea5e9",
    iconBg: "#f0f9ff",
    tag: "Resource Guard",
    tagColor: "#0284c7",
    tagBg: "#e0f2fe",
    headline: "Water tank nearing full",
    items: [
      "Predicts overflow from usage pattern",
      "Stops the motor before overflow",
      "Logs event in household timeline",
    ],
    accent: "#0ea5e9",
  },
];

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.15 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 40 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] } },
};

export function HouseholdStories() {
  return (
    <section className="px-8 md:px-12 lg:px-20 py-24">
      {/* Section label */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6 }}
        className="flex items-center gap-3 font-mono text-[12px] font-bold tracking-widest uppercase mb-6"
      >
        <span className="text-[#3b82f6]">{"< 03 >"}</span>
        <span className="text-[#9ca3af]">·</span>
        <span className="text-[#4b5563]">Real Household Stories</span>
      </motion.div>

      {/* Title */}
      <motion.h2
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.7, delay: 0.1 }}
        className="font-heading text-[40px] md:text-[52px] lg:text-[58px] font-bold text-[#111827] leading-[1.08] tracking-tight mb-4"
      >
        A system that{" "}
        <span className="italic font-serif font-normal text-[#8b5cf6]">
          thinks ahead.
        </span>
      </motion.h2>

      <motion.p
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="text-[17px] text-[#6b7280] max-w-[520px] mb-16 leading-relaxed"
      >
        SAATHI doesn't wait for commands. It watches, learns, and handles things
        before you even notice them.
      </motion.p>

      {/* Cards */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true }}
        className="grid grid-cols-1 md:grid-cols-3 gap-6"
      >
        {stories.map((story) => {
          const Icon = story.icon;
          return (
            <motion.div
              key={story.id}
              variants={cardVariants}
              whileHover={{ y: -6, transition: { duration: 0.3 } }}
              className="relative bg-white rounded-[28px] border border-[#e5e7eb] p-7 flex flex-col gap-5 shadow-[0_4px_24px_rgba(0,0,0,0.05)] overflow-hidden group"
            >
              {/* Subtle top accent bar */}
              <div
                className="absolute top-0 left-0 right-0 h-[3px] rounded-t-[28px]"
                style={{ backgroundColor: story.accent, opacity: 0.6 }}
              />

              {/* Icon + tag */}
              <div className="flex items-start justify-between">
                <div
                  className="w-12 h-12 rounded-2xl flex items-center justify-center"
                  style={{ backgroundColor: story.iconBg }}
                >
                  <Icon size={22} strokeWidth={1.8} style={{ color: story.iconColor }} />
                </div>
                <span
                  className="text-[11px] font-mono font-bold tracking-widest uppercase px-3 py-1 rounded-full"
                  style={{ backgroundColor: story.tagBg, color: story.tagColor }}
                >
                  {story.tag}
                </span>
              </div>

              {/* Headline */}
              <h3 className="font-heading text-[18px] font-bold text-[#111827] leading-snug">
                {story.headline}
              </h3>

              {/* Divider */}
              <div className="h-px bg-[#f3f4f6]" />

              {/* SAATHI response */}
              <div className="flex flex-col gap-1.5">
                <p className="text-[11px] font-mono font-bold tracking-widest uppercase text-[#9ca3af] mb-1">
                  SAATHI
                </p>
                {story.items.map((item, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <div
                      className="mt-[6px] w-[5px] h-[5px] rounded-full flex-shrink-0"
                      style={{ backgroundColor: story.accent }}
                    />
                    <p className="text-[14px] text-[#374151] leading-snug">{item}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </section>
  );
}
