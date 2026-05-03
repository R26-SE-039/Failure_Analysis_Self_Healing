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
      change: "Live updates",
    },
    {
      title: "Healing Actions",
      value: String(summary.total_healing_actions),
      change: "Auto-suggested",
    },
    {
      title: "Flaky Tests",
      value: String(summary.total_flaky_tests),
      change: "Heuristics",
    },
    {
      title: "Notifications",
      value: String(summary.total_notifications),
      change: "Slack & Email",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {dashboardStats.map((stat) => (
          <StatCard
            key={stat.title}
            title={stat.title}
            value={stat.value}
            change={stat.change}
          />
        ))}
      </div>

      <div className="grid gap-8 xl:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 mb-4">
            <div>
              <h3 className="text-lg font-bold text-[var(--foreground)] tracking-tight">Recent Failures</h3>
              <p className="text-xs font-medium text-[var(--muted)]">Latest pipeline failure records</p>
            </div>
            <span className="text-xs font-bold bg-indigo-50 border border-indigo-100/50 text-indigo-700 rounded-full px-3 py-1">
              Live
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs font-bold text-[var(--muted)] uppercase tracking-wider">
                  <th className="py-3 px-1">Test Name</th>
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
                    className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50/50 transition duration-150"
                  >
                    <td className="py-4 font-bold text-[var(--foreground)]">{item.test_name}</td>
                    <td className="py-4 text-xs font-medium text-[var(--muted)]">{item.pipeline}</td>
                    <td className="py-4">
                      <StatusBadge label={item.root_cause} type="rootCause" />
                    </td>
                    <td className="py-4">
                      <StatusBadge label={item.status} type="status" />
                    </td>
                    <td className="py-4">
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
                      className="py-6 text-center text-sm font-medium text-[var(--muted)]"
                    >
                      No recent failures recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-lg font-bold tracking-tight border-b border-[var(--border)] pb-4 text-[var(--foreground)]">
              System Metrics
            </h3>
            <div className="mt-5 space-y-4 text-sm flex-1">
              <div className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)]/50 transition hover:border-indigo-100 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Failures</p>
                  <p className="mt-1 text-2xl font-extrabold text-[var(--foreground)]">
                    {summary.total_failures}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-red-100/60 border border-red-100 flex items-center justify-center text-red-600 font-extrabold text-xs">
                  FL
                </div>
              </div>

              <div className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)]/50 transition hover:border-indigo-100 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Healing</p>
                  <p className="mt-1 text-2xl font-extrabold text-[var(--foreground)]">
                    {summary.total_healing_actions}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-emerald-100/60 border border-emerald-100 flex items-center justify-center text-emerald-600 font-extrabold text-xs">
                  HL
                </div>
              </div>

              <div className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)]/50 transition hover:border-indigo-100 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Flaky Tests</p>
                  <p className="mt-1 text-2xl font-extrabold text-[var(--foreground)]">
                    {summary.total_flaky_tests}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-amber-100/60 border border-amber-100 flex items-center justify-center text-amber-600 font-extrabold text-xs">
                  FK
                </div>
              </div>

              <div className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)]/50 transition hover:border-indigo-100 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Alerts Sent</p>
                  <p className="mt-1 text-2xl font-extrabold text-[var(--foreground)]">
                    {summary.total_notifications}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-indigo-100/60 border border-indigo-100 flex items-center justify-center text-indigo-600 font-extrabold text-xs">
                  AL
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}