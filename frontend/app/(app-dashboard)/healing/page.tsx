import StatusBadge from "@/components/status-badge";
import { fetchHealingActions } from "@/lib/api";
import { HealingAction } from "@/lib/types";
import DeleteRecordButton from "@/components/delete-record-button";
import Link from "next/link";

export default async function HealingPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const limit = 10;

  const response = await fetchHealingActions(page, limit);
  const isPaginated = !Array.isArray(response);
  const healingActions: HealingAction[] = isPaginated ? response.data : response;
  const total = isPaginated ? response.total : healingActions.length;
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
      <div className="border-b border-[var(--border)] pb-4 mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-[var(--foreground)] tracking-tight">
            Self-Healing Recommendations
          </h3>
          <p className="text-xs font-medium text-[var(--muted)]">
            Proposed repair actions for unstable or failed test scripts
          </p>
        </div>
        <span className="text-xs font-bold bg-emerald-50 border border-emerald-100/50 text-emerald-700 rounded-full px-3 py-1">
          Automated
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs font-bold text-[var(--muted)] uppercase tracking-wider">
              <th className="py-3 px-1">Healing ID</th>
              <th className="py-3">Failure ID</th>
              <th className="py-3">Test Name</th>
              <th className="py-3">Repair Type</th>
              <th className="py-3">Old Value</th>
              <th className="py-3">New Value</th>
              <th className="py-3">Status</th>
              <th className="py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {healingActions.map((item) => (
              <tr
                key={item.id}
                className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50/50 transition duration-150"
              >
                <td className="py-4 text-xs font-mono font-bold text-indigo-600">{item.healing_id}</td>
                <td className="py-4 text-xs font-mono text-[var(--muted)]">{item.failure_test_id}</td>
                <td className="py-4 font-bold text-[var(--foreground)]">{item.test_name}</td>
                <td className="py-4 text-xs font-medium text-slate-700">{item.repair_type}</td>
                <td className="py-4 text-xs font-mono bg-slate-50/50 p-1 rounded border border-slate-100 m-1 max-w-xs truncate" title={item.old_value}>{item.old_value}</td>
                <td className="py-4 text-xs font-mono bg-emerald-50/40 p-1 rounded border border-emerald-100/40 m-1 max-w-xs truncate text-emerald-800" title={item.new_value}>{item.new_value}</td>
                <td className="py-4">
                  <StatusBadge label={item.status} type="healing" />
                </td>
                <td className="py-4">
                  <DeleteRecordButton endpoint="healing" recordId={item.healing_id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {healingActions.length === 0 && (
          <p className="py-6 text-center text-sm font-medium text-[var(--muted)]">
            No healing actions found.
          </p>
        )}

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-[var(--border)] pt-4 mt-4">
            <span className="text-xs font-bold text-[var(--muted)]">
              Showing page {page} of {totalPages} ({total} total records)
            </span>
            <div className="flex gap-2">
              <Link
                href={`/healing?page=${page - 1}`}
                className={`rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-bold transition ${
                  page <= 1
                    ? "pointer-events-none opacity-50 bg-slate-50 text-[var(--muted)]"
                    : "hover:bg-[var(--card-2)] text-[var(--foreground)]"
                }`}
              >
                Previous
              </Link>
              <Link
                href={`/healing?page=${page + 1}`}
                className={`rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-bold transition ${
                  page >= totalPages
                    ? "pointer-events-none opacity-50 bg-slate-50 text-[var(--muted)]"
                    : "hover:bg-[var(--card-2)] text-[var(--foreground)]"
                }`}
              >
                Next
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}