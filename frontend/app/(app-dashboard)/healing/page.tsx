import StatusBadge from "@/components/status-badge";
import { fetchHealingActions } from "@/lib/api";
import { HealingAction } from "@/lib/types";

export default async function HealingPage() {
  const healingActions: HealingAction[] = await fetchHealingActions();

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
              </tr>
            ))}
          </tbody>
        </table>

        {healingActions.length === 0 && (
          <p className="py-6 text-center text-sm font-medium text-[var(--muted)]">
            No healing actions found.
          </p>
        )}
      </div>
    </div>
  );
}