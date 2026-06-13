"use client";

import { Sparkles } from "lucide-react";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

export function Badge({ children, className = "" }: BadgeProps) {
  return (
    <div
      className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[11px] font-semibold tracking-widest uppercase border border-[#ddd6fe] bg-[#f5f3ff] text-[#7c3aed] ${className}`}
    >
      <Sparkles size={10} strokeWidth={2.5} className="text-[#8b5cf6]" />
      {children}
    </div>
  );
}
