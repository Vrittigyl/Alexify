"use client";

import { Shield } from "lucide-react";
import { motion } from "framer-motion";
import { PRIVACY } from "@/lib/constants";

export function PrivacyCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.9, duration: 0.5, ease: "easeOut" }}
      className="flex items-start gap-2.5"
    >
      <div className="mt-0.5 flex-shrink-0">
        <Shield
          size={16}
          strokeWidth={1.8}
          className="text-[#8b5cf6]"
          fill="rgba(139, 92, 246, 0.1)"
        />
      </div>
      <div>
        <p className="text-[13px] font-semibold text-[#374151] leading-tight">
          {PRIVACY.line1}
        </p>
        <p className="text-[12px] text-[#9ca3af] leading-tight mt-0.5">
          {PRIVACY.line2}
        </p>
      </div>
    </motion.div>
  );
}
