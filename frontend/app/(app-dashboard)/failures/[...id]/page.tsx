import Link from "next/link";
import { fetchFailureById } from "@/lib/api";
import { Failure } from "@/lib/types";
import FailureActionButtons from "@/components/failure-action-buttons";
import { ArrowLeft, ShieldCheck, AlertCircle, FileText, Database } from "lucide-react";

type FailureDetailsPageProps = {
  params: Promise<{
    id: string | string[];
  }>;
};

export default async function FailureDetailsPage({
  params,
}: FailureDetailsPageProps) {
  const { id } = await params;
  const failureId = Array.isArray(id) ? id.join("/") : id;

  let failure: Failure | null = null;

  try {
    failure = await fetchFailureById(failureId);
  } catch {
    failure = null;
  }

  if (!failure) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-sm text-center max-w-xl mx-auto my-12">
        <div className="text-4xl mb-4">🔍</div>
        <h2 className="text-2xl font-extrabold tracking-tight text-[var(--foreground)]">Failure not found</h2>
        <p className="text-xs font-medium text-[var(--muted)] mt-1 mb-6">We couldn't retrieve the failure log for ID: {failureId}</p>
        <Link
          href="/failures"
          className="inline-flex items-center gap-2 font-bold text-indigo-600 hover:text-indigo-700 bg-indigo-50 border border-indigo-100/50 hover:bg-indigo-100/50 px-5 py-2.5 rounded-xl transition shadow-sm text-xs"
        >
          <ArrowLeft size={14} />
          Back to failures
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 mb-4">
        <div>
          <h2 className="text-2xl font-extrabold tracking-tight text-[var(--foreground)]">{failure.test_name}</h2>
          <p className="text-xs font-medium text-[var(--muted)]">
            Failure ID: <span className="font-mono font-bold text-indigo-600">{failure.test_id}</span>
          </p>
        </div>

        <Link
          href="/failures"
          className="rounded-xl border border-[var(--border)] bg-[var(--card-2)] px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 hover:shadow-sm transition flex items-center gap-1.5"
        >
          <ArrowLeft size={13} />
          Back to List
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 mb-4">
              <ShieldCheck size={16} className="text-indigo-600" />
              <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight">Test Metadata</h3>
            </div>
            <div className="space-y-3 text-sm">
              <p className="flex justify-between border-b border-slate-50 pb-2">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wide">Pipeline</span>
                <span className="text-xs font-bold text-slate-800">{failure.pipeline}</span>
              </p>
              <p className="flex justify-between border-b border-slate-50 pb-2">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wide">Status</span>
                <span className="text-xs font-bold text-red-600 uppercase tracking-wider bg-red-50/50 px-2 py-0.5 rounded border border-red-100/40">{failure.status}</span>
              </p>
              <p className="flex justify-between border-b border-slate-50 pb-2">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wide">Root Cause</span>
                <span className="text-xs font-bold text-amber-600 uppercase tracking-wider bg-amber-50/50 px-2 py-0.5 rounded border border-amber-100/40">{failure.root_cause}</span>
              </p>
              <p className="flex justify-between border-b border-slate-50 pb-2">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wide">Healing</span>
                <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider bg-emerald-50/50 px-2 py-0.5 rounded border border-emerald-100/40">{failure.healing || "None"}</span>
              </p>
              <p className="flex justify-between">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wide">ML Confidence</span>
                <span className="text-xs font-bold text-indigo-700 bg-indigo-50/50 px-2 py-0.5 rounded border border-indigo-100/40">{failure.confidence || "N/A"}</span>
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm lg:col-span-2 relative overflow-hidden flex flex-col justify-between">
          <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-indigo-500 to-indigo-600" />
          <div>
            <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 mb-4">
              <AlertCircle size={16} className="text-indigo-600" />
              <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight">AI Generated Recommendation</h3>
            </div>
            <p className="text-sm font-medium leading-relaxed bg-slate-50 p-4 rounded-2xl border border-slate-100 text-[var(--foreground)]">
              {failure.recommendation || "No recommendation available."}
            </p>
          </div>

          <div className="pt-4 mt-auto">
            <FailureActionButtons failure={failure} />
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 mb-4">
            <FileText size={16} className="text-indigo-600" />
            <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight">Console Execution Logs</h3>
          </div>
          <pre className="flex-1 rounded-2xl bg-[var(--card-2)] p-4 text-xs font-mono font-medium text-slate-700 overflow-x-auto leading-relaxed border border-[var(--border)]/30 min-h-[140px] max-h-[300px] whitespace-pre-wrap">
            {failure.logs || "No logs available."}
          </pre>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 mb-4">
            <Database size={16} className="text-indigo-600" />
            <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight">Full Failure Stack Trace</h3>
          </div>
          <pre className="flex-1 rounded-2xl bg-[var(--card-2)] p-4 text-xs font-mono font-medium text-slate-700 overflow-x-auto leading-relaxed border border-[var(--border)]/30 min-h-[140px] max-h-[300px] whitespace-pre-wrap">
            {failure.stack_trace || "No stack trace available."}
          </pre>
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-amber-500" />
        <h3 className="text-base font-bold text-[var(--foreground)] tracking-tight border-b border-[var(--border)] pb-3 mb-4 flex items-center gap-2">
          Developer Insights & Recommended Escalation
        </h3>
        <p className="text-xs font-medium text-slate-700 leading-relaxed bg-slate-50/50 border border-slate-100 p-3 rounded-xl max-w-fit">
          {failure.developer_alert
            ? "🔔 High priority: This failure looks like an application or environment issue. Immediate developer notification/escalation is recommended."
            : "✓ Low priority: This failure looks repairable at test-script level. Automatic healing can be attempted first."}
        </p>
      </div>
    </div>
  );
}