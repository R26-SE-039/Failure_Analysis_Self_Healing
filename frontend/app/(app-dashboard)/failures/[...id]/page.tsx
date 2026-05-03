import Link from "next/link";
import { fetchFailureById } from "@/lib/api";
import { Failure } from "@/lib/types";
import FailureActionButtons from "@/components/failure-action-buttons";

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
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8">
        <h2 className="text-2xl font-bold">Failure not found</h2>
        <Link
          href="/failures"
          className="mt-4 inline-block text-[var(--accent)]"
        >
          Back to failures
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{failure.test_name}</h2>
          <p className="text-sm text-[var(--muted)]">
            Failure ID: {failure.test_id}
          </p>
        </div>

        <Link
          href="/failures"
          className="rounded-lg border border-[var(--border)] px-4 py-2"
        >
          Back
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="text-lg font-semibold">Test Metadata</h3>
          <div className="mt-4 space-y-3 text-sm">
            <p>
              <span className="text-[var(--muted)]">Pipeline:</span>{" "}
              {failure.pipeline}
            </p>
            <p>
              <span className="text-[var(--muted)]">Status:</span>{" "}
              {failure.status}
            </p>
            <p>
              <span className="text-[var(--muted)]">Root Cause:</span>{" "}
              {failure.root_cause}
            </p>
            <p>
              <span className="text-[var(--muted)]">Healing:</span>{" "}
              {failure.healing || "None"}
            </p>
            <p>
              <span className="text-[var(--muted)]">ML Confidence:</span>{" "}
              {failure.confidence || "N/A"}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 lg:col-span-2">
          <h3 className="text-lg font-semibold">Recommendation</h3>
          <p className="mt-4 text-sm text-[var(--foreground)]">
            {failure.recommendation || "No recommendation available."}
          </p>

          <FailureActionButtons failure={failure} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="text-lg font-semibold">Execution Logs</h3>
          <div className="mt-4 rounded-xl bg-[var(--card-2)] p-4 text-sm text-[var(--muted)]">
            {failure.logs || "No logs available."}
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="text-lg font-semibold">Stack Trace</h3>
          <div className="mt-4 rounded-xl bg-[var(--card-2)] p-4 text-sm text-[var(--muted)]">
            {failure.stack_trace || "No stack trace available."}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <h3 className="text-lg font-semibold">Developer Alert</h3>
        <p className="mt-4 text-sm">
          {failure.developer_alert
            ? "This failure looks like an application or environment issue. Developer notification is recommended."
            : "This failure looks repairable at test-script level. Automatic healing can be attempted first."}
        </p>
      </div>
    </div>
  );
}