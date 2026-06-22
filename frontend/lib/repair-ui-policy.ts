export function canShowControlledRepair(
  rootCause: string,
  allowedToPlan: boolean,
) {
  return rootCause === "application_defect" && allowedToPlan;
}

export function isNotificationOnly(rootCause: string) {
  return rootCause === "test_script_issue";
}

export function actionTargetLabel(rootCause: string, target: string) {
  return rootCause === "test_script_issue"
    ? "Forwarded to Test Script Generation Module"
    : target;
}
