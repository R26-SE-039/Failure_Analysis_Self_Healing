"""
healing_engine.py — Healing Service
Determines the appropriate repair strategy based on root_cause
and delegates to the correct strategy module.
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

    elif rc == "network_api_error":
        broken = old_value or "direct API call without retry"
        new_val = "retry with exponential backoff (max 3 attempts)"
        repair_type, recommendation = _RECOMMENDATIONS["network_api_error"]
        status = "Pending"
        developer_alert = True

    else:  # application_defect — no auto-heal
        broken = old_value or "N/A"
        new_val = "N/A — requires developer fix"
        repair_type, recommendation = _RECOMMENDATIONS["application_defect"]
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
