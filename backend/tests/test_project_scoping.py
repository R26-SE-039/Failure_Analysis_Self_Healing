import unittest
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.failure import Failure
from app.models.flaky_test import FlakyTest
from app.models.healing import HealingAction
from app.models.notification import Notification
from app.models.repair_attempt import RepairAttempt


class ProjectScopingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "project_scoping.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.TestSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        def override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.org_id = uuid4()
        self.project_a = uuid4()
        self.project_b = uuid4()
        self.iteration_id = uuid4()
        self.user_story_id = uuid4()
        self.suite_id = uuid4()
        self.execution_id = uuid4()
        self.test_run_id = uuid4()
        self.created_project_ids = {self.project_a, self.project_b}
        self._seed_records()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _scope(self, project_id):
        return {
            "organization_id": str(self.org_id),
            "project_id": str(project_id),
        }

    def _seed_records(self):
        with self.TestSessionLocal() as db:
            failure_a = Failure(
                organization_id=self.org_id,
                project_id=self.project_a,
                test_id=f"TEST-A-{uuid4().hex[:8]}",
                test_name="Project A failure",
                pipeline="CI",
                status="FAIL",
                root_cause="application_defect",
            )
            failure_b = Failure(
                organization_id=self.org_id,
                project_id=self.project_b,
                test_id=f"TEST-B-{uuid4().hex[:8]}",
                test_name="Project B failure",
                pipeline="CI",
                status="FAIL",
                root_cause="application_defect",
            )
            db.add_all([failure_a, failure_b])
            db.flush()

            self.failure_a_test_id = failure_a.test_id
            self.failure_b_test_id = failure_b.test_id
            self.healing_b_id = f"HEAL-B-{uuid4().hex[:8]}"
            self.notification_b_id = None
            self.flaky_b_code = f"FLAKY-B-{uuid4().hex[:8]}"
            self.attempt_b_id = f"REPAIR-B-{uuid4().hex[:8]}"

            db.add_all(
                [
                    HealingAction(
                        failure_id=failure_a.id,
                        healing_id=f"HEAL-A-{uuid4().hex[:8]}",
                        failure_test_id=failure_a.test_id,
                        test_name=failure_a.test_name,
                        repair_type="Manual",
                        old_value="",
                        new_value="",
                        status="Pending",
                    ),
                    HealingAction(
                        failure_id=failure_b.id,
                        healing_id=self.healing_b_id,
                        failure_test_id=failure_b.test_id,
                        test_name=failure_b.test_name,
                        repair_type="Manual",
                        old_value="",
                        new_value="",
                        status="Pending",
                    ),
                    Notification(
                        failure_id=failure_a.id,
                        failure_test_id=failure_a.test_id,
                        test_name=failure_a.test_name,
                        root_cause="application_defect",
                        message="A",
                        target="developer",
                    ),
                    Notification(
                        failure_id=failure_b.id,
                        failure_test_id=failure_b.test_id,
                        test_name=failure_b.test_name,
                        root_cause="application_defect",
                        message="B",
                        target="developer",
                    ),
                    FlakyTest(
                        organization_id=self.org_id,
                        project_id=self.project_a,
                        test_code=f"FLAKY-A-{uuid4().hex[:8]}",
                        test_name="Project A flaky",
                        instability_score="80%",
                        recent_pattern="fail/pass",
                        risk_level="High",
                    ),
                    FlakyTest(
                        organization_id=self.org_id,
                        project_id=self.project_b,
                        test_code=self.flaky_b_code,
                        test_name="Project B flaky",
                        instability_score="20%",
                        recent_pattern="pass/fail",
                        risk_level="Low",
                    ),
                    RepairAttempt(
                        failure_id=failure_b.id,
                        attempt_id=self.attempt_b_id,
                        failure_test_id=failure_b.test_id,
                        status="eligible",
                        mode="read_only",
                        eligible=True,
                        eligibility_code="eligible",
                        eligibility_reason="Eligible",
                        predicted_root_cause="application_defect",
                        confidence=0.9,
                        decision_source="test",
                        selected_action="start_mcp_code_repair",
                        error_type="AssertionError",
                        error_message="sanitized",
                        candidate_file="app/service.py",
                        candidate_line=1,
                        log_content_sha256="a" * 64,
                        sanitized_log_excerpt="sanitized",
                        github_changes_made=False,
                    ),
                ]
            )
            db.commit()

    def test_failures_dashboard_healing_notifications_and_analytics_are_scoped(self):
        failure_response = self.client.get(
            "/failures/",
            params=self._scope(self.project_a),
        )
        self.assertEqual(failure_response.status_code, 200)
        failure_names = {
            item["test_name"] for item in failure_response.json()["data"]
        }
        self.assertIn("Project A failure", failure_names)
        self.assertNotIn("Project B failure", failure_names)

        dashboard = self.client.get(
            "/dashboard/summary",
            params=self._scope(self.project_a),
        )
        self.assertEqual(dashboard.status_code, 200)
        recent_names = {
            item["test_name"] for item in dashboard.json()["recent_failures"]
        }
        self.assertIn("Project A failure", recent_names)
        self.assertNotIn("Project B failure", recent_names)

        trend = self.client.get(
            "/dashboard/trend",
            params=self._scope(self.project_a),
        )
        self.assertEqual(trend.status_code, 200)

        healing = self.client.get(
            "/healing/",
            params=self._scope(self.project_a),
        )
        self.assertEqual(healing.status_code, 200)
        healing_names = {
            item["test_name"] for item in healing.json()["data"]
        }
        self.assertIn("Project A failure", healing_names)
        self.assertNotIn("Project B failure", healing_names)

        notifications = self.client.get(
            "/notifications/",
            params=self._scope(self.project_a),
        )
        self.assertEqual(notifications.status_code, 200)
        notification_names = {
            item["test_name"] for item in notifications.json()["data"]
        }
        self.assertIn("Project A failure", notification_names)
        self.assertNotIn("Project B failure", notification_names)

        flaky = self.client.get(
            "/analytics/flaky-tests",
            params=self._scope(self.project_a),
        )
        self.assertEqual(flaky.status_code, 200)
        flaky_names = {
            item["test_name"] for item in flaky.json()["data"]
        }
        self.assertIn("Project A flaky", flaky_names)
        self.assertNotIn("Project B flaky", flaky_names)

    def test_project_a_cannot_delete_or_access_project_b_resources(self):
        details = self.client.get(
            f"/failures/{self.failure_b_test_id}",
            params=self._scope(self.project_a),
        )
        self.assertEqual(details.status_code, 404)

        delete_failure = self.client.delete(
            f"/failures/{self.failure_b_test_id}",
            params=self._scope(self.project_a),
        )
        self.assertEqual(delete_failure.status_code, 404)

        delete_flaky = self.client.delete(
            f"/analytics/flaky-tests/{self.flaky_b_code}",
            params=self._scope(self.project_a),
        )
        self.assertEqual(delete_flaky.status_code, 404)

        repair = self.client.get(
            f"/api/repairs/{self.attempt_b_id}",
            params=self._scope(self.project_a),
        )
        self.assertEqual(repair.status_code, 404)

        plan = self.client.post(
            f"/api/repairs/{self.attempt_b_id}/plan",
            params=self._scope(self.project_a),
            json={"confirm_read_only": True},
        )
        self.assertEqual(plan.status_code, 404)

        publish = self.client.post(
            f"/api/repairs/{self.attempt_b_id}/publish",
            params=self._scope(self.project_a),
            json={"confirm_publish": True},
        )
        self.assertEqual(publish.status_code, 404)

    def test_project_owned_endpoints_require_scope(self):
        checks = [
            ("get", "/dashboard/summary", None),
            ("get", "/dashboard/trend", None),
            ("get", "/dashboard/root-cause-breakdown", None),
            ("get", "/failures/", None),
            ("get", f"/failures/{self.failure_a_test_id}", None),
            ("delete", f"/failures/{self.failure_a_test_id}", None),
            ("get", "/healing/", None),
            ("delete", f"/healing/{self.healing_b_id}", None),
            ("get", "/analytics/flaky-tests", None),
            ("delete", f"/analytics/flaky-tests/{self.flaky_b_code}", None),
            ("get", "/notifications/", None),
            ("get", "/api/repairs/history", None),
            ("get", f"/api/repairs/{self.attempt_b_id}", None),
            ("post", f"/api/repairs/{self.attempt_b_id}/plan", {"confirm_read_only": True}),
            ("post", f"/api/repairs/{self.attempt_b_id}/publish", {"confirm_publish": True}),
        ]

        for method, path, json_payload in checks:
            with self.subTest(method=method, path=path):
                request = getattr(self.client, method)
                kwargs = {}
                if json_payload is not None:
                    kwargs["json"] = json_payload
                response = request(path, **kwargs)
                self.assertIn(response.status_code, {400, 422})

    def test_repair_history_is_scoped(self):
        history_a = self.client.get(
            "/api/repairs/history",
            params=self._scope(self.project_a),
        )
        self.assertEqual(history_a.status_code, 200)
        self.assertEqual(history_a.json(), [])

        history_b = self.client.get(
            "/api/repairs/history",
            params=self._scope(self.project_b),
        )
        self.assertEqual(history_b.status_code, 200)
        self.assertEqual(
            [item["attempt_id"] for item in history_b.json()],
            [self.attempt_b_id],
        )

    def test_analyze_persists_shared_traceability_ids(self):
        payload = {
            **self._scope(self.project_a),
            "iteration_id": str(self.iteration_id),
            "user_story_id": str(self.user_story_id),
            "suite_id": str(self.suite_id),
            "execution_id": str(self.execution_id),
            "test_run_id": str(self.test_run_id),
            "test_name": "Traceability smoke",
            "pipeline": "CI",
            "error_message": "AssertionError expected true",
            "stack_trace": "tests/test_demo.py:10",
            "logs": "AssertionError expected true",
        }
        response = self.client.post("/analyze/", json=payload)
        self.assertEqual(response.status_code, 200)
        test_id = response.json()["test_id"]

        with self.TestSessionLocal() as db:
            failure = (
                db.query(Failure)
                .filter(Failure.test_id == test_id)
                .first()
            )
            self.assertEqual(failure.organization_id, self.org_id)
            self.assertEqual(failure.project_id, self.project_a)
            self.assertEqual(failure.iteration_id, self.iteration_id)
            self.assertEqual(failure.user_story_id, self.user_story_id)
            self.assertEqual(failure.suite_id, self.suite_id)
            self.assertEqual(failure.execution_id, self.execution_id)
            self.assertEqual(failure.test_run_id, self.test_run_id)

    def test_analyze_requires_organization_and_project_ids(self):
        response = self.client.post(
            "/analyze/",
            json={
                "test_name": "Manual smoke",
                "pipeline": "CI",
                "error_message": "AssertionError expected true",
                "logs": "AssertionError expected true",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_manual_analyze_can_omit_optional_upstream_ids(self):
        response = self.client.post(
            "/analyze/",
            json={
                **self._scope(self.project_a),
                "test_name": "Manual smoke",
                "pipeline": "CI",
                "error_message": "AssertionError expected true",
                "logs": "AssertionError expected true",
            },
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
