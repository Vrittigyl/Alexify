"use client";

import React from "react";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
}

export function GlassCard({ children, className = "" }: GlassCardProps) {
  return (
    <div
      className={`bg-white/70 backdrop-blur-xl border border-white/80 rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.07)] ${className}`}
    >
      {children}
    </div>
  );
}
