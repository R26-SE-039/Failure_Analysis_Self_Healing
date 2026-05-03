import { ShieldCheck } from "lucide-react";

export default function Topbar() {
  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--card)] px-8 py-5 shadow-sm">
      <div>
        <h2 className="text-xl font-extrabold tracking-tight text-[var(--foreground)]">
          Failure Analysis Dashboard
        </h2>
        <p className="text-xs font-medium text-[var(--muted)]">
          Monitor failures, healing actions, and flaky tests
        </p>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 rounded-2xl bg-[var(--card-2)] border border-[var(--border)] px-4 py-2 text-xs font-bold text-indigo-700 shadow-sm transition hover:bg-indigo-50">
          <ShieldCheck size={16} className="text-indigo-600 animate-pulse" />
          Enterprise Verified
        </div>
      </div>
    </div>
  );
}