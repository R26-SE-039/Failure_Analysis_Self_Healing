import { createElement as h, type ReactNode } from "react";
import type { RepairHistoryItem } from "../lib/types.ts";

function label(value: string | null) {
  return (value || "Not started").replaceAll("_", " ");
}

function githubBranchUrl(repository: string, branch: string) {
  const encodedBranch = branch.split("/").map(encodeURIComponent).join("/");
  return `https://github.com/${repository}/tree/${encodedBranch}`;
}

function link(href: string | null, text: string, key: string): ReactNode {
  if (!href) return null;
  return h(
    "a",
    {
      key,
      href,
      target: "_blank",
      rel: "noreferrer",
      className: "font-bold text-indigo-700 hover:underline",
    },
    text,
  );
}

function cell(key: string, children: ReactNode, className = "") {
  return h(
    "td",
    { key, className: `px-3 py-4 align-top ${className}` },
    children,
  );
}

export default function RepairHistoryTable({
  items,
}: {
  items: RepairHistoryItem[];
}) {
  if (items.length === 0) {
    return h(
      "div",
      {
        "data-testid": "repair-history-empty",
        className: "border-t border-[var(--border)] py-12 text-center text-sm font-medium text-[var(--muted)]",
      },
      "No repair attempts match these filters.",
    );
  }

  const headers = [
    "Attempt",
    "Classification",
    "Repository",
    "Failure",
    "Healing",
    "Publishing",
    "GitHub",
    "Updated",
  ];
  return h(
    "div",
    { className: "overflow-x-auto", "data-testid": "repair-history-table" },
    h(
      "table",
      { className: "w-full min-w-[1180px] border-collapse text-left text-xs" },
      h(
        "thead",
        null,
        h(
          "tr",
          { className: "border-y border-[var(--border)] bg-slate-50 text-[var(--muted)]" },
          ...headers.map((header) =>
            h("th", { key: header, className: "px-3 py-3 font-extrabold uppercase" }, header),
          ),
        ),
      ),
      h(
        "tbody",
        null,
        ...items.map((item) => {
          const branchUrl =
            item.repository && item.repair_branch
              ? githubBranchUrl(item.repository, item.repair_branch)
              : null;
          const failedBranchUrl =
            item.repository && item.failed_branch
              ? githubBranchUrl(item.repository, item.failed_branch)
              : null;
          return h(
            "tr",
            { key: item.attempt_id, className: "border-b border-[var(--border)] hover:bg-slate-50/60" },
            cell(
              "attempt",
              h("div", null,
                h("p", { className: "font-mono font-bold text-indigo-700" }, item.attempt_id),
                h("p", { className: "mt-1 text-[var(--muted)]" }, new Date(item.created_at).toLocaleString()),
              ),
            ),
            cell(
              "classification",
              h("div", null,
                h("p", { className: "font-bold capitalize text-slate-800" }, label(item.root_cause)),
                h("p", { className: "mt-1 font-mono text-[var(--muted)]" }, `${(item.confidence * 100).toFixed(1)}%`),
              ),
            ),
            cell(
              "repository",
              h("div", null,
                h("p", { className: "font-bold text-slate-800" }, item.repository || "Unavailable"),
                h("p", { className: "mt-1 font-mono text-[var(--muted)]" }, item.failed_branch || "No branch"),
                h("p", { className: "mt-1 font-mono text-[var(--muted)]" }, item.failed_sha?.slice(0, 12) || "No SHA"),
              ),
            ),
            cell(
              "failure",
              h("p", { className: "max-w-52 break-all font-mono text-slate-700" },
                `${item.candidate_file}${item.candidate_line ? `:${item.candidate_line}` : ""}`,
              ),
            ),
            cell(
              "healing",
              h("div", null,
                h("p", { className: "font-bold capitalize text-cyan-700" }, label(item.automation_level)),
                h("p", { className: "mt-1 max-w-64 text-slate-700" }, item.recommended_action),
                h("p", { className: "mt-2 font-bold capitalize text-blue-700" }, label(item.history_status)),
                item.validation_guidance.length > 0
                  ? h("ul", { className: "mt-2 space-y-1 font-mono text-[10px] text-[var(--muted)]" },
                      ...item.validation_guidance.map((guidance) =>
                        h("li", { key: guidance }, guidance),
                      ),
                    )
                  : null,
              ),
            ),
            cell(
              "publishing",
              h("div", null,
                h("p", { className: "font-bold capitalize text-slate-800" }, label(item.publish_status)),
                item.action_status
                  ? h("p", { className: "mt-1 font-bold capitalize text-cyan-700" }, label(item.action_status))
                  : null,
                item.target_module
                  ? h("p", { className: "mt-1 text-[var(--muted)]" }, item.target_module)
                  : null,
                h("p", { className: "mt-1 font-mono text-[var(--muted)]" }, item.commit_sha?.slice(0, 12) || "No commit"),
                h("p", { className: `mt-2 font-bold ${item.github_changes_made ? "text-emerald-700" : "text-slate-500"}` },
                  item.github_changes_made ? "GitHub changes recorded" : "No GitHub changes",
                ),
              ),
            ),
            cell(
              "github",
              h("div", { className: "flex flex-col items-start gap-2" },
                link(item.github_run_url, "Workflow run", "run"),
                link(failedBranchUrl, "Failed branch", "failed-branch"),
                link(branchUrl, "Repair branch", "branch"),
                link(item.draft_pr_url, "Draft PR", "pr"),
              ),
            ),
            cell("updated", new Date(item.updated_at).toLocaleString(), "whitespace-nowrap text-[var(--muted)]"),
          );
        }),
      ),
    ),
  );
}
