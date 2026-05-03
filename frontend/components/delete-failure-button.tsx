"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { deleteFailure } from "@/lib/api";

export default function DeleteFailureButton({ testId }: { testId: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this record? This action cannot be undone.")) return;
    
    setLoading(true);
    try {
      await deleteFailure(testId);
      router.refresh();
    } catch (e) {
      console.error(e);
      alert("Failed to delete failure");
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleDelete}
      disabled={loading}
      className="rounded-xl bg-red-50 text-red-600 px-3 py-2 text-xs font-bold hover:bg-red-100 hover:text-red-700 transition duration-150 border border-red-100/50 disabled:opacity-50 flex items-center gap-1.5"
      title="Delete record"
    >
      {loading ? (
        <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-red-600 border-t-transparent" />
      ) : (
        <Trash2 size={15} />
      )}
      Delete
    </button>
  );
}
