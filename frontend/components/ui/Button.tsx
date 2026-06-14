"use client";

import { motion } from "framer-motion";
import React from "react";

interface ButtonProps {
  variant?: "primary" | "secondary";
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

export function Button({
  variant = "primary",
  children,
  onClick,
  className = "",
  icon,
  disabled = false,
}: ButtonProps) {
  const baseStyles =
    "inline-flex items-center gap-2.5 font-semibold text-[15px] rounded-full transition-all duration-200 cursor-pointer select-none";

  const variants = {
    primary:
      "bg-[#111827] text-white px-7 py-3.5 shadow-lg shadow-black/20 hover:bg-[#1f2937] hover:shadow-xl hover:shadow-black/25",
    secondary:
      "bg-white text-[#374151] px-7 py-3.5 border border-[#e5e7eb] shadow-sm hover:bg-[#f9fafb] hover:border-[#d1d5db]",
  };

  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { scale: 1.03 }}
      whileTap={disabled ? {} : { scale: 0.98 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={`${baseStyles} ${variants[variant]} ${className} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </motion.button>
  );
}
