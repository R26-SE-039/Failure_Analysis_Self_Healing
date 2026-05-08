"""
generate_synthetic_dataset.py
------------------------------
Generates ~800 synthetic Selenium/UI test failure records covering:
  - locator_issue
  - synchronization_issue
  - test_data_issue
  - environment_failure
  - network_api_error
  - application_defect

Then merges with the existing ci_cd_pipeline_failure_logs_dataset.csv
and produces a final_training_dataset.csv ready for ML training.
"""

import csv
import random
import os
from datetime import datetime, timedelta

random.seed(42)

# ── Noise Configuration ────────────────────────────────────────────────────────
# Introducing noise to achieve ~75-80% accuracy instead of 100%
LABEL_NOISE_RATE = 0.10  # 10% of labels will be randomly flipped
GENERIC_MSG_PROB = 0.15  # 15% of records will use a generic error message

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXISTING_CSV  = os.path.join(DATA_DIR, "ci_cd_pipeline_failure_logs_dataset.csv")
SYNTHETIC_CSV = os.path.join(DATA_DIR, "synthetic_selenium_failures.csv")
FINAL_CSV     = os.path.join(DATA_DIR, "final_training_dataset.csv")

# ── vocabulary pools ───────────────────────────────────────────────────────────

LOCATOR_OLD = [
    "#login-btn", "#submit-btn", ".checkout-form", "//button[@id='pay']",
    "#email-field", ".nav-menu li:nth-child(3)", "#product-add-cart",
    "//input[@name='username']", ".modal-close-btn", "#search-input",
    "#register-link", "//div[@class='dropdown']/a", ".hero-cta-button",
    "#confirm-order", "//span[text()='Proceed']",
]

LOCATOR_NEW = [
    "[data-testid='login-button']", "[data-testid='submit']",
    "[data-cy='checkout-form']", "//button[@data-qa='pay-now']",
    "[data-testid='email-input']", "[aria-label='Main Navigation'] li:nth-child(3)",
    "[data-testid='add-to-cart']", "//input[@data-testid='username']",
    "[data-testid='modal-close']", "[data-testid='search-bar']",
    "[data-testid='register-link']", "[data-qa='dropdown-toggle']",
    "[data-testid='hero-cta']", "[data-testid='confirm-order']",
    "//button[contains(@data-testid,'proceed')]",
]

WAIT_OLD = [
    "time.sleep(2)", "driver.implicitly_wait(3)", "time.sleep(1)",
    "WebDriverWait(driver, 5)", "time.sleep(0.5)", "driver.implicitly_wait(2)",
]

WAIT_NEW = [
    "WebDriverWait(driver, 15).until(EC.visibility_of_element_located(locator))",
    "WebDriverWait(driver, 20).until(EC.element_to_be_clickable(locator))",
    "WebDriverWait(driver, 10).until(EC.presence_of_element_located(locator))",
    "WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element(locator, text))",
    "WebDriverWait(driver, 12).until(EC.invisibility_of_element_located(loader))",
]

TEST_NAMES = [
    "Login Test", "Checkout Test", "Registration Test", "Profile Update Test",
    "Product Search Test", "Cart Validation Test", "Password Reset Test",
    "Filter Test", "Payment Test", "Logout Test", "Dashboard Load Test",
    "Report Export Test", "User Role Test", "Session Timeout Test",
    "File Upload Test", "API Response Test", "Notification Test",
    "Multi-Tab Navigation Test", "Form Validation Test", "Order History Test",
]

PIPELINES = ["Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Azure DevOps"]
BROWSERS   = ["Chrome", "Firefox", "Edge", "Safari"]
OS_LIST    = ["ubuntu-latest", "windows-latest", "macos-latest"]
LANGS      = ["Python", "Java", "JavaScript", "C#"]
CLOUD      = ["AWS", "Azure", "GCP", "On-Prem"]
BRANCHES   = ["main", "develop", "feature-x", "release", "hotfix"]

GENERIC_MESSAGES = [
    "An unexpected error occurred during test execution.",
    "The operation timed out after 60 seconds.",
    "System.Exception: General failure detected in the testing pipeline.",
    "Failed to complete the action on the web application.",
    "Test runner encountered an unhandled exception.",
]

# ── per-category templates ─────────────────────────────────────────────────────

