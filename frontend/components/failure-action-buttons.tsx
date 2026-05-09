"use client";

import { useState } from "react";
import { Failure } from "@/lib/types";
import { Check, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export default function FailureActionButtons({ failure }: { failure: Failure }) {
  const router = useRouter();
  const [healingStatus, setHealingStatus] = useState<"idle" | "loading" | "success">("idle");
  const [notifyStatus, setNotifyStatus] = useState<"idle" | "loading" | "success">("idle");

  const canHeal = failure.healing === "Suggested";
  const isDevAlert = failure.developer_alert;

  const handleApplyHealing = async () => {
    setHealingStatus("loading");
    
    try {
      // Actually hit the backend to update the status in the DB
      await fetch(`${API_BASE}/failures/${failure.test_id}/heal`, {
        method: "PATCH",
      });
      
      setHealingStatus("success");
      
      // Refresh the page data from the server so the status changes from FAIL to HEALED
      router.refresh();
      
      setTimeout(() => setHealingStatus("idle"), 3000);
    } catch (error) {
      setHealingStatus("idle");
      console.error("Failed to apply healing:", error);
    }
  };

  const handleNotifyDeveloper = async () => {
    setNotifyStatus("loading");
    // Simulate API call to send Slack/Email notification
    await new Promise((resolve) => setTimeout(resolve, 1500));
    setNotifyStatus("success");
    setTimeout(() => setNotifyStatus("idle"), 3000);
  };

  return (
    <div className="mt-6 flex gap-3">
      <button
        onClick={handleApplyHealing}
        disabled={!canHeal || healingStatus !== "idle"}
        className={`flex items-center gap-2 rounded-lg px-4 py-2 text-white transition ${
          failure.healing !== "Rejected" && failure.healing
            ? healingStatus === "success" || failure.healing === "Applied"
              ? "bg-green-600"
              : "bg-blue-600 hover:bg-blue-700"
            : "cursor-not-allowed border border-[var(--border)] bg-[var(--card-2)] text-[var(--muted)] opacity-50"
        }`}
      >
        {healingStatus === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
        {healingStatus === "success" && <Check className="h-4 w-4" />}
        {healingStatus === "success" || failure.healing === "Applied" ? "Healing Applied" : "Apply Healing"}
      </button>

      <button
        onClick={handleNotifyDeveloper}
        disabled={!isDevAlert || notifyStatus !== "idle"}
        className={`flex items-center gap-2 rounded-lg px-4 py-2 text-white transition ${
          isDevAlert
            ? notifyStatus === "success"
              ? "bg-green-600"
              : "bg-[var(--danger)] hover:opacity-90"
            : "cursor-not-allowed border border-[var(--border)] bg-[var(--card-2)] text-[var(--muted)] opacity-50"
        }`}
      >
        {notifyStatus === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
        {notifyStatus === "success" && <Check className="h-4 w-4" />}
        {notifyStatus === "success" ? "Developer Notified" : "Notify Developer"}
      </button>
    </div>
  );
}
