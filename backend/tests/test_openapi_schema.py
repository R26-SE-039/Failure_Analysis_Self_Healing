import unittest

from fastapi.testclient import TestClient

from app.main import app


class OpenApiSchemaTests(unittest.TestCase):
    def test_openapi_schema_generates_and_includes_github_actions_paths(self):
        schema = app.openapi()

        self.assertIsInstance(schema, dict)
        self.assertIn("paths", schema)
        self.assertIn("/api/github/actions/failed-runs", schema["paths"])
        self.assertIn("/api/github/actions/runs/{run_id}", schema["paths"])
        self.assertIn("/api/github/actions/runs/{run_id}/evidence", schema["paths"])
        self.assertIn(
            "/api/github/actions/runs/{run_id}/jobs/{job_id}/classify",
            schema["paths"],
        )
        self.assertIn(
            "/api/github/actions/runs/{run_id}/jobs/{job_id}/analyze",
            schema["paths"],
        )

    def test_openapi_schema_defines_bearer_security_for_github_actions(self):
        schema = app.openapi()
        schemes = schema["components"]["securitySchemes"]

        self.assertIn("BearerAuth", schemes)
        self.assertEqual(schemes["BearerAuth"]["type"], "http")
        self.assertEqual(schemes["BearerAuth"]["scheme"], "bearer")

        expected_operations = [
            ("/api/github/actions/failed-runs", "get"),
            ("/api/github/actions/runs/{run_id}", "get"),
            ("/api/github/actions/runs/{run_id}/evidence", "get"),
            ("/api/github/actions/runs/{run_id}/jobs/{job_id}/classify", "post"),
            ("/api/github/actions/runs/{run_id}/jobs/{job_id}/analyze", "post"),
            ("/api/github/actions/resolve", "post"),
        ]
        for path, method in expected_operations:
            with self.subTest(path=path, method=method):
                operation = schema["paths"][path][method]
                self.assertIn({"BearerAuth": []}, operation.get("security", []))

    def test_openapi_json_endpoint_returns_success(self):
        response = TestClient(app).get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("paths", response.json())


if __name__ == "__main__":
    unittest.main()
