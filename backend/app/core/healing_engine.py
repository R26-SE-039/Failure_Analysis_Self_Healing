"""
healing_engine.py — Core Logic
Determines the appropriate repair strategy based on root_cause.
"""
import re
import uuid
from typing import Optional


# ── Locator patterns to detect old/fragile selectors ──────────────────────────
_LOCATOR_PATTERNS = [
    r"#[\w-]+",                      # CSS id selectors
    r"\.[\w-]+",                     # CSS class selectors
    r"xpath=.+",
    r"//\w+\[.+\]",                  # XPath
    r"By\.(id|cssSelector|xpath)\(", # Selenium By.*
]

_STABLE_SUGGESTION = "[data-testid='{element}']"

_SYNC_UPGRADES = {
    "time.sleep(":         "WebDriverWait(driver, 15).until(EC.visibility_of_element_located(locator))",
    "implicitly_wait":     "WebDriverWait(driver, 20).until(EC.element_to_be_clickable(locator))",
    "wait(":               "WebDriverWait(driver, 15).until(EC.presence_of_element_located(locator))",
    "Thread.sleep":        "WebDriverWait(driver, 15, poll_frequency=0.5).until(EC.visibility_of_element_located(locator))",
}

_RECOMMENDATIONS = {
    "locator_issue": (
        "Locator Repair",
        "Update the failing element locator to use a stable data-testid or aria-label "
        "attribute instead of fragile CSS id/class selectors. Verify the new locator "
        "against the current DOM structure before committing."
    ),
    "synchronization_issue": (
        "Wait Strategy Upgrade",
        "Replace fixed sleep/implicit waits with explicit WebDriverWait conditions. "
        "Use EC.visibility_of_element_located() or EC.element_to_be_clickable() "
        "to make the test resilient to page-load timing variations."
    ),
    "test_data_issue": (
        "Test Data Refresh",
        "Re-seed the test database with fresh test data before execution. "
        "Use @BeforeEach setup methods or test data factories to ensure "
        "isolated and reproducible test state."
    ),
    "environment_failure": (
        "Environment Retry",
        "Retry after verifying test environment health. Check that all required "
        "services (database, Docker containers, Selenium Grid) are running. "
        "Consider adding a pre-test smoke check."
    ),
    "network_api_error": (
        "Network Retry with Backoff",
        "Add retry logic with exponential backoff for transient network failures. "
        "Consider mocking external API calls in test environments to isolate "
        "the test from network instability."
    ),
    "network_issue": (
        "Network Retry with Backoff",
        "Retry the job after checking transient network, DNS, and upstream API "
        "availability. Add exponential backoff where the failing step calls "
        "external services."
    ),
    "dependency_issue": (
        "Dependency Review",
        "Review package versions, lockfiles, and package registry availability. "
        "Regenerate the lockfile or pin the failing dependency before rerunning "
        "the pipeline."
    ),
    "deployment_issue": (
        "Deployment Review",
        "Review rollout status, image availability, migration output, and probe "
        "configuration. Roll back or redeploy after the failing deployment step "
        "is corrected."
    ),
    "infrastructure_resource_issue": (
        "Resource Review",
        "Check runner disk, memory, timeout, and quota limits. Increase resources "
        "or split the job if the pipeline exhausted infrastructure capacity."
    ),
    "security_policy_issue": (
        "Security Policy Review",
        "Block automatic healing and route the failure to security review. Fix "
        "the policy, vulnerability, or secret-scanning issue before rerunning."
    ),
    "test_script_issue": (
        "Test Script Repair",
        "Route the failure to the test script component. Inspect assertions, "
        "fixtures, locators, waits, and test setup before rerunning the suite."
    ),
    "workflow_environment_issue": (
        "Workflow Configuration Review",
        "Check workflow paths, environment variables, permissions, and working "
        "directory configuration. Update the CI job configuration before rerun."
    ),
    "other_or_unknown": (
        "Manual Review",
        "The classifier could not isolate a precise repair path. Review the "
        "captured log excerpt and route the failure manually."
    ),
    "application_defect": (
        "Developer Alert",
        "This failure indicates an application-level defect. No automated repair "
        "is possible. A bug report has been raised for the development team."
    ),
}


def _extract_locator(error_message: str, old_value: str) -> str:
    """Try to pull the broken locator from the error message."""
    if old_value and old_value not in ("N/A", "", "hardcoded/stale test data"):
        return old_value
    for pat in _LOCATOR_PATTERNS:
        m = re.search(pat, error_message)
        if m:
            return m.group(0)
    return "#unknown-locator"


