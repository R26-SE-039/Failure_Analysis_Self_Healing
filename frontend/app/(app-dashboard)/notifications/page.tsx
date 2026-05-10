import { fetchNotifications } from "@/lib/api";
import { Notification } from "@/lib/types";
import { Send, AlertTriangle, Mail, MessageSquare, GitBranch } from "lucide-react";
import DeleteRecordButton from "@/components/delete-record-button";
import Link from "next/link";

export default async function AlertOutboxPage({
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
    <div className="space-y-6">

      {/* Page Header */}
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-[var(--foreground)]">Alert Outbox</h2>
        <p className="text-xs font-medium text-[var(--muted)] mt-1">
          Dispatched alerts for failures the self-healing engine could not repair automatically
        </p>
      </div>

      {/* Future Delivery Channels Banner */}
      <div className="rounded-2xl border border-dashed border-indigo-200 bg-indigo-50/40 p-5">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0 mt-0.5">
            <AlertTriangle size={15} className="text-indigo-600" />
          </div>
          <div>
            <p className="text-sm font-bold text-indigo-800">Delivery Channels — Planned for Future Release</p>
            <p className="text-xs font-medium text-indigo-600 mt-0.5">
              The system currently logs alerts internally. Outbound delivery integrations are under development.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                { label: "Email Alerts", icon: Mail },
                { label: "Slack Notifications", icon: MessageSquare },
                { label: "Jira Issue Creation", icon: GitBranch },
              ].map(({ label, icon: Icon }) => (
                <span
                  key={label}
                  className="flex items-center gap-1.5 text-xs font-bold text-indigo-700 bg-white border border-indigo-100 rounded-xl px-3 py-1.5 shadow-sm"
                >
                  <Icon size={12} />
                  {label}
                  <span className="ml-1 text-[10px] font-bold text-indigo-400 uppercase tracking-wide">Soon</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Alerts Table */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
        <div className="border-b border-[var(--border)] pb-4 mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight">
              Dispatched Developer Alerts
            </h3>
            <p className="text-xs font-medium text-[var(--muted)]">
              Application-level defects requiring developer attention
            </p>
          </div>
          <span className="text-xs font-bold bg-amber-50 border border-amber-100/50 text-amber-700 rounded-full px-3 py-1 flex items-center gap-1">
            <Send size={12} />
            {total} Sent
          </span>
        </div>

        <div className="mt-4 space-y-4">
          {notifications.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card-2)] p-5 transition hover:border-amber-100 flex flex-col gap-2 relative overflow-hidden"
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
                  Root Cause: <span className="font-bold text-slate-700">{item.root_cause}</span>
                </p>
              </div>
              <p className="mt-2 text-sm text-[var(--foreground)] font-medium leading-relaxed bg-white/60 p-3 rounded-xl border border-[var(--border)]/30">
                {item.message}
              </p>
            </div>
          ))}

          {notifications.length === 0 && (
            <div className="py-12 text-center">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-100 flex items-center justify-center mx-auto mb-3">
                <Send size={20} className="text-emerald-500" />
              </div>
              <p className="text-sm font-bold text-[var(--foreground)]">No alerts dispatched yet.</p>
              <p className="text-xs text-[var(--muted)] font-medium mt-1">The self-healing engine resolved all failures automatically.</p>
            </div>
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
    </div>
  );
}