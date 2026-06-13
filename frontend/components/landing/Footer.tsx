"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

const links = [
  { label: "Home", href: "#" },
  { label: "Why SAATHI?", href: "#" },
  { label: "Household Stories", href: "#" },
  { label: "Contact Us", href: "#" },
];

const legal = [
  { label: "Privacy Policy", href: "#" },
  { label: "Terms of Service", href: "#" },
  { label: "Security", href: "#" },
  { label: "Cookie Policy", href: "#" },
];

export function Footer() {
  return (
    <footer className="w-full bg-[#faf7f3] pt-20 pb-8 px-8 md:px-12 lg:px-20 border-t border-[#e5e7eb]/60">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-start gap-12 md:gap-8">
        
        {/* Brand */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#8b5cf6] to-[#6d28d9] flex items-center justify-center text-white shadow-sm">
            <Sparkles size={14} strokeWidth={2.5} />
          </div>
          <span className="font-heading font-bold text-[#111827] tracking-tight text-[17px]">
            SAATHI
          </span>
        </div>

        {/* Links & Legal Columns */}
        <div className="flex gap-16 md:gap-24 lg:gap-32">
          {/* Links Column */}
          <div className="flex flex-col gap-5">
            <h4 className="font-mono text-[10px] font-bold tracking-[0.2em] text-[#9ca3af] uppercase">
              Links
            </h4>
            <div className="flex flex-col gap-3.5">
              {links.map((link) => (
                <Link
                  key={link.label}
                  href={link.href}
                  className="text-[14px] text-[#6b7280] hover:text-[#111827] transition-colors"
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </div>

          {/* Legal Column */}
          <div className="flex flex-col gap-5">
            <h4 className="font-mono text-[10px] font-bold tracking-[0.2em] text-[#9ca3af] uppercase">
              Legal
            </h4>
            <div className="flex flex-col gap-3.5">
              {legal.map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  className="text-[14px] text-[#6b7280] hover:text-[#111827] transition-colors"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        </div>

        {/* Social Icons Stack */}
        <div className="hidden lg:flex flex-col gap-3">
          {/* Twitter/X */}
          <a href="#" className="w-10 h-10 rounded-full bg-white flex items-center justify-center text-[#6b7280] hover:text-[#111827] shadow-[0_2px_10px_rgba(0,0,0,0.04)] border border-[#f3f4f6] transition-all hover:scale-105">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4l16 16M4 20L20 4"/></svg>
          </a>
          {/* LinkedIn */}
          <a href="#" className="w-10 h-10 rounded-full bg-white flex items-center justify-center text-[#6b7280] hover:text-[#111827] shadow-[0_2px_10px_rgba(0,0,0,0.04)] border border-[#f3f4f6] transition-all hover:scale-105">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>
          </a>
          {/* Mail */}
          <a href="#" className="w-10 h-10 rounded-full bg-white flex items-center justify-center text-[#6b7280] hover:text-[#111827] shadow-[0_2px_10px_rgba(0,0,0,0.04)] border border-[#f3f4f6] transition-all hover:scale-105">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
          </a>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="max-w-6xl mx-auto mt-20 pt-6 border-t border-[#e5e7eb]/60 flex flex-col md:flex-row items-center justify-between gap-4">
        <p className="text-[13px] text-[#9ca3af]">
          © 2026 SAATHI, Inc. All rights reserved.
        </p>
        
        {/* Mobile social icons */}
        <div className="flex lg:hidden gap-4">
          <a href="#" className="text-[#9ca3af] hover:text-[#111827]"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4l16 16M4 20L20 4"/></svg></a>
          <a href="#" className="text-[#9ca3af] hover:text-[#111827]"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg></a>
          <a href="#" className="text-[#9ca3af] hover:text-[#111827]"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg></a>
        </div>
      </div>
    </footer>
  );
}
