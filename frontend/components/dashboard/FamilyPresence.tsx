"use client";

import type { FamilyPresence as FP } from "@/services/dashboard.service";

const ageColor: Record<string, string> = {
  senior: "#8b5cf6",
  adult:  "#374151",
  teen:   "#0ea5e9",
  child:  "#10b981",
};

export function FamilyPresence({ presence }: { presence: FP }) {
  // isLive === false means no live presence endpoint. Show honest banner.
  const isLive = presence.isLive !== false;

  return (
    <div className="bg-white border border-[#e5e7eb] rounded-2xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[#f3f4f6] flex items-center justify-between">
        <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-[#9ca3af] font-semibold">Family presence</p>
        {!isLive && (
          <span className="text-[10px] font-mono bg-[#fef9c3] text-[#92400e] px-1.5 py-0.5 rounded">
            Illustrative · no live endpoint
          </span>
        )}
      </div>

      {/* Honest banner when no live data */}
      {!isLive && (
        <div className="px-5 py-2.5 border-b border-[#fef3c7] bg-[#fffbeb]">
          <p className="text-[11px] text-[#92400e] leading-relaxed">
            No live presence API is connected. Member locations below are illustrative defaults, not real-time data.
          </p>
        </div>
      )}

      {/* Home */}
      {presence.home.length > 0 && (
        <div className={`px-5 py-3 border-b border-[#f9f9f9]${!isLive ? " opacity-60" : ""}`}>
          <p className="font-mono text-[9px] tracking-[0.15em] uppercase text-[#10b981] mb-2">Home · {presence.home.length}</p>
          <div className="flex flex-col gap-2">
            {presence.home.map((m) => {
              const activity = presence.currentActivity.find((a) => a.memberId === m.id);
              return (
                <div key={m.id} className="flex items-center gap-2.5">
                  <div
                    className="w-6 h-6 rounded-full border flex items-center justify-center text-[11px] font-bold shrink-0"
                    style={{ color: ageColor[m.ageGroup], borderColor: `${ageColor[m.ageGroup]}30`, backgroundColor: `${ageColor[m.ageGroup]}08` }}
                  >
                    {m.name[0]}
                  </div>
                  <div className="min-w-0">
                    <span className="text-[13px] font-semibold text-[#111827]">{m.name}</span>
                    {activity && (
                      <p className="text-[11px] text-[#9ca3af] truncate">{activity.activity}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Away */}
      {presence.away.length > 0 && (
        <div className={`px-5 py-3${!isLive ? " opacity-60" : ""}`}>
          <p className="font-mono text-[9px] tracking-[0.15em] uppercase text-[#9ca3af] mb-2">Away · {presence.away.length}</p>
          <div className="flex flex-col gap-2">
            {presence.away.map((m) => (
              <div key={m.id} className="flex items-center gap-2.5 opacity-60">
                <div
                  className="w-6 h-6 rounded-full border flex items-center justify-center text-[11px] font-bold shrink-0"
                  style={{ color: ageColor[m.ageGroup], borderColor: `${ageColor[m.ageGroup]}30`, backgroundColor: `${ageColor[m.ageGroup]}08` }}
                >
                  {m.name[0]}
                </div>
                <span className="text-[13px] font-semibold text-[#6b7280]">{m.name}</span>
                <span className="text-[11px] text-[#9ca3af] ml-auto capitalize">{m.ageGroup}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
