"use client";

import { motion, Variants } from "framer-motion";
import { ArrowRight, Play } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { PrivacyCard } from "./PrivacyCard";
import { HERO } from "@/lib/constants";

const containerVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
};

export function HeroContent() {
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="flex flex-col gap-7 lg:gap-8"
    >
      {/* Custom Text Badge */}
      <motion.div variants={itemVariants}>
        <div className="flex items-center gap-3 font-mono text-[13px] font-bold tracking-widest uppercase">
          <span className="text-[#3b82f6]">{"< 04 >"}</span>
          <span className="text-[#9ca3af]">·</span>
          <span className="text-[#4b5563]">AI POWERED HOME INTELLIGENCE</span>
        </div>
      </motion.div>

      {/* Main Heading */}
      <motion.div variants={itemVariants} className="flex flex-col gap-1">
        <h1
          className="text-[48px] sm:text-[54px] lg:text-[58px] xl:text-[64px] font-bold leading-[1.05] tracking-tight text-[#111827] font-heading"
        >
          {HERO.heading1}
          <br />
          {HERO.heading2}{" "}
          <span
            style={{ color: "#8b5cf6" }}
            className="italic font-serif font-normal"
          >
            {HERO.headingHighlight}
          </span>
        </h1>
      </motion.div>

      {/* Supporting text */}
      <motion.p
        variants={itemVariants}
        className="text-[16px] leading-[1.65] text-[#6b7280] font-normal"
        style={{ maxWidth: "460px" }}
      >
        {HERO.subtext}
      </motion.p>

      {/* CTA Buttons */}
      <motion.div
        variants={itemVariants}
        className="flex flex-col sm:flex-row gap-3"
      >
        <Button
          variant="primary"
          icon={<ArrowRight size={16} strokeWidth={2.5} />}
          className="justify-center sm:justify-start"
        >
          {HERO.ctaPrimary}
        </Button>
        <Button
          variant="secondary"
          icon={<Play size={14} strokeWidth={2} fill="currentColor" />}
          className="justify-center sm:justify-start"
        >
          {HERO.ctaSecondary}
        </Button>
      </motion.div>

      {/* Privacy card — bottom left */}
      <motion.div variants={itemVariants} className="mt-2">
        <PrivacyCard />
      </motion.div>
    </motion.div>
  );
}
