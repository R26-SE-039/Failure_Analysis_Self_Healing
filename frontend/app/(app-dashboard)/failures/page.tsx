import Link from "next/link";
import StatusBadge from "@/components/status-badge";
import { fetchFailures } from "@/lib/api";
import { Failure } from "@/lib/types";
import DeleteFailureButton from "@/components/delete-failure-button";

export default async function FailuresPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const limit = 10;
  
  const response = await fetchFailures(page, limit);
  // Ensure we safely handle the case where backend returns list vs paginated dict
  const isPaginated = !Array.isArray(response);
  const failures: Failure[] = isPaginated ? response.data : response;
  const total = isPaginated ? response.total : failures.length;
  const totalPages = Math.ceil(total / limit);

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
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/failures/${item.test_id}`}
                      className="rounded-xl bg-indigo-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-indigo-700 hover:shadow-sm transition-all shadow-indigo-500/10"
                    >
                      View Details
                    </Link>
                    <DeleteFailureButton testId={item.test_id} />
                  </div>
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

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-[var(--border)] pt-4 mt-4">
            <span className="text-xs font-bold text-[var(--muted)]">
              Showing page {page} of {totalPages} ({total} total records)
            </span>
            <div className="flex gap-2">
              <Link
                href={`/failures?page=${page - 1}`}
                className={`rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-bold transition ${
                  page <= 1
                    ? "pointer-events-none opacity-50 bg-slate-50 text-[var(--muted)]"
                    : "hover:bg-[var(--card-2)] text-[var(--foreground)]"
                }`}
              >
                Previous
              </Link>
              <Link
                href={`/failures?page=${page + 1}`}
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