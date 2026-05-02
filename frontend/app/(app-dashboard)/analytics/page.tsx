import StatusBadge from "@/components/status-badge";
import FlakyRiskChart from "@/components/flaky-risk-chart";
import { fetchFlakyTests } from "@/lib/api";
import { FlakyTest } from "@/lib/types";

export default async function AnalyticsPage() {
  const flakyTests: FlakyTest[] = await fetchFlakyTests();

  const totalTests = flakyTests.length;

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

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <p className="text-sm text-[var(--muted)]">Predicted Flaky Tests</p>
          <h3 className="mt-2 text-3xl font-bold">{totalTests}</h3>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <p className="text-sm text-[var(--muted)]">Avg Instability Score</p>
          <h3 className="mt-2 text-3xl font-bold">{averageScore}%</h3>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <p className="text-sm text-[var(--muted)]">Predicted High Risk Cases</p>
          <h3 className="mt-2 text-3xl font-bold">{highRiskCount}</h3>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 xl:col-span-2">
          <h3 className="text-lg font-semibold">Flaky Test Prediction</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Historical pass/fail trends used for predictive analysis
          </p>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-[var(--muted)]">
                  <th className="py-3">Test ID</th>
                  <th className="py-3">Test Name</th>
                  <th className="py-3">Instability Score</th>
                  <th className="py-3">Recent Pattern</th>
                  <th className="py-3">Risk Level</th>
                </tr>
              </thead>
              <tbody>
                {flakyTests.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-[var(--border)] last:border-0"
                  >
                    <td className="py-3">{item.test_code}</td>
                    <td className="py-3">{item.test_name}</td>
                    <td className="py-3">{item.instability_score}</td>
                    <td className="py-3">{item.recent_pattern}</td>
                    <td className="py-3">
                      <StatusBadge label={item.risk_level} type="risk" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {flakyTests.length === 0 && (
              <p className="mt-4 text-sm text-[var(--muted)]">
                No flaky test analytics found.
              </p>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="text-lg font-semibold">Risk Distribution</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Predicted flaky test risk levels
          </p>
          <div className="mt-4">
            <FlakyRiskChart />
          </div>
        </div>
      </div>
    </div>
  );
}