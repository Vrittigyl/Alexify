"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useDashboard } from "@/components/dashboard/DashboardProvider";
import { ReasoningFeed } from "@/components/dashboard/ReasoningFeed";
import { Send, Sparkles, User, Cpu, Database } from "lucide-react";
import { SimulatorPanel } from "@/components/dashboard/SimulatorPanel";
import { BACKEND_BASE } from "@/services/api.config";

const SUGGESTIONS = [
  { label: "Grandpa's BP is high", event: "Dadaji's BP is reading 150/90. Should we adjust anything?" },
  { label: "Unexpected Guests", event: "Rohan's friends just arrived for a study session." },
  { label: "Water tank overflow", event: "The water tank is overflowing!" },
];

export default function ChatPage() {
  const { data } = useDashboard();
  const [messages, setMessages] = useState<{ role: "user" | "saathi"; content: string; id: number }[]>([
    { role: "saathi", content: "Hello! I'm SAATHI. How can I assist the household today?", id: Date.now() },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [simulatorOpen, setSimulatorOpen] = useState(false);

  if (!data) return null;

  async function handleSend(text: string) {
    if (!text.trim() || !data) return;
    
    const userMsg = { role: "user" as const, content: text, id: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      // Freeform ingest fallback
      const res = await fetch(`${BACKEND_BASE}/events/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          household_id: data.household.id,
          source: "SAATHI_CHAT",
          payload: { text },
        }),
      });

      let reply = "I've processed your request.";
      if (res.ok) {
        const body = await res.json();
        if (body.decision) {
          reply = `I routed this via ${body.decision.route}. ${body.decision.suggested_action || ""}`;
        }
      } else {
        reply = "I couldn't reach the backend, but I've noted this in my mock memory.";
      }
      
      setTimeout(() => {
        setMessages((prev) => [...prev, { role: "saathi", content: reply, id: Date.now() + 1 }]);
        setLoading(false);
      }, 500);

    } catch (e) {
      setTimeout(() => {
        setMessages((prev) => [...prev, { role: "saathi", content: "I'm operating in offline mode right now.", id: Date.now() + 1 }]);
        setLoading(false);
      }, 500);
    }
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row h-[calc(100vh-160px)]">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-white rounded-2xl border border-[#e5e7eb] shadow-sm overflow-hidden relative">
        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-4 max-w-[80%] ${msg.role === "user" ? "self-end flex-row-reverse" : "self-start"}`}
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "user" ? "bg-gray-100" : "bg-violet-100"}`}>
                {msg.role === "user" ? <User size={14} className="text-gray-600" /> : <Sparkles size={14} className="text-violet-600" />}
              </div>
              <div className={`px-4 py-3 rounded-2xl text-[14px] ${msg.role === "user" ? "bg-[#111827] text-white rounded-tr-sm" : "bg-[#f3f4f6] text-[#111827] rounded-tl-sm"}`}>
                {msg.content}
              </div>
            </motion.div>
          ))}
          {loading && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4 self-start">
              <div className="w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center">
                <Sparkles size={14} className="text-violet-600 animate-pulse" />
              </div>
              <div className="px-4 py-3 rounded-2xl bg-[#f3f4f6] text-[#9ca3af] text-[14px] rounded-tl-sm flex items-center gap-1">
                <span className="animate-bounce">.</span><span className="animate-bounce delay-100">.</span><span className="animate-bounce delay-200">.</span>
              </div>
            </motion.div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-[#f3f4f6] bg-white">
          <div className="flex gap-2 mb-3 overflow-x-auto scrollbar-hide pb-1">
            {SUGGESTIONS.map((sug) => (
              <button
                key={sug.label}
                onClick={() => handleSend(sug.event)}
                className="px-3 py-1.5 rounded-full border border-[#e5e7eb] text-[12px] text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827] transition-colors whitespace-nowrap shrink-0"
              >
                {sug.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend(input)}
              placeholder="Tell SAATHI what's happening..."
              className="flex-1 bg-[#f9fafb] border border-[#e5e7eb] rounded-xl px-4 py-3 text-[14px] text-[#111827] focus:outline-none focus:border-[#8b5cf6] focus:ring-1 focus:ring-[#8b5cf6]"
            />
            <button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || loading}
              className="w-12 h-12 rounded-xl bg-[#8b5cf6] flex items-center justify-center text-white disabled:opacity-50 hover:bg-[#7c3aed] transition-colors shrink-0"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Right Sidebar - Reasoning Panel */}
      <div className="w-full lg:w-[360px] flex flex-col gap-4 overflow-y-auto pr-1">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-[#111827] flex items-center gap-2">
            <Cpu size={18} className="text-[#8b5cf6]" /> Reasoning Panel
          </h3>
          <button 
            onClick={() => setSimulatorOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#f3f4f6] hover:bg-[#e5e7eb] rounded-lg text-[12px] font-semibold text-[#374151] transition-colors"
          >
            <Database size={14} className="text-[#8b5cf6]" /> Simulator
          </button>
        </div>
        <ReasoningFeed entries={data.reasoning} />
      </div>

      <SimulatorPanel isOpen={simulatorOpen} onClose={() => setSimulatorOpen(false)} data={data} />
    </div>
  );
}
