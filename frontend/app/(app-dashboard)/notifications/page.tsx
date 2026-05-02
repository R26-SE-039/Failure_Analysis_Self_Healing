import { fetchNotifications } from "@/lib/api";
import { Notification } from "@/lib/types";

export default async function NotificationsPage() {
  const notifications: Notification[] = await fetchNotifications();

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
      <h3 className="text-lg font-semibold">Developer Notifications</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Failures that likely require developer or environment-level attention
      </p>

      <div className="mt-4 space-y-4">
        {notifications.map((item) => (
          <div
            key={item.id}
            className="rounded-xl border border-[var(--border)] bg-[var(--card-2)] p-4"
          >
            <h4 className="text-base font-semibold">{item.test_name}</h4>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Failure ID: {item.failure_test_id}
            </p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Root Cause: {item.root_cause}
            </p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Target: {item.target}
            </p>
            <p className="mt-2 text-sm">{item.message}</p>
          </div>
        ))}

        {notifications.length === 0 && (
          <p className="text-sm text-[var(--muted)]">
            No developer alerts at the moment.
          </p>
        )}
      </div>
    </div>
  );
}