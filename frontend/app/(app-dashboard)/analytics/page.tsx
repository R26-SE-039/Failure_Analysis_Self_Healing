import StatusBadge from "@/components/status-badge";
import FlakyRiskChart from "@/components/flaky-risk-chart";
import { fetchFlakyTests } from "@/lib/api";
import { FlakyTest } from "@/lib/types";
import DeleteRecordButton from "@/components/delete-record-button";
import Link from "next/link";

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const limit = 10;

  const response = await fetchFlakyTests(page, limit);
  const isPaginated = !Array.isArray(response);
  const flakyTests: FlakyTest[] = isPaginated ? response.data : response;
  const total = isPaginated ? response.total : flakyTests.length;
  const totalPages = Math.ceil(total / limit);

  const totalTests = total;

  const numericScores = flakyTests
    .map((item) => parseInt(item.instability_score.replace("%", ""), 10))
    .filter((value) => !Number.isNaN(value));

  const averageScore =
    numericScores.length > 0
      ? Math.round(
          numericScores.reduce((sum, value) => sum + value, 0) /
            numericScores.length
        )
      : 0;

  const highRiskCount = flakyTests.filter(
    (item) => item.risk_level.toLowerCase() === "high"
  ).length;

  const riskDistribution = [
    {
      name: "High",
      value: flakyTests.filter((t) => t.risk_level.toLowerCase() === "high").length,
      color: "#ef4444",
    },
    {
      name: "Medium",
      value: flakyTests.filter((t) => t.risk_level.toLowerCase() === "medium").length,
      color: "#f59e0b",
    },
    {
      name: "Low",
      value: flakyTests.filter((t) => t.risk_level.toLowerCase() === "low").length,
      color: "#10b981",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="grid gap-5 md:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Predicted Flaky Tests</p>
          <h3 className="mt-2 text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">{totalTests}</h3>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Avg Instability Score</p>
          <h3 className="mt-2 text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">{averageScore}%</h3>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Predicted High Risk</p>
          <h3 className="mt-2 text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">{highRiskCount}</h3>
        </div>
      </div>

      <div className="grid gap-8 xl:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm xl:col-span-2">
          <div className="border-b border-[var(--border)] pb-4 mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-[var(--foreground)] tracking-tight">Flaky Test Prediction</h3>
              <p className="text-xs font-medium text-[var(--muted)]">
                Historical pass/fail trends used for predictive analysis
              </p>
            </div>
            <span className="text-xs font-bold bg-indigo-50 border border-indigo-100/50 text-indigo-700 rounded-full px-3 py-1">
              Live Analysis
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs font-bold text-[var(--muted)] uppercase tracking-wider">
                  <th className="py-3 px-1">Test ID</th>
                  <th className="py-3">Test Name</th>
                  <th className="py-3">Instability</th>
                  <th className="py-3">Pattern</th>
                  <th className="py-3">Risk Level</th>
                  <th className="py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {flakyTests.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50/50 transition duration-150"
                  >
                    <td className="py-4 text-xs font-mono font-bold text-indigo-600">{item.test_code}</td>
                    <td className="py-4 font-bold text-[var(--foreground)]">{item.test_name}</td>
                    <td className="py-4 font-bold text-slate-700">{item.instability_score}</td>
                    <td className="py-4 font-mono text-xs text-slate-500 bg-slate-50/60 p-1 rounded border border-slate-100/60 m-1">{item.recent_pattern}</td>
                    <td className="py-4">
                      <StatusBadge label={item.risk_level} type="risk" />
                    </td>
                    <td className="py-4">
                      <DeleteRecordButton endpoint="analytics/flaky-tests" recordId={item.test_code} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {flakyTests.length === 0 && (
              <p className="py-6 text-center text-sm font-medium text-[var(--muted)]">
                No flaky test analytics found.
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
                    href={`/analytics?page=${page - 1}`}
                    className={`rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-bold transition ${
                      page <= 1
                        ? "pointer-events-none opacity-50 bg-slate-50 text-[var(--muted)]"
                        : "hover:bg-[var(--card-2)] text-[var(--foreground)]"
                    }`}
                  >
                    Previous
                  </Link>
                  <Link
                    href={`/analytics?page=${page + 1}`}
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

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-lg font-bold tracking-tight border-b border-[var(--border)] pb-4 text-[var(--foreground)]">Risk Distribution</h3>
            <p className="text-xs font-medium text-[var(--muted)] mb-4">
              Predicted flaky test risk levels
            </p>
            <div className="mt-4">
              <FlakyRiskChart data={riskDistribution} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}