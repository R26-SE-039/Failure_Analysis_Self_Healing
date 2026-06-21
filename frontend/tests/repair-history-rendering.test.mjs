import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import RepairHistoryTable from "../components/repair-history-table.ts";

const item = {
  attempt_id: "REPAIR-TEST-1",
  root_cause: "application_defect",
  confidence: 0.811,
  repository: "example/project",
  failed_branch: "main",
  failed_sha: "a".repeat(40),
  github_run_url: "https://github.com/example/project/actions/runs/123",
  candidate_file: "app/user_service.py",
  candidate_line: 10,
  healing_action: "start_mcp_code_repair",
  plan_status: "planned",
  publish_status: "draft_pr_created",
  action_status: null,
  target_module: null,
  repair_branch: "auto-heal/repair-test-syntaxerror",
  commit_sha: "b".repeat(40),
  draft_pr_url: "https://github.com/example/project/pull/1",
  github_changes_made: true,
  created_at: "2026-06-21T12:00:00Z",
  updated_at: "2026-06-21T12:05:00Z",
};

test("renders safe repair metadata and GitHub links", () => {
  const markup = renderToStaticMarkup(
    React.createElement(RepairHistoryTable, { items: [item] }),
  );

  assert.match(markup, /REPAIR-TEST-1/);
  assert.match(markup, /application defect/);
  assert.match(markup, /app\/user_service.py:10/);
  assert.match(markup, /Workflow run/);
  assert.match(markup, /Failed branch/);
  assert.match(markup, /Repair branch/);
  assert.match(markup, /Draft PR/);
  assert.doesNotMatch(markup, /prompt|token|source excerpt|raw log/i);
});

test("renders the empty history state", () => {
  const markup = renderToStaticMarkup(
    React.createElement(RepairHistoryTable, { items: [] }),
  );
  assert.match(markup, /No repair attempts match these filters/);
});

test("renders notification-only test script history", () => {
  const notificationItem = {
    ...item,
    root_cause: "test_script_issue",
    publish_status: null,
    action_status: "notification_sent",
    target_module: "Test Script Generation Module",
    repair_branch: null,
    commit_sha: null,
    draft_pr_url: null,
    github_changes_made: false,
  };
  const markup = renderToStaticMarkup(
    React.createElement(RepairHistoryTable, { items: [notificationItem] }),
  );

  assert.match(markup, /notification sent/);
  assert.match(markup, /Test Script Generation Module/);
  assert.match(markup, /No GitHub changes/);
  assert.doesNotMatch(markup, /Repair branch|Draft PR/);
});
