"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Play, Database, Send, AlertCircle } from "lucide-react";
import type { DashboardData } from "@/services/dashboard.service";
import { Button } from "@/components/ui/Button";

interface SimulatorPanelProps {
  isOpen: boolean;
  onClose: () => void;
  data: DashboardData;
}

export function SimulatorPanel({ isOpen, onClose, data }: SimulatorPanelProps) {
  const [ingestPayload, setIngestPayload] = useState('{\n  "event_type": "sensor_reading",\n  "device_id": "sensor_01",\n  "value": 25\n}');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: "success" | "error"; msg: string } | null>(null);

  // Derive suggested events from onboarded devices
  const deviceEvents = data.devices.map(d => ({
    label: `${d.name} (${d.type})`,
    events: [
      { name: `${d.type}_on`, label: `Turn ON` },
      { name: `${d.type}_off`, label: `Turn OFF` },
      { name: `${d.type}_error`, label: `Trigger Error` },
    ]
  }));

  // Common household events
  const commonEvents = [
    { name: "guest_arrival", label: "Guest Arrival" },
    { name: "board_exam", label: "Board Exam" },
    { name: "fridge_door_open", label: "Fridge Door Open" },
    { name: "doorbell_ring", label: "Doorbell Ring" },
    { name: "smoke_detected", label: "Smoke Detected" },
  ];

  async function handleSimulate(eventName: string) {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`http://localhost:8000/simulate/event/${eventName}?household_id=${data.household.id}`, {
        method: "POST",
      });
      if (res.ok) {
        setResult({ status: "success", msg: `Event '${eventName}' simulated successfully.` });
      } else {
        setResult({ status: "error", msg: `Failed to simulate event: ${await res.text()}` });
      }
    } catch (e) {
      setResult({ status: "error", msg: "Backend unreachable." });
    }
    setLoading(false);
  }

  async function handleIngest() {
    setLoading(true);
    setResult(null);
    try {
      let parsed;
      try {
        parsed = JSON.parse(ingestPayload);
      } catch (e) {
        setResult({ status: "error", msg: "Invalid JSON format." });
        setLoading(false);
        return;
      }

      const res = await fetch("http://localhost:8000/events/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          household_id: data.household.id,
          source: "SIMULATOR",
          payload: parsed,
        }),
      });

      if (res.ok) {
        setResult({ status: "success", msg: "Event ingested successfully." });
      } else {
        setResult({ status: "error", msg: `Ingest failed: ${await res.text()}` });
      }
    } catch (e) {
      setResult({ status: "error", msg: "Backend unreachable." });
    }
    setLoading(false);
  }

  async function handleSeed() {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("http://localhost:8000/admin/seed", { method: "POST" });
      if (res.ok) {
        setResult({ status: "success", msg: "Database seeded successfully." });
      } else {
        setResult({ status: "error", msg: `Seed failed: ${await res.text()}` });
      }
    } catch (e) {
      setResult({ status: "error", msg: "Backend unreachable." });
    }
    setLoading(false);
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.4 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black z-40"
          />
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed top-0 right-0 h-full w-full sm:w-[450px] bg-white shadow-2xl z-50 flex flex-col border-l border-[#e5e7eb]"
          >
            <div className="flex items-center justify-between px-6 py-5 border-b border-[#f3f4f6] bg-[#faf7f3]">
              <div>
                <h2 className="text-[18px] font-bold text-[#111827] flex items-center gap-2">
                  <Database size={18} className="text-[#8b5cf6]" />
                  Backend Simulator
                </h2>
                <p className="text-[12px] text-[#6b7280] font-mono mt-0.5">ID: {data.household.id}</p>
              </div>
              <button onClick={onClose} className="p-2 hover:bg-[#e5e7eb] rounded-full transition-colors text-[#6b7280]">
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-8">
              
              {result && (
                <div className={`p-3 rounded-xl flex items-start gap-2 text-[13px] font-medium ${result.status === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
                  <AlertCircle size={16} className="shrink-0 mt-0.5" />
                  <span className="leading-snug">{result.msg}</span>
                </div>
              )}

              {/* Specific Device Events */}
              <div>
                <h3 className="text-[14px] font-bold text-[#111827] mb-3 uppercase tracking-wide">Simulate Device Events</h3>
                <div className="flex flex-col gap-4">
                  {deviceEvents.length > 0 ? deviceEvents.map((group) => (
                    <div key={group.label} className="bg-[#f9fafb] p-3 rounded-xl border border-[#e5e7eb]">
                      <p className="text-[12px] font-bold text-[#374151] mb-2">{group.label}</p>
                      <div className="flex flex-wrap gap-2">
                        {group.events.map((ev) => (
                          <button
                            key={ev.name}
                            onClick={() => handleSimulate(ev.name)}
                            disabled={loading}
                            className="px-3 py-1.5 bg-white border border-[#d1d5db] text-[#374151] text-[12px] font-medium rounded-lg hover:bg-[#f3f4f6] hover:border-[#9ca3af] transition-all flex items-center gap-1 disabled:opacity-50"
                          >
                            <Play size={12} className="text-[#8b5cf6]" /> {ev.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )) : (
                    <p className="text-[12px] text-[#9ca3af]">No devices found in current graph.</p>
                  )}
                </div>
              </div>

              {/* Common Events */}
              <div>
                <h3 className="text-[14px] font-bold text-[#111827] mb-3 uppercase tracking-wide">Common Events</h3>
                <div className="flex flex-wrap gap-2">
                  {commonEvents.map((ev) => (
                    <button
                      key={ev.name}
                      onClick={() => handleSimulate(ev.name)}
                      disabled={loading}
                      className="px-3 py-1.5 bg-[#f5f3ff] border border-[#ddd6fe] text-[#6d28d9] text-[12px] font-medium rounded-lg hover:bg-[#ede9fe] hover:border-[#c4b5fd] transition-all flex items-center gap-1 disabled:opacity-50"
                    >
                      <Play size={12} /> {ev.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Freeform Ingest */}
              <div>
                <h3 className="text-[14px] font-bold text-[#111827] mb-3 uppercase tracking-wide">Custom Event Ingest</h3>
                <textarea
                  value={ingestPayload}
                  onChange={(e) => setIngestPayload(e.target.value)}
                  className="w-full h-32 bg-[#111827] text-[#e5e7eb] font-mono text-[12px] p-3 rounded-xl border border-[#374151] focus:outline-none focus:border-[#8b5cf6] focus:ring-1 focus:ring-[#8b5cf6] mb-2"
                />
                <Button variant="primary" onClick={handleIngest} disabled={loading} className="w-full justify-center !py-2.5 !text-[13px]">
                  <Send size={14} /> Send Custom Event
                </Button>
              </div>

              {/* Admin Tools */}
              <div className="pt-6 border-t border-[#f3f4f6]">
                <h3 className="text-[14px] font-bold text-[#111827] mb-3 uppercase tracking-wide">Admin Tools</h3>
                <Button variant="secondary" onClick={handleSeed} disabled={loading} className="w-full justify-center !py-2.5 !text-[13px] border-red-200 hover:bg-red-50 text-red-700">
                  <Database size={14} /> Seed DynamoDB with Mocks
                </Button>
                <p className="text-[11px] text-[#9ca3af] mt-2 leading-relaxed">
                  Warning: Seeding writes the static Sharma family mock data to the backend DynamoDB tables.
                </p>
              </div>

            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
