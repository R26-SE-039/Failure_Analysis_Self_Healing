export type Failure = {
  id: number;
  test_id: string;
  test_name: string;
  pipeline: string;
  status: string;
  root_cause: string;
  confidence?: string | null;
  healing?: string | null;
  logs?: string | null;
  stack_trace?: string | null;
  recommendation?: string | null;
  developer_alert: boolean;
  created_at?: string | null;
};

export type HealingAction = {
  id: number;
  healing_id: string;
  failure_test_id: string;
  test_name: string;
  repair_type: string;
  old_value: string;
  new_value: string;
  status: string;
};

export type FlakyTest = {
  id: number;
  test_code: string;
  test_name: string;
  instability_score: string;
  recent_pattern: string;
  risk_level: string;
};

export type Notification = {
  id: number;
  failure_test_id: string;
  test_name: string;
  root_cause: string;
  message: string;
  target: string;
};

export type DashboardSummary = {
  total_failures: number;
  total_healing_actions: number;
  total_flaky_tests: number;
  total_notifications: number;
  recent_failures: Array<{
    id: number;
    test_id: string;
    test_name: string;
    pipeline: string;
    status: string;
    root_cause: string;
    healing?: string | null;
  }>;
};

export type RepairHistoryItem = {
  attempt_id: string;
  root_cause: string;
  confidence: number;
  repository: string | null;
  failed_branch: string | null;
  failed_sha: string | null;
  github_run_url: string | null;
  candidate_file: string;
  candidate_line: number | null;
  healing_action: string;
  plan_status: string;
  publish_status: string | null;
  action_status: string | null;
  target_module: string | null;
  automation_level: string;
  recommended_action: string;
  validation_guidance: string[];
  history_status: string;
  repair_branch: string | null;
  commit_sha: string | null;
  draft_pr_url: string | null;
  github_changes_made: boolean;
  created_at: string;
  updated_at: string;
};