def _extract_wait_call(error_message: str, old_value: str) -> str:
    if old_value and old_value not in ("N/A", ""):
        return old_value
    for key in _SYNC_UPGRADES:
        if key.lower() in error_message.lower():
            return key
    return "time.sleep(2)"


def heal(
    test_id: str,
    test_name: str,
    root_cause: str,
    confidence: float,
    error_message: str,
    stack_trace: str = "",
    failure_type: str = "Test Failure",
    old_value: str = "",
) -> dict:
    healing_id = f"H-{uuid.uuid4().hex[:8].upper()}"
    rc = root_cause.lower()

    if rc == "locator_issue":
        broken = _extract_locator(error_message, old_value)
        # Suggest a stable data-testid version
        element_name = re.sub(r"[^a-zA-Z0-9]", "-", broken).strip("-").lower()
        new_val = f"[data-testid='{element_name}']"
        repair_type, recommendation = _RECOMMENDATIONS["locator_issue"]
        status = "Suggested"
        developer_alert = False

    elif rc == "synchronization_issue":
        old_wait = _extract_wait_call(error_message, old_value)
        new_val = _SYNC_UPGRADES.get(old_wait, list(_SYNC_UPGRADES.values())[0])
        broken = old_wait
        repair_type, recommendation = _RECOMMENDATIONS["synchronization_issue"]
        status = "Suggested"
        developer_alert = False

    elif rc == "test_data_issue":
        broken = old_value or "hardcoded / stale test data"
        new_val = "@BeforeEach dynamic test data setup"
        repair_type, recommendation = _RECOMMENDATIONS["test_data_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "environment_failure":
        broken = old_value or "environment service down"
        new_val = "retry after environment health check"
        repair_type, recommendation = _RECOMMENDATIONS["environment_failure"]
        status = "Pending"
        developer_alert = True

    elif rc in {"network_api_error", "network_issue"}:
        broken = old_value or "direct API call without retry"
        new_val = "retry with exponential backoff (max 3 attempts)"
        repair_type, recommendation = _RECOMMENDATIONS.get(
            rc,
            _RECOMMENDATIONS["network_api_error"],
        )
        status = "Pending"
        developer_alert = True

    elif rc == "test_script_issue":
        broken = old_value or "failing test script"
        new_val = "send to test script repair component"
        repair_type, recommendation = _RECOMMENDATIONS["test_script_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "dependency_issue":
        broken = old_value or "dependency or lockfile"
        new_val = "pin dependency or regenerate lockfile"
        repair_type, recommendation = _RECOMMENDATIONS["dependency_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "workflow_environment_issue":
        broken = old_value or "workflow environment configuration"
        new_val = "update CI environment configuration"
        repair_type, recommendation = _RECOMMENDATIONS["workflow_environment_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "infrastructure_resource_issue":
        broken = old_value or "runner resource limit"
        new_val = "increase resources or split pipeline job"
        repair_type, recommendation = _RECOMMENDATIONS["infrastructure_resource_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "deployment_issue":
        broken = old_value or "deployment step"
        new_val = "rollback or redeploy after correction"
        repair_type, recommendation = _RECOMMENDATIONS["deployment_issue"]
        status = "Pending"
        developer_alert = True

    elif rc == "security_policy_issue":
        broken = old_value or "security policy gate"
        new_val = "manual security review required"
        repair_type, recommendation = _RECOMMENDATIONS["security_policy_issue"]
        status = "Rejected"
        developer_alert = True

    elif rc == "other_or_unknown":
        broken = old_value or "unknown failure signal"
        new_val = "manual triage required"
        repair_type, recommendation = _RECOMMENDATIONS["other_or_unknown"]
        status = "Pending"
        developer_alert = True

    else:  # application_defect or unknown label
        broken = old_value or "N/A"
        new_val = "N/A - requires developer fix"
        repair_type, recommendation = _RECOMMENDATIONS.get(
            rc,
            _RECOMMENDATIONS["application_defect"],
        )
        status = "Rejected"
        developer_alert = True

    return {
        "test_id":        test_id,
        "healing_id":     healing_id,
        "repair_type":    repair_type,
        "old_value":      broken,
        "new_value":      new_val,
        "recommendation": recommendation,
        "status":         status,
        "developer_alert": developer_alert,
    }
