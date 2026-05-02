import StatusBadge from "@/components/status-badge";
import { fetchHealingActions } from "@/lib/api";
import { HealingAction } from "@/lib/types";

export default async function HealingPage() {
  const healingActions: HealingAction[] = await fetchHealingActions();

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
      <h3 className="text-lg font-semibold">Self-Healing Recommendations</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Proposed repair actions for unstable or failed test scripts
      </p>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-[var(--muted)]">
              <th className="py-3">Healing ID</th>
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
                className="border-b border-[var(--border)] last:border-0"
              >
                <td className="py-3">{item.healing_id}</td>
                <td className="py-3">{item.failure_test_id}</td>
                <td className="py-3">{item.test_name}</td>
                <td className="py-3">{item.repair_type}</td>
                <td className="py-3">{item.old_value}</td>
                <td className="py-3">{item.new_value}</td>
                <td className="py-3">
                  <StatusBadge label={item.status} type="healing" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {healingActions.length === 0 && (
          <p className="mt-4 text-sm text-[var(--muted)]">
            No healing actions found.
          </p>
        )}
      </div>
    </div>
  );
}