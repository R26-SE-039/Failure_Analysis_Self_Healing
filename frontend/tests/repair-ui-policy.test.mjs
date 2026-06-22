import assert from "node:assert/strict";
import test from "node:test";

import {
  canShowControlledRepair,
  isNotificationOnly,
  actionTargetLabel,
} from "../lib/repair-ui-policy.ts";

test("test script issues never show controlled repair controls", () => {
  assert.equal(canShowControlledRepair("test_script_issue", false), false);
  assert.equal(canShowControlledRepair("test_script_issue", true), false);
  assert.equal(isNotificationOnly("test_script_issue"), true);
  assert.equal(
    actionTargetLabel("test_script_issue", "ignored"),
    "Forwarded to Test Script Generation Module",
  );
});

test("all remaining root causes hide repair controls", () => {
  for (const rootCause of [
    "dependency_issue",
    "workflow_environment_issue",
    "network_issue",
    "infrastructure_resource_issue",
    "deployment_issue",
    "security_policy_issue",
    "other_or_unknown",
  ]) {
    assert.equal(canShowControlledRepair(rootCause, false), false);
    assert.equal(canShowControlledRepair(rootCause, true), false);
  }
});

test("application defects preserve controlled repair visibility", () => {
  assert.equal(canShowControlledRepair("application_defect", true), true);
  assert.equal(canShowControlledRepair("application_defect", false), false);
});
