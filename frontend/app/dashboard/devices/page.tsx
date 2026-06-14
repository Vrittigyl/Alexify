"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useDashboard } from "@/components/dashboard/DashboardProvider";
import { Cpu, Power, Droplet, Thermometer, Shield, CheckCircle2, AlertCircle } from "lucide-react";

type CategoryTab = "All" | "Kitchen" | "Water" | "Comfort" | "Safety";

export default function DevicesPage() {
  const { data } = useDashboard();
  const [filter, setFilter] = useState<CategoryTab>("All");

  if (!data) return null;

  const devices = data.devices;

  const filteredDevices = devices.filter(d => {
    if (filter === "All") return true;
    if (filter === "Kitchen") return ["fridge", "microwave", "coffee_maker", "oven", "tv"].includes(d.type);
    if (filter === "Water") return ["water_motor", "geyser", "purifier"].includes(d.type);
    if (filter === "Comfort") return ["ac", "fan", "heater", "lights"].includes(d.type);
    if (filter === "Safety") return ["camera", "lock", "smoke_detector"].includes(d.type);
    return true;
  });

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 className="text-[28px] font-bold text-[#111827]" style={{ fontFamily: "var(--font-space-grotesk)" }}>
          Connected Devices
        </h2>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-2 sm:pb-0">
          {(["All", "Kitchen", "Water", "Comfort", "Safety"] as CategoryTab[]).map(tab => (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-colors shrink-0 ${
                filter === tab ? "bg-[#111827] text-white" : "bg-white border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f9fafb]"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {filteredDevices.map(device => {
          const isOn = device.status === "on";
          const hasIssue = device.status === "alert" || device.alertLevel === "critical" || device.alertLevel === "warning";
          
          return (
            <motion.div
              key={device.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-2xl border border-[#e5e7eb] p-5 shadow-sm flex flex-col gap-4 relative overflow-hidden"
            >
              {isOn && (
                <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
              )}
              {hasIssue && (
                <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
              )}
              
              <div className="flex items-start justify-between">
                <div className="w-10 h-10 rounded-xl bg-[#f3f4f6] flex items-center justify-center text-xl">
                  {device.emoji || "🔌"}
                </div>
                <button className={`p-2 rounded-full border ${isOn ? "bg-emerald-50 border-emerald-200 text-emerald-600" : "bg-gray-50 border-gray-200 text-gray-400"}`}>
                  <Power size={16} />
                </button>
              </div>

              <div>
                <h3 className="text-[15px] font-bold text-[#111827]">{device.name}</h3>
                <p className="text-[12px] text-[#6b7280] mt-0.5">{device.room}</p>
              </div>

              <div className="mt-auto pt-4 border-t border-[#f3f4f6] flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] text-[#9ca3af] uppercase font-mono tracking-wider">Status</span>
                  <span className={`text-[12px] font-semibold ${hasIssue ? "text-amber-600" : isOn ? "text-emerald-600" : "text-[#374151]"}`}>
                    {hasIssue ? "Needs attention" : isOn ? "On" : device.status === "standby" ? "Standby" : "Off"}
                  </span>
                  {device.detail && (
                    <span className="text-[11px] text-[#6b7280]">{device.detail}</span>
                  )}
                </div>
                {device.saathiNote && (
                  <div className="flex flex-col items-end gap-0.5">
                    <span className="text-[10px] text-[#9ca3af] uppercase font-mono tracking-wider">Note</span>
                    <span className="text-[11px] text-right text-[#6b7280] max-w-[110px] leading-tight">{device.saathiNote.slice(0, 30)}{device.saathiNote.length > 30 ? "…" : ""}</span>
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
        {/* Maintenance Ledger */}
        <div className="bg-white rounded-2xl border border-[#e5e7eb] shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-[#f3f4f6] flex items-center justify-between">
            <h3 className="font-bold text-[#111827]">Maintenance Ledger</h3>
            <span className="text-[12px] bg-amber-50 text-amber-600 px-2 py-1 rounded-full font-medium border border-amber-200">1 Upcoming</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-[#f9fafb] text-[#6b7280] border-b border-[#f3f4f6]">
                <tr>
                  <th className="px-5 py-3 font-medium">Device</th>
                  <th className="px-5 py-3 font-medium">Last Service</th>
                  <th className="px-5 py-3 font-medium">Next Due</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f3f4f6]">
                <tr>
                  <td className="px-5 py-3 font-medium text-[#111827]">Rooftop Water Tank</td>
                  <td className="px-5 py-3 text-[#6b7280]">Feb 12, 2026</td>
                  <td className="px-5 py-3 text-[#111827]">Aug 12, 2026</td>
                  <td className="px-5 py-3"><CheckCircle2 size={16} className="text-emerald-500" /></td>
                </tr>
                <tr>
                  <td className="px-5 py-3 font-medium text-[#111827]">Living Room AC</td>
                  <td className="px-5 py-3 text-[#6b7280]">Oct 05, 2025</td>
                  <td className="px-5 py-3 text-amber-600 font-medium">Next week</td>
                  <td className="px-5 py-3"><AlertCircle size={16} className="text-amber-500" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Smart Fridge Inventory */}
        <div className="bg-white rounded-2xl border border-[#e5e7eb] shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-[#f3f4f6] flex items-center justify-between">
            <h3 className="font-bold text-[#111827]">Fridge Inventory</h3>
            <span className="text-[12px] bg-blue-50 text-blue-600 px-2 py-1 rounded-full font-medium border border-blue-200">Smart Scanned</span>
          </div>
          <div className="p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between p-3 rounded-xl border border-[#e5e7eb] bg-[#f9fafb]">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🥛</span>
                <div>
                  <p className="text-[14px] font-bold text-[#111827]">Milk</p>
                  <p className="text-[12px] text-[#6b7280]">Low stock</p>
                </div>
              </div>
              <span className="text-[12px] font-bold text-amber-600">Order today</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-xl border border-[#e5e7eb] bg-white">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🥚</span>
                <div>
                  <p className="text-[14px] font-bold text-[#111827]">Eggs</p>
                  <p className="text-[12px] text-[#6b7280]">12 remaining</p>
                </div>
              </div>
              <span className="text-[12px] font-medium text-[#374151]">Sufficient</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-xl border border-[#e5e7eb] bg-white">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🍎</span>
                <div>
                  <p className="text-[14px] font-bold text-[#111827]">Apples</p>
                  <p className="text-[12px] text-[#6b7280]">Expiring soon</p>
                </div>
              </div>
              <span className="text-[12px] font-medium text-amber-600">Consume soon</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
