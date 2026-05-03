import Link from "next/link";
import StatusBadge from "@/components/status-badge";
import { fetchFailures } from "@/lib/api";
import { Failure } from "@/lib/types";

export default async function FailuresPage() {
  const failures: Failure[] = await fetchFailures();

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
      <div className="border-b border-[var(--border)] pb-4 mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-[var(--foreground)] tracking-tight">
            Failed Test Cases
          </h3>
          <p className="text-xs font-medium text-[var(--muted)]">
            View recent failed tests and inspect root cause analysis
          </p>
        </div>
        <span className="text-xs font-bold bg-indigo-50 border border-indigo-100/50 text-indigo-700 rounded-full px-3 py-1">
          Real-time
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs font-bold text-[var(--muted)] uppercase tracking-wider">
              <th className="py-3 px-1">Test ID</th>
              <th className="py-3">Test Name</th>
              <th className="py-3">Pipeline</th>
              <th className="py-3">Root Cause</th>
              <th className="py-3">Status</th>
              <th className="py-3">Healing</th>
              <th className="py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {failures.map((item) => (
              <tr
                key={item.id}
                className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50/50 transition duration-150"
              >
                <td className="py-4 text-xs font-mono font-bold text-indigo-600">{item.test_id}</td>
                <td className="py-4 font-bold text-[var(--foreground)]">{item.test_name}</td>
                <td className="py-4 text-xs font-medium text-[var(--muted)]">{item.pipeline}</td>
                <td className="py-4">
                  <StatusBadge label={item.root_cause} type="rootCause" />
                </td>
                <td className="py-4">
                  <StatusBadge label={item.status} type="status" />
                </td>
                <td className="py-4">
                  <StatusBadge label={item.healing || "None"} type="healing" />
                </td>
                <td className="py-4">
                  <Link
                    href={`/failures/${item.test_id}`}
                    className="rounded-xl bg-indigo-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-indigo-700 hover:shadow-sm transition-all shadow-indigo-500/10"
                  >
                    View Details
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {failures.length === 0 && (
          <p className="py-6 text-center text-sm font-medium text-[var(--muted)]">
            No failure records found.
          </p>
        )}
      </div>
    </div>
  );
}