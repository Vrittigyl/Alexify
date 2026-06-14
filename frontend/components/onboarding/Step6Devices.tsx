"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, ArrowLeft, Cpu, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { onboardingStore, useOnboardingStore, Device } from "@/lib/onboarding-store";
import { useState } from "react";

const DEVICE_TYPES: { type: Device["type"]; label: string; emoji: string }[] = [
  { type: "ac", label: "Air Conditioner", emoji: "❄️" },
  { type: "tv", label: "Smart TV", emoji: "📺" },
  { type: "water_motor", label: "Water Motor", emoji: "💧" },
  { type: "geyser", label: "Geyser / Water Heater", emoji: "🔥" },
  { type: "fridge", label: "Refrigerator", emoji: "🧊" },
  { type: "washing_machine", label: "Washing Machine", emoji: "🫧" },
  { type: "pressure_cooker", label: "Pressure Cooker", emoji: "♨️" },
  { type: "lights", label: "Smart Lights", emoji: "💡" },
  { type: "security_camera", label: "Security Camera", emoji: "📷" },
  { type: "doorbell", label: "Smart Doorbell", emoji: "🔔" },
  { type: "other", label: "Other", emoji: "🔌" },
];

const ROOMS = ["Living Room", "Bedroom 1", "Bedroom 2", "Kitchen", "Bathroom", "Hall", "Study", "Terrace", "Other"];

function generateId() {
  return Math.random().toString(36).slice(2, 9);
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as [number,number,number,number] } },
};
const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

function QuickAddChip({
  type, emoji, label, alreadyAdded, onAdd,
}: {
  type: Device["type"]; emoji: string; label: string; alreadyAdded: boolean; onAdd: () => void;
}) {
  return (
    <motion.button
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.96 }}
      onClick={onAdd}
      className={`flex items-center gap-2 px-3 py-2 rounded-2xl border text-[13px] font-semibold transition-all ${
        alreadyAdded
          ? "bg-[#f0fdf4] border-[#86efac] text-[#16a34a] cursor-default"
          : "bg-white border-[#e5e7eb] text-[#374151] hover:border-[#8b5cf6] hover:text-[#8b5cf6]"
      }`}
    >
      <span>{emoji}</span>
      {label}
      {!alreadyAdded && <Plus size={12} className="text-[#9ca3af]" />}
      {alreadyAdded && (
        <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
          <path d="M1 5L4 8L11 1" stroke="#16a34a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </motion.button>
  );
}

export function Step6Devices() {
  const state = useOnboardingStore();
  const [selectedRoom, setSelectedRoom] = useState(ROOMS[0]);

  function quickAdd(type: Device["type"], label: string, emoji: string) {
    // Check if already added for this room
    const exists = state.devices.some((d) => d.type === type && d.room === selectedRoom);
    if (exists) return;
    onboardingStore.addDevice({
      id: generateId(),
      name: label,
      type,
      room: selectedRoom,
      brand: undefined,
    });
  }

  function handleRemove(id: string) {
    onboardingStore.removeDevice(id);
  }

  const grouped = ROOMS.reduce<Record<string, Device[]>>((acc, room) => {
    const devs = state.devices.filter((d) => d.room === room);
    if (devs.length > 0) acc[room] = devs;
    return acc;
  }, {});

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-8">
      {/* Header */}
      <motion.div variants={item}>
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#0ea5e9] to-[#0284c7] flex items-center justify-center mb-4">
          <Cpu size={22} strokeWidth={1.8} className="text-white" />
        </div>
        <h2 className="text-[32px] font-bold text-[#111827] leading-tight mb-2" style={{ fontFamily: "var(--font-space-grotesk)" }}>
          Show SAATHI your home
        </h2>
        <p className="text-[15px] text-[#6b7280]">
          Tell us which appliances you have. Tap a device to add it to a room.
        </p>
      </motion.div>

      {/* Room selector */}
      <motion.div variants={item}>
        <p className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] mb-2">Select room</p>
        <div className="flex gap-2 flex-wrap">
          {ROOMS.map((room) => (
            <button
              key={room}
              onClick={() => setSelectedRoom(room)}
              className={`px-3 py-1.5 rounded-xl text-[12px] font-semibold border transition-all ${
                selectedRoom === room
                  ? "bg-[#111827] text-white border-[#111827]"
                  : "bg-white text-[#6b7280] border-[#e5e7eb] hover:border-[#374151]"
              }`}
            >
              {room}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Quick-add chips */}
      <motion.div variants={item}>
        <p className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] mb-3">
          Add to {selectedRoom}
        </p>
        <div className="flex flex-wrap gap-2">
          {DEVICE_TYPES.map(({ type, label, emoji }) => {
            const already = state.devices.some((d) => d.type === type && d.room === selectedRoom);
            return (
              <QuickAddChip
                key={type}
                type={type}
                emoji={emoji}
                label={label}
                alreadyAdded={already}
                onAdd={() => quickAdd(type, label, emoji)}
              />
            );
          })}
        </div>
      </motion.div>

      {/* Device summary */}
      {Object.keys(grouped).length > 0 && (
        <motion.div variants={item} className="flex flex-col gap-3">
          <p className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af]">Your devices</p>
          {Object.entries(grouped).map(([room, devs]) => (
            <div key={room} className="bg-white rounded-2xl border border-[#e5e7eb] p-4 shadow-sm">
              <p className="font-semibold text-[#374151] text-[13px] mb-2">{room}</p>
              <div className="flex flex-wrap gap-2">
                <AnimatePresence>
                  {devs.map((d) => {
                    const meta = DEVICE_TYPES.find((dt) => dt.type === d.type);
                    return (
                      <motion.div
                        key={d.id}
                        initial={{ opacity: 0, scale: 0.85 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.85 }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#f5f3ff] border border-[#ddd6fe] text-[12px] font-semibold text-[#6d28d9]"
                      >
                        <span>{meta?.emoji ?? "🔌"}</span>
                        {d.name}
                        <button
                          onClick={() => handleRemove(d.id)}
                          className="ml-1 text-[#c4b5fd] hover:text-[#7c3aed] transition-colors"
                        >
                          <Trash2 size={11} />
                        </button>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {state.devices.length === 0 && (
        <motion.div variants={item} className="text-center py-4">
          <p className="text-[13px] text-[#9ca3af]">No devices added yet — you can skip this and add them later.</p>
        </motion.div>
      )}

      {/* Nav */}
      <motion.div variants={item} className="flex gap-3 pt-2">
        <Button variant="secondary" icon={<ArrowLeft size={15} />} onClick={() => onboardingStore.back()}>
          Back
        </Button>
        <Button
          variant="primary"
          icon={<ArrowRight size={16} strokeWidth={2.5} />}
          onClick={() => onboardingStore.next()}
        >
          {state.devices.length === 0 ? "Skip for now" : "Continue"}
        </Button>
      </motion.div>
    </motion.div>
  );
}
