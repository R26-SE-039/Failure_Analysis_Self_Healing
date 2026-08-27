import unittest

from app.routers.analyze import _classification_from_root_cause
from app.services.repair_evidence_service import (
    RepairEvidenceService,
)
from app.services.secret_redaction import (
    bounded_sanitized_text,
    contains_secret,
    redact_secrets,
)


class SecretRedactionTests(unittest.TestCase):
    def test_redacts_credentials_without_returning_value(self):
        sanitized = redact_secrets(
            "api_key=hidden-value-12345"
        )

        self.assertIn("[REDACTED:", sanitized)
        self.assertNotIn("hidden-value-12345", sanitized)
        self.assertFalse(contains_secret(sanitized))

    def test_evidence_stores_hash_and_bounded_excerpt(self):
        raw = "\n".join(
            [f"line {index}" for index in range(20)]
            + [
                "api_key=hidden-value-12345",
                "SyntaxError: '(' was never closed",
            ]
        )
        evidence = RepairEvidenceService(
            max_excerpt_lines=5,
            max_excerpt_chars=500,
        ).extract(
            raw,
            {
                "error_type": "SyntaxError",
                "error_message": (
                    "SyntaxError: '(' was never closed"
                ),
                "failed_file": "app/user_service.py",
                "failed_line": "10",
            },
        )

        self.assertEqual(
            len(evidence.log_content_sha256),
            64,
        )
        self.assertLessEqual(
            len(evidence.sanitized_log_excerpt.splitlines()),
            5,
        )
        self.assertNotIn(
            "hidden-value-12345",
            evidence.sanitized_log_excerpt,
        )

    def test_classification_response_redacts_error_evidence(self):
        response = _classification_from_root_cause(
            {
                "final_root_cause": "application_defect",
                "ml_prediction": "application_defect",
                "ml_confidence_percentage": 81.0,
                "detected_error": {
                    "error_type": "SyntaxError",
                    "error_message": (
                        "api_key=hidden-value-12345"
                    ),
                    "failed_file": "app/user_service.py",
                    "failed_line": "10",
                },
            }
        )

        message = response["detected_error"]["error_message"]
        self.assertNotIn("hidden-value-12345", message)
        self.assertIn("[REDACTED:", message)


if __name__ == "__main__":
    unittest.main()
