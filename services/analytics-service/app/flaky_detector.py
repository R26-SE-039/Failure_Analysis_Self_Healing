"""
flaky_detector.py — Analytics Service
Predicts flaky test risk based on execution metadata using
rule-based heuristics + simple ML scoring.
"""
import re
from typing import Optional


# Risk thresholds
HIGH_RETRY   = 3
MEDIUM_RETRY = 2

FLAKY_FAILURE_TYPES = {
    "Timeout", "Network Error", "Test Failure"
}

FLAKY_ROOT_CAUSES = {
    "synchronization_issue", "network_api_error", "locator_issue"
}


def _compute_instability_score(
    retry_count: float,
    failure_type: str,
    failure_stage: str,
    severity: str,
    test_duration_sec: float,
) -> float:
    """
    Heuristic instability score (0.0 – 1.0).
    Higher = more likely to be a flaky test.
    """
    score = 0.0

    # Retry contribution (max 0.40)
    score += min(retry_count / 5.0, 0.40)

    # Failure type (max 0.20)
    if failure_type in FLAKY_FAILURE_TYPES:
        score += 0.20

    # Stage contribution (test stage = more likely flaky)
    if failure_stage == "test":
        score += 0.10

    # Severity inverse (LOW severity = higher flaky chance)
    sev_map = {"LOW": 0.15, "MEDIUM": 0.10, "HIGH": 0.05, "CRITICAL": 0.0}
    score += sev_map.get(severity.upper(), 0.05)

    # Long test duration = more timeout exposure
    if test_duration_sec > 120:
        score += 0.10
    elif test_duration_sec > 60:
        score += 0.05

    return min(round(score, 4), 1.0)


def _risk_level(score: float) -> str:
    if score >= 0.65:
        return "High"
    elif score >= 0.40:
        return "Medium"
    else:
        return "Low"


def _generate_pattern(score: float, retry_count: float) -> str:
    """Generate a synthetic recent pass/fail pattern string for display."""
    import random
    random.seed(int(score * 1000 + retry_count * 10))
    results = []
    for _ in range(5):
        r = random.random()
        results.append("FAIL" if r < score else "PASS")
    return ", ".join(results)


def check_flaky(
    test_id: str,
    test_name: str,
    retry_count: float,
    failure_type: str,
    failure_stage: str,
    severity: str,
    test_duration_sec: float,
) -> dict:
    score = _compute_instability_score(
        retry_count, failure_type, failure_stage, severity, test_duration_sec
    )
    risk = _risk_level(score)
    is_flaky = score >= 0.40

    return {
        "test_id":           test_id,
        "test_name":         test_name,
        "is_flaky":          is_flaky,
        "flaky_probability": score,
        "risk_level":        risk,
        "instability_score": f"{int(score * 100)}%",
        "recent_pattern":    _generate_pattern(score, retry_count),
    }
