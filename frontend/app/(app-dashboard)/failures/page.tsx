import Link from "next/link";
import StatusBadge from "@/components/status-badge";
import { fetchFailures } from "@/lib/api";
import { Failure } from "@/lib/types";

export default async function FailuresPage() {
  const failures: Failure[] = await fetchFailures();

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
      <h3 className="text-lg font-semibold">Failed Test Cases</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        View recent failed tests and inspect root cause analysis
      </p>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-[var(--muted)]">
              <th className="py-3">ID</th>
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
                className="border-b border-[var(--border)] last:border-0"
              >
                <td className="py-3">{item.test_id}</td>
                <td className="py-3">{item.test_name}</td>
                <td className="py-3">{item.pipeline}</td>
                <td className="py-3">
                  <StatusBadge label={item.root_cause} type="rootCause" />
                </td>
                <td className="py-3">
                  <StatusBadge label={item.status} type="status" />
                </td>
                <td className="py-3">
                  <StatusBadge label={item.healing || "None"} type="healing" />
                </td>
                <td className="py-3">
                  <Link
                    href={`/failures/${item.test_id}`}
                    className="rounded-lg bg-[var(--accent)] px-3 py-2 text-white"
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {failures.length === 0 && (
          <p className="mt-4 text-sm text-[var(--muted)]">
            No failure records found.
          </p>
        )}
      </div>
    </div>
  );
}