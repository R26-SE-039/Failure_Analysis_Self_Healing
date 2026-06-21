import assert from "node:assert/strict";
import test from "node:test";

import {
  canShowControlledRepair,
  isNotificationOnly,
} from "../lib/repair-ui-policy.ts";

test("test script issues never show controlled repair controls", () => {
  assert.equal(canShowControlledRepair("test_script_issue", false), false);
  assert.equal(canShowControlledRepair("test_script_issue", true), false);
  assert.equal(isNotificationOnly("test_script_issue"), true);
});

test("application defects preserve controlled repair visibility", () => {
  assert.equal(canShowControlledRepair("application_defect", true), true);
  assert.equal(canShowControlledRepair("application_defect", false), false);
});