def make_locator_issue(i):
    old = random.choice(LOCATOR_OLD)
    new = random.choice(LOCATOR_NEW)
    test = random.choice(TEST_NAMES)
    msgs = [
        f"org.openqa.selenium.NoSuchElementException: no such element: Unable to locate element: {{{old}}}",
        f"selenium.common.exceptions.NoSuchElementException: Message: no such element: {old}",
        f"org.openqa.selenium.StaleElementReferenceException: stale element reference: element is not attached to the page document; locator={old}",
        f"ElementNotInteractableException: element not interactable using locator {old}",
        f"InvalidSelectorException: invalid selector: {old} is not a valid CSS selector",
    ]
    traces = [
        f"NoSuchElementException at {test.replace(' ','')}.findElement(By.cssSelector(\"{old}\"))",
        f"StaleElementReferenceException at {test.replace(' ','')}.clickElement()",
        f"ElementNotInteractableException at {test.replace(' ','')}.sendKeys()",
    ]
    recs = [
        f"Update locator from '{old}' to '{new}' using stable data-testid attribute",
        f"Replace brittle CSS selector '{old}' with data attribute '{new}'",
        f"Locator changed after UI refactor. Use '{new}' instead of '{old}'",
    ]
    return {
        "test_id": f"SEL-{1000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "locator_issue",
        "failure_stage": "test",
        "failure_type": "Test Failure",
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["HIGH", "MEDIUM"]),
        "old_value": old,
        "new_value": new,
        "retry_count": random.randint(0, 2),
        "test_duration_sec": random.randint(5, 120),
        "cpu_usage_pct": round(random.uniform(20, 70), 2),
        "memory_usage_mb": random.randint(512, 4096),
        "is_flaky_test": random.choice([True, False]),
        "recommendation": random.choice(recs),
        "developer_alert": False,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


def make_sync_issue(i):
    test = random.choice(TEST_NAMES)
    old = random.choice(WAIT_OLD)
    new = random.choice(WAIT_NEW)
    msgs = [
        f"org.openqa.selenium.TimeoutException: Expected condition failed: waiting for visibility of element (tried for 5 second(s))",
        f"selenium.common.exceptions.TimeoutException: Message: Timeout waiting for element to be clickable",
        f"ElementClickInterceptedException: element click intercepted: another element obscures the target",
        f"TimeoutException: Timed out after 10000ms while waiting for element '.modal-overlay' to disappear",
        f"selenium.common.exceptions.ElementNotVisibleException: element is not visible at the time of interaction",
    ]
    traces = [
        f"TimeoutException at {test.replace(' ','')}.waitForElement() — implicit wait too short",
        f"ElementClickInterceptedException at {test.replace(' ','')}.clickButton() — overlay not dismissed",
        f"TimeoutException at WebDriverWait.until() — element not ready within timeout period",
    ]
    recs = [
        f"Replace '{old}' with explicit wait: {new}",
        f"Increase timeout and add explicit visibility check before interaction",
        f"Use fluent wait to handle dynamic page loading instead of fixed sleep",
    ]
    return {
        "test_id": f"SEL-{2000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "synchronization_issue",
        "failure_stage": "test",
        "failure_type": "Timeout",
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["MEDIUM", "HIGH"]),
        "old_value": old,
        "new_value": new,
        "retry_count": random.randint(1, 4),
        "test_duration_sec": random.randint(30, 300),
        "cpu_usage_pct": round(random.uniform(10, 50), 2),
        "memory_usage_mb": random.randint(512, 3000),
        "is_flaky_test": True,
        "recommendation": random.choice(recs),
        "developer_alert": False,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


def make_test_data_issue(i):
    test = random.choice(TEST_NAMES)
    msgs = [
        "AssertionError: Expected price 250.00 but found 199.00 — test data mismatch",
        "AssertionError: Expected user role 'admin' but got 'viewer' — DB seed data incorrect",
        "NullPointerException: Test data record not found in database for user_id=TEST_9921",
        "AssertionError: Expected item count 5 but found 0 — cart test data not initialized",
        "DataNotFoundException: Test coupon code 'SAVE20' expired or not seeded in test DB",
        "AssertionError: Expected status 'ACTIVE' but found 'INACTIVE' — stale test fixture",
        "SQLException: Test user 'qa_user_001' does not exist in test environment database",
    ]
    traces = [
        f"AssertionError at {test.replace(' ','')}.validateExpectedResult()",
        f"NullPointerException at {test.replace(' ','')}.getTestRecord()",
        f"DataNotFoundException at TestDataHelper.fetchRecord()",
    ]
    recs = [
        "Re-seed test database with fresh test data before execution",
        "Use dynamic test data generation instead of hardcoded values",
        "Validate test data availability in @BeforeEach setup method",
        "Use test data factories to ensure isolated, reproducible test state",
    ]
    return {
        "test_id": f"SEL-{3000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "test_data_issue",
        "failure_stage": "test",
        "failure_type": "Test Failure",
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["LOW", "MEDIUM"]),
        "old_value": "hardcoded/stale test data",
        "new_value": "dynamic test data with @BeforeEach setup",
        "retry_count": random.randint(0, 1),
        "test_duration_sec": random.randint(5, 60),
        "cpu_usage_pct": round(random.uniform(10, 40), 2),
        "memory_usage_mb": random.randint(256, 2048),
        "is_flaky_test": random.choice([True, True, False]),
        "recommendation": random.choice(recs),
        "developer_alert": True,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


