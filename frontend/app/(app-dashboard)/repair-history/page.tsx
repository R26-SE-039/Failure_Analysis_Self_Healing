import { Filter, RotateCcw } from "lucide-react";
import Link from "next/link";

import RepairHistoryTable from "@/components/repair-history-table";
import { fetchRepairHistory } from "@/lib/api";
import type { RepairHistoryItem } from "@/lib/types";

const ROOT_CAUSES = [
  "application_defect",
  "test_script_issue",
  "network_issue",
  "dependency_issue",
  "workflow_environment_issue",
  "infrastructure_resource_issue",
  "deployment_issue",
  "security_policy_issue",
  "other_or_unknown",
];

const PUBLISH_STATUSES = [
  "in_progress",
  "branch_created",
  "commit_created",
  "draft_pr_created",
  "partial_manual_review",
  "manual_review",
  "notification_sent",
  "failed",
];

function optionLabel(value: string) {
  return value.replaceAll("_", " ");
}

export default async function RepairHistoryPage({
  searchParams,
}: {
  searchParams: Promise<{
    root_cause?: string;
    publish_status?: string;
    repository?: string;
  }>;
}) {
  const filters = await searchParams;
  const items: RepairHistoryItem[] = await fetchRepairHistory({
    rootCause: filters.root_cause,
    publishStatus: filters.publish_status,
    repository: filters.repository,
  });

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-[var(--foreground)]">
            Repair History
          </h2>
          <p className="mt-1 text-sm font-medium text-[var(--muted)]">
            Controlled repair plans, publishing outcomes, and developer review links.
          </p>
        </div>
        <span className="border-l-4 border-indigo-500 pl-3 text-sm font-bold text-slate-700">
          {items.length} matching attempts
        </span>
      </header>

      <section className="border-y border-[var(--border)] bg-[var(--card)] py-4">
        <form className="grid gap-3 px-1 md:grid-cols-[1fr_1fr_1.2fr_auto_auto] md:items-end">
          <label className="text-xs font-bold text-[var(--muted)]">
            Root cause
            <select
              name="root_cause"
              defaultValue={filters.root_cause || ""}
              className="mt-1.5 h-10 w-full rounded-lg border border-[var(--border)] bg-white px-3 text-sm font-medium text-slate-800"
            >
              <option value="">All root causes</option>
              {ROOT_CAUSES.map((value) => (
                <option key={value} value={value}>{optionLabel(value)}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-bold text-[var(--muted)]">
            Publish status
            <select
              name="publish_status"
              defaultValue={filters.publish_status || ""}
              className="mt-1.5 h-10 w-full rounded-lg border border-[var(--border)] bg-white px-3 text-sm font-medium text-slate-800"
            >
              <option value="">All statuses</option>
              {PUBLISH_STATUSES.map((value) => (
                <option key={value} value={value}>{optionLabel(value)}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-bold text-[var(--muted)]">
            Repository
            <input
              name="repository"
              defaultValue={filters.repository || ""}
              placeholder="owner/repository"
              className="mt-1.5 h-10 w-full rounded-lg border border-[var(--border)] bg-white px-3 text-sm font-medium text-slate-800"
            />
          </label>
          <button
            type="submit"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 text-xs font-bold text-white hover:bg-indigo-700"
          >
            <Filter size={15} /> Apply
          </button>
          <Link
            href="/repair-history"
            aria-label="Clear repair history filters"
            title="Clear filters"
            className="inline-flex h-10 items-center justify-center rounded-lg border border-[var(--border)] px-3 text-slate-600 hover:bg-slate-50"
          >
            <RotateCcw size={15} />
          </Link>
        </form>
      </section>

      <section className="border border-[var(--border)] bg-[var(--card)] shadow-sm">
        <RepairHistoryTable items={items} />
      </section>
    </div>
  );
}
