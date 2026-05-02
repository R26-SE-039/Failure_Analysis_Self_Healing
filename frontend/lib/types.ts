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