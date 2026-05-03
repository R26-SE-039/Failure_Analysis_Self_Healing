import { fetchNotifications } from "@/lib/api";
import { Notification } from "@/lib/types";
import { BellRing } from "lucide-react";
import DeleteRecordButton from "@/components/delete-record-button";
import Link from "next/link";

export default async function NotificationsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const limit = 10;

  const response = await fetchNotifications(page, limit);
  const isPaginated = !Array.isArray(response);
  const notifications: Notification[] = isPaginated ? response.data : response;
  const total = isPaginated ? response.total : notifications.length;
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
      <div className="border-b border-[var(--border)] pb-4 mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-[var(--foreground)] tracking-tight">
            Developer Notifications
          </h3>
          <p className="text-xs font-medium text-[var(--muted)]">
            Failures that likely require developer or environment-level attention
          </p>
        </div>
        <span className="text-xs font-bold bg-amber-50 border border-amber-100/50 text-amber-700 rounded-full px-3 py-1 flex items-center gap-1">
          <BellRing size={12} className="animate-bounce" />
          Alerts
        </span>
      </div>

      <div className="mt-6 space-y-4">
        {notifications.map((item) => (
          <div
            key={item.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--card-2)] p-5 transition hover:border-indigo-100 flex flex-col gap-2 relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 w-1 h-full bg-amber-500/80" />
            <div className="flex justify-between items-start">
              <h4 className="text-base font-bold text-[var(--foreground)]">{item.test_name}</h4>
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-xl border border-amber-100/50">
                  {item.target}
                </span>
                <DeleteRecordButton endpoint="notifications" recordId={item.id} />
              </div>
            </div>
            <div className="grid md:grid-cols-2 gap-2 text-xs font-medium text-[var(--muted)] mt-1">
              <p>
                Failure ID: <span className="font-mono text-indigo-600 font-bold">{item.failure_test_id}</span>
              </p>
              <p>
                Predicted Root Cause: <span className="font-bold text-slate-700">{item.root_cause}</span>
              </p>
            </div>
            <p className="mt-2 text-sm text-[var(--foreground)] font-medium leading-relaxed bg-white/60 p-3 rounded-xl border border-[var(--border)]/30">
              {item.message}
            </p>
          </div>
        ))}

        {notifications.length === 0 && (
          <p className="py-6 text-center text-sm font-medium text-[var(--muted)]">
            No developer alerts at the moment.
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
                href={`/notifications?page=${page - 1}`}
                className={`rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-bold transition ${
                  page <= 1
                    ? "pointer-events-none opacity-50 bg-slate-50 text-[var(--muted)]"
                    : "hover:bg-[var(--card-2)] text-[var(--foreground)]"
                }`}
              >
                Previous
              </Link>
              <Link
                href={`/notifications?page=${page + 1}`}
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