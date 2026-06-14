"use client";

/**
 * DeleteHouseholdModal — Phase 12B
 *
 * Confirmation dialog before wiping a household from DynamoDB.
 *
 * UX contract:
 *   1. User clicks "Delete household" in the header.
 *   2. Modal opens with a plain-language warning.
 *   3. User must type the family name to unlock the confirm button.
 *   4. On confirm:
 *        a. Call DELETE /household/{id} (backend wipes all tables)
 *        b. onboardingStore.reset() (clear localStorage)
 *        c. dashboardService.clearCache()
 *        d. router.push("/onboard")
 *
 * The family-name confirmation guard prevents accidental wipes.
 */

import { useRef, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";
import { onboardingStore } from "@/lib/onboarding-store";
import { dashboardService } from "@/services/dashboard.service";
import { deleteHousehold } from "@/services/household.service";

interface DeleteHouseholdModalProps {
  householdId: string;
  familyName: string;
  onClose: () => void;
}

export function DeleteHouseholdModal({
  householdId,
  familyName,
  onClose,
}: DeleteHouseholdModalProps) {
  const router = useRouter();
  const [confirmText, setConfirmText] = useState("");
  const [status, setStatus] = useState<"idle" | "deleting" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the text field as soon as the modal opens
  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 80);
    return () => clearTimeout(timer);
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && status !== "deleting") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, status]);

  const confirmed = confirmText.trim().toLowerCase() === familyName.trim().toLowerCase();

  async function handleDelete() {
    if (!confirmed || status === "deleting") return;

    setStatus("deleting");
    setErrorMessage("");

    try {
      // 1. Wipe DynamoDB
      await deleteHousehold(householdId);

      // 2. Clear local state — both the cache and localStorage
      dashboardService.clearCache();
      onboardingStore.reset();

      // 3. Send the user to onboarding
      router.push("/onboard");
    } catch (err) {
      setStatus("error");
      setErrorMessage(err instanceof Error ? err.message : "Unknown error. Please try again.");
    }
  }

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && status !== "deleting") onClose();
      }}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        className="bg-white rounded-2xl shadow-xl border border-[#e5e7eb] w-full max-w-md overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-6 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#fef2f2] border border-[#fca5a5] flex items-center justify-center shrink-0">
              <AlertTriangle size={16} className="text-[#ef4444]" strokeWidth={2} />
            </div>
            <div>
              <h2 className="text-[15px] font-semibold text-[#111827]">Delete household</h2>
              <p className="text-[12px] text-[#9ca3af] mt-0.5">This cannot be undone</p>
            </div>
          </div>
          {status !== "deleting" && (
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-[#9ca3af] hover:text-[#374151] hover:bg-[#f3f4f6] transition-colors"
            >
              <X size={14} strokeWidth={2} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 pb-6 flex flex-col gap-4">
          {/* Warning block */}
          <div className="bg-[#fef2f2] border border-[#fca5a5] rounded-xl px-4 py-3">
            <p className="text-[13px] text-[#374151] leading-relaxed">
              This will permanently delete <strong className="text-[#111827]">all data</strong> for the{" "}
              <strong className="text-[#111827]">{familyName} household</strong> — including the knowledge
              graph, all learned patterns, promoted rules, action history, and reasoning logs.
            </p>
            <p className="text-[12px] text-[#6b7280] mt-2">
              You will be sent back to onboarding and must set up the household again from scratch.
            </p>
          </div>

          {/* What gets deleted */}
          <div className="flex flex-col gap-1.5">
            {[
              "Household knowledge graph",
              "All learned patterns and promoted rules",
              "Action log and notification history",
              "RTE audit log (reasoning decisions)",
              "Metrics and analytics data",
            ].map((item) => (
              <div key={item} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#ef4444] shrink-0" />
                <span className="text-[12px] text-[#374151]">{item}</span>
              </div>
            ))}
          </div>

          {/* Confirmation input */}
          <div>
            <label className="block text-[12px] font-medium text-[#374151] mb-1.5">
              Type <strong className="text-[#111827]">{familyName}</strong> to confirm
            </label>
            <input
              ref={inputRef}
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleDelete(); }}
              disabled={status === "deleting"}
              placeholder={familyName}
              className="w-full px-3 py-2 text-[13px] border rounded-xl outline-none transition-colors
                placeholder:text-[#d1d5db]
                disabled:bg-[#f9fafb] disabled:cursor-not-allowed
                focus:border-[#ef4444] focus:ring-2 focus:ring-[#fca5a5]/30"
              style={{
                borderColor: confirmText && !confirmed ? "#fca5a5" : "#e5e7eb",
              }}
            />
          </div>

          {/* Error */}
          {status === "error" && errorMessage && (
            <div className="bg-[#fef2f2] border border-[#fca5a5] rounded-xl px-3 py-2">
              <p className="text-[12px] text-[#ef4444]">{errorMessage}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              disabled={status === "deleting"}
              className="flex-1 px-4 py-2.5 rounded-xl border border-[#e5e7eb] text-[13px] font-medium text-[#374151]
                hover:bg-[#f9fafb] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={!confirmed || status === "deleting"}
              className="flex-1 px-4 py-2.5 rounded-xl text-[13px] font-semibold text-white transition-colors
                disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                backgroundColor: confirmed && status !== "deleting" ? "#ef4444" : "#fca5a5",
              }}
            >
              {status === "deleting" ? (
                <span className="flex items-center justify-center gap-2">
                  <motion.span
                    className="w-3 h-3 rounded-full border-2 border-white/40 border-t-white"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
                  />
                  Deleting…
                </span>
              ) : (
                "Delete household"
              )}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