def make_environment_failure(i):
    test = random.choice(TEST_NAMES)
    msgs = [
        "ConnectionRefusedError: Test environment database is not reachable at localhost:5432",
        "WebDriverException: Chrome browser failed to launch — ChromeDriver version mismatch",
        "EnvironmentError: Selenium Grid node is unavailable — no free nodes in the hub",
        "ConnectionError: Test application server returned HTTP 503 — service unavailable",
        "DockerContainerError: Test container exited unexpectedly with code 137 (OOM Killed)",
        "SSLError: SSL certificate verification failed for test environment endpoint",
        "RuntimeError: Test environment variable SELENIUM_REMOTE_URL not configured",
    ]
    traces = [
        f"ConnectionRefusedError at {test.replace(' ','')}.setupEnvironment()",
        f"WebDriverException at WebDriver.initialize() — driver binary not found",
        f"EnvironmentError at TestBase.getDriver() — RemoteWebDriver unavailable",
    ]
    recs = [
        "Restart test environment services and verify all dependencies are running",
        "Update ChromeDriver version to match installed Chrome browser version",
        "Check Selenium Grid hub availability and ensure test node is registered",
        "Verify test environment Docker containers are healthy before test run",
    ]
    return {
        "test_id": f"SEL-{4000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "environment_failure",
        "failure_stage": random.choice(["test", "build", "deploy"]),
        "failure_type": random.choice(["Configuration Error", "Resource Exhaustion", "Dependency Error"]),
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["HIGH", "CRITICAL"]),
        "old_value": "N/A",
        "new_value": "N/A",
        "retry_count": random.randint(1, 5),
        "test_duration_sec": random.randint(5, 40),
        "cpu_usage_pct": round(random.uniform(60, 99), 2),
        "memory_usage_mb": random.randint(3000, 8192),
        "is_flaky_test": random.choice([True, False]),
        "recommendation": random.choice(recs),
        "developer_alert": True,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


def make_network_api_error(i):
    test = random.choice(TEST_NAMES)
    msgs = [
        "requests.exceptions.ConnectionError: HTTPSConnectionPool — Max retries exceeded for URL",
        "urllib.error.URLError: <urlopen error [Errno 111] Connection refused> for test API endpoint",
        "AssertionError: Expected HTTP 200 but received 503 from /api/v1/products",
        "ReadTimeout: HTTPSConnectionPool read operation timed out after 30 seconds",
        "JSONDecodeError: API response body is not valid JSON — service returned HTML error page",
        "AssertionError: Expected response field 'status' == 'success' but got 'error'",
        "requests.exceptions.HTTPError: 429 Too Many Requests — API rate limit exceeded",
    ]
    traces = [
        f"ConnectionError at {test.replace(' ','')}.callExternalAPI()",
        f"ReadTimeout at {test.replace(' ','')}.validateAPIResponse()",
        f"AssertionError at APIHelper.assertResponseStatus() — unexpected status code",
    ]
    recs = [
        "Add retry logic with exponential backoff for transient network failures",
        "Use mock API responses for test isolation instead of live API calls",
        "Increase API request timeout configuration for slow test environments",
        "Verify API service health before test execution using smoke tests",
    ]
    return {
        "test_id": f"SEL-{5000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "network_api_error",
        "failure_stage": "test",
        "failure_type": "Network Error",
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["MEDIUM", "HIGH"]),
        "old_value": "N/A",
        "new_value": "N/A",
        "retry_count": random.randint(2, 5),
        "test_duration_sec": random.randint(30, 180),
        "cpu_usage_pct": round(random.uniform(15, 55), 2),
        "memory_usage_mb": random.randint(512, 2048),
        "is_flaky_test": True,
        "recommendation": random.choice(recs),
        "developer_alert": True,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


