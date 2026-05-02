import StatCard from "@/components/stat-card";
import StatusBadge from "@/components/status-badge";
import { fetchDashboardSummary } from "@/lib/api";
import { DashboardSummary } from "@/lib/types";

export default async function HomePage() {
  const summary: DashboardSummary = await fetchDashboardSummary();

  const dashboardStats = [
    {
      title: "Total Failures",
      value: String(summary.total_failures),
      change: "Live data",
    },
    {
      title: "Healing Actions",
      value: String(summary.total_healing_actions),
      change: "Live data",
    },
    {
      title: "Flaky Tests",
      value: String(summary.total_flaky_tests),
      change: "Live data",
    },
    {
      title: "Notifications",
      value: String(summary.total_notifications),
      change: "Live data",
    },
  ];

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {dashboardStats.map((stat) => (
          <StatCard
            key={stat.title}
            title={stat.title}
            value={stat.value}
            change={stat.change}
          />
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 xl:col-span-2">
          <h3 className="text-lg font-semibold">Recent Failures</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Latest failures loaded from backend
          </p>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-[var(--muted)]">
                  <th className="py-3">Test</th>
                  <th className="py-3">Pipeline</th>
                  <th className="py-3">Root Cause</th>
                  <th className="py-3">Status</th>
                  <th className="py-3">Healing</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_failures.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-[var(--border)] last:border-0"
                  >
                    <td className="py-3">{item.test_name}</td>
                    <td className="py-3">{item.pipeline}</td>
                    <td className="py-3">
                      <StatusBadge label={item.root_cause} type="rootCause" />
                    </td>
                    <td className="py-3">
                      <StatusBadge label={item.status} type="status" />
                    </td>
                    <td className="py-3">
                      <StatusBadge
                        label={item.healing || "None"}
                        type="healing"
                      />
                    </td>
                  </tr>
                ))}

                {summary.recent_failures.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="py-4 text-sm text-[var(--muted)]"
                    >
                      No recent failures found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="text-lg font-semibold">System Summary</h3>
          <div className="mt-4 space-y-4 text-sm">
            <div className="rounded-xl bg-[var(--card-2)] p-4">
              <p className="text-[var(--muted)]">Failure Records</p>
              <p className="mt-1 text-2xl font-bold">
                {summary.total_failures}
              </p>
            </div>

            <div className="rounded-xl bg-[var(--card-2)] p-4">
              <p className="text-[var(--muted)]">Healing Records</p>
              <p className="mt-1 text-2xl font-bold">
                {summary.total_healing_actions}
              </p>
            </div>

            <div className="rounded-xl bg-[var(--card-2)] p-4">
              <p className="text-[var(--muted)]">Flaky Test Records</p>
              <p className="mt-1 text-2xl font-bold">
                {summary.total_flaky_tests}
              </p>
            </div>

            <div className="rounded-xl bg-[var(--card-2)] p-4">
              <p className="text-[var(--muted)]">Notification Records</p>
              <p className="mt-1 text-2xl font-bold">
                {summary.total_notifications}
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}