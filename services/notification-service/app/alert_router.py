"""
alert_router.py — Notification Service
Routes failure alerts to the correct stakeholder target.
"""
import uuid

TARGET_LABELS = {
    "developer": "Software Developer",
    "devops":    "DevOps Engineer",
    "manager":   "Project Manager",
}

ROOT_CAUSE_TARGETS = {
    "application_defect":    "developer",
    "test_data_issue":       "developer",
    "environment_failure":   "devops",
    "network_api_error":     "devops",
    "locator_issue":         "developer",
    "synchronization_issue": "developer",
}


def create_notification(
    failure_test_id: str,
    test_name: str,
    root_cause: str,
    message: str,
    target: str = "developer",
) -> dict:
    notification_id = f"N-{uuid.uuid4().hex[:8].upper()}"

    # Auto-route if not specified
    if target not in TARGET_LABELS:
        target = ROOT_CAUSE_TARGETS.get(root_cause.lower(), "developer")

    label = TARGET_LABELS.get(target, "Developer")

    return {
        "notification_id":  notification_id,
        "failure_test_id":  failure_test_id,
        "test_name":        test_name,
        "root_cause":       root_cause,
        "message":          message,
        "target":           target,
        "status":           "sent",
    }