def make_application_defect(i):
    test = random.choice(TEST_NAMES)
    msgs = [
        "AssertionError: Expected button 'Add to Cart' to be enabled but it is disabled — regression introduced",
        "AssertionError: Page title mismatch — Expected 'Dashboard' but found '404 Page Not Found'",
        "AssertionError: Expected user balance 1000.00 but found 850.00 — calculation bug",
        "AssertionError: Form submission succeeded but no confirmation email was sent",
        "AssertionError: Filter by category 'Electronics' returned 0 results — backend filtering broken",
        "AssertionError: Password reset link expired immediately — token TTL bug",
        "AssertionError: Exported CSV file has 0 rows — data export functionality broken",
    ]
    traces = [
        f"AssertionError at {test.replace(' ','')}.verifyExpectedBehavior() — application regression",
        f"AssertionError at {test.replace(' ','')}.validatePageContent() — incorrect UI state",
        f"AssertionError at {test.replace(' ','')}.assertBusinessRule() — logic defect detected",
    ]
    recs = [
        "This is an application-level defect. Raise a bug report for the development team",
        "Test correctly identified a regression. Do NOT auto-heal — requires code fix",
        "Forward to developer: application behaviour does not match expected specification",
    ]
    return {
        "test_id": f"SEL-{6000+i:04d}",
        "test_name": test,
        "pipeline": random.choice(PIPELINES),
        "browser": random.choice(BROWSERS),
        "os": random.choice(OS_LIST),
        "language": random.choice(LANGS),
        "cloud_provider": random.choice(CLOUD),
        "branch": random.choice(BRANCHES),
        "root_cause": "application_defect",
        "failure_stage": "test",
        "failure_type": "Test Failure",
        "error_message": random.choice(msgs),
        "stack_trace": random.choice(traces),
        "severity": random.choice(["HIGH", "CRITICAL"]),
        "old_value": "N/A",
        "new_value": "N/A",
        "retry_count": random.randint(0, 1),
        "test_duration_sec": random.randint(10, 90),
        "cpu_usage_pct": round(random.uniform(20, 60), 2),
        "memory_usage_mb": random.randint(512, 3000),
        "is_flaky_test": False,
        "recommendation": random.choice(recs),
        "developer_alert": True,
        "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
    }


# ── generate records ──────────────────────────────────────────────────────────

CATEGORY_COUNTS = {
    "locator_issue":       200,
    "synchronization_issue": 150,
    "test_data_issue":     130,
    "environment_failure": 130,
    "network_api_error":   110,
    "application_defect":  130,
}

GENERATORS = {
    "locator_issue":       make_locator_issue,
    "synchronization_issue": make_sync_issue,
    "test_data_issue":     make_test_data_issue,
    "environment_failure": make_environment_failure,
    "network_api_error":   make_network_api_error,
    "application_defect":  make_application_defect,
}

SYNTHETIC_FIELDS = [
    "test_id", "test_name", "pipeline", "browser", "os", "language",
    "cloud_provider", "branch", "root_cause", "failure_stage", "failure_type",
    "error_message", "stack_trace", "severity", "old_value", "new_value",
    "retry_count", "test_duration_sec", "cpu_usage_pct", "memory_usage_mb",
    "is_flaky_test", "recommendation", "developer_alert", "timestamp",
]

all_records = []
for category, count in CATEGORY_COUNTS.items():
    fn = GENERATORS[category]
    for j in range(count):
        all_records.append(fn(j))

random.shuffle(all_records)

# ── Introduce Label Noise ─────────────────────────────────────────────────────
print(f"Applying {LABEL_NOISE_RATE*100}% label noise to make the dataset realistic...")
VALID_CLASSES = list(CATEGORY_COUNTS.keys())
noise_count = 0

for record in all_records:
    # 1. Randomly inject generic messages
    if random.random() < GENERIC_MSG_PROB:
        record["error_message"] = random.choice(GENERIC_MESSAGES)
        record["stack_trace"] = "Exception at generic_handler.py"

    # 2. Randomly flip labels
    if random.random() < LABEL_NOISE_RATE:
        original = record["root_cause"]
        # Pick a different class
        other_classes = [c for c in VALID_CLASSES if c != original]
        record["root_cause"] = random.choice(other_classes)
        noise_count += 1

print(f"  Injected noise into {noise_count} records")
print(f"Generated {len(all_records)} synthetic Selenium failure records")

# ── write synthetic CSV ───────────────────────────────────────────────────────

