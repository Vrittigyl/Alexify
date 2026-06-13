"use client";

import { Triangle } from "lucide-react";
import { BRAND } from "@/lib/constants";

export function TopBrand() {
  return (
    <header className="w-full px-8 md:px-12 lg:px-16 py-5 flex items-center justify-between">
      {/* Logo */}
      <div className="flex items-center gap-2.5">
        {/* Purple icon — minimal geometric mark */}
        <div className="relative w-8 h-8 flex items-center justify-center">
          <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] opacity-90" />
          <Triangle
            size={14}
            strokeWidth={2.5}
            className="relative z-10 text-white fill-white"
            style={{ transform: "rotate(180deg)" }}
          />
        </div>
        <span className="text-[#111827] font-bold text-[18px] tracking-tight font-heading">
          {BRAND.name}
        </span>
      </div>

      {/* Right side: intentionally empty as per spec */}
      <div />
    </header>
  );
}
