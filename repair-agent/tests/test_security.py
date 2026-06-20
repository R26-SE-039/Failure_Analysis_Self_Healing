import unittest

from repair_agent.security import (
    SecurityError,
    normalize_repository_path,
    reject_sensitive_content,
)


class SecurityTests(unittest.TestCase):
    def test_accepts_application_source_path(self):
        self.assertEqual(
            normalize_repository_path(
                "app/services/user_service.py"
            ),
            "app/services/user_service.py",
        )

    def test_rejects_path_traversal_and_protected_paths(self):
        for path in (
            "../secret.txt",
            ".env",
            "auth/login.py",
            "migrations/001.sql",
            "certificates/server.pem",
        ):
            with self.subTest(path=path):
                with self.assertRaises(SecurityError):
                    normalize_repository_path(path)

    def test_rejects_secret_content_without_echoing_it(self):
        with self.assertRaises(SecurityError):
            reject_sensitive_content(
                "authorization: bearer hidden-value"
            )


if __name__ == "__main__":
    unittest.main()