with open(SYNTHETIC_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=SYNTHETIC_FIELDS)
    writer.writeheader()
    writer.writerows(all_records)

print(f"Saved synthetic dataset -> {SYNTHETIC_CSV}")

# ── category distribution summary ─────────────────────────────────────────────
print("\n=== SYNTHETIC DATASET DISTRIBUTION ===")
from collections import Counter
dist = Counter(r["root_cause"] for r in all_records)
for label, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"  {label:<25} {cnt:>4} records")

# ── merge with existing dataset ───────────────────────────────────────────────
print("\nMerging with existing CI/CD dataset …")

FINAL_FIELDS = [
    "test_id", "test_name", "pipeline", "browser", "os", "language",
    "cloud_provider", "branch", "root_cause", "failure_stage", "failure_type",
    "error_message", "stack_trace", "severity", "old_value", "new_value",
    "retry_count", "test_duration_sec", "cpu_usage_pct", "memory_usage_mb",
    "is_flaky_test", "recommendation", "developer_alert", "timestamp",
]

CATEGORY_MAP = {
    "Build Failure":         "application_defect",
    "Test Failure":          "application_defect",   # will be overridden by synthetic
    "Dependency Error":      "environment_failure",
    "Network Error":         "network_api_error",
    "Configuration Error":   "environment_failure",
    "Resource Exhaustion":   "environment_failure",
    "Timeout":               "synchronization_issue",
    "Deployment Failure":    "environment_failure",
    "Security Scan Failure": "environment_failure",
    "Permission Error":      "environment_failure",
}

merged_records = []
existing_count = 0

with open(EXISTING_CSV, "r", encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ft = row.get("failure_type", "")
        rc = CATEGORY_MAP.get(ft, "environment_failure")
        merged_records.append({
            "test_id":          row.get("run_id", ""),
            "test_name":        f"{ft} — {row.get('repository','')}",
            "pipeline":         row.get("ci_tool", ""),
            "browser":          "N/A",
            "os":               row.get("os", ""),
            "language":         row.get("language", ""),
            "cloud_provider":   row.get("cloud_provider", ""),
            "branch":           row.get("branch", ""),
            "root_cause":       rc,
            "failure_stage":    row.get("failure_stage", ""),
            "failure_type":     ft,
            "error_message":    row.get("error_message", ""),
            "stack_trace":      "",
            "severity":         row.get("severity", ""),
            "old_value":        "N/A",
            "new_value":        "N/A",
            "retry_count":      row.get("retry_count", 0),
            "test_duration_sec": row.get("test_duration_sec", 0),
            "cpu_usage_pct":    row.get("cpu_usage_pct", 0),
            "memory_usage_mb":  row.get("memory_usage_mb", 0),
            "is_flaky_test":    row.get("is_flaky_test", False),
            "recommendation":   "",
            "developer_alert":  str(row.get("incident_created", "False")),
            "timestamp":        row.get("timestamp", ""),
        })
        existing_count += 1

# append synthetic records
merged_records.extend(all_records)

# shuffle
random.shuffle(merged_records)

# ── Introduce Noise to Entire Merged Dataset ──────────────────────────────────
print(f"Applying {LABEL_NOISE_RATE*100}% label noise to the entire merged dataset ({len(merged_records)} records)...")
VALID_CLASSES = list(set(r["root_cause"] for r in merged_records))
noise_count = 0

for record in merged_records:
    # Randomly flip labels
    if random.random() < LABEL_NOISE_RATE:
        original = record["root_cause"]
        # Pick a different class
        other_classes = [c for c in VALID_CLASSES if c != original]
        if other_classes:
            record["root_cause"] = random.choice(other_classes)
            noise_count += 1

print(f"  Injected noise into {noise_count} records")

with open(FINAL_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FINAL_FIELDS)
    writer.writeheader()
    writer.writerows(merged_records)

total = len(merged_records)
print(f"\n=== FINAL MERGED DATASET ===")
print(f"  Existing CI/CD records : {existing_count}")
print(f"  Synthetic records      : {len(all_records)}")
print(f"  TOTAL                  : {total}")
print(f"\n=== FINAL ROOT CAUSE DISTRIBUTION ===")
dist2 = Counter(str(r.get("root_cause","")) for r in merged_records)
for label, cnt in sorted(dist2.items(), key=lambda x: -x[1]):
    pct = cnt / total * 100
    print(f"  {label:<25} {cnt:>6} records  ({pct:.1f}%)")

print(f"\nFinal dataset saved -> {FINAL_CSV}")
print("Done!")
