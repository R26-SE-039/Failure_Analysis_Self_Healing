import hashlib
import json
import re
import unittest
from pathlib import Path

import sklearn

from app.routers.analyze import AnalyzeRequest, _build_log_text
from app.services.root_cause_service import root_cause_service


TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parents[1]
FIXTURE_PATH = TESTS_DIR / "fixtures" / "0_test.txt"
CONTRACT_PATH = (
    TESTS_DIR / "fixtures" / "application_defect_contract.json"
)
MODEL_PATH = (
    PROJECT_ROOT
    / "research"
    / "models"
    / "best_9class_root_cause_model.joblib"
)


def _frontend_request(raw_log: str) -> AnalyzeRequest:
    first_line = raw_log.split("\n")[0]
    error_message = (
        first_line[:500]
        if first_line
        else raw_log[:500]
    )
    stack_trace = "\n".join(
        line
        for line in raw_log.split("\n")
        if re.search(r"at\s|Exception|Error", line)
    )
    return AnalyzeRequest(
        test_name="0_test",
        pipeline="GitHub Actions",
        error_message=error_message,
        stack_trace=stack_trace,
        logs=raw_log,
    )


class ClassifierRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )
        cls.raw_log = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_application_defect_contract(self):
        fixture_hash = hashlib.sha256(
            self.raw_log.encode("utf-8")
        ).hexdigest().upper()
        model_hash = hashlib.sha256(
            MODEL_PATH.read_bytes()
        ).hexdigest().upper()

        request = _frontend_request(self.raw_log)
        analysis_text = _build_log_text(request)
        details = root_cause_service.extract_error_details(
            analysis_text
        )
        model_input = root_cause_service.build_model_input(
            details
        )
        probabilities = root_cause_service.model.predict_proba(
            [model_input]
        )[0]
        best_index = int(probabilities.argmax())

        self.assertEqual(
            sklearn.__version__,
            self.contract["sklearn_version"],
        )
        self.assertEqual(
            fixture_hash,
            self.contract["fixture_sha256"],
        )
        self.assertEqual(
            model_hash,
            self.contract["model_artifact_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                model_input.encode("utf-8")
            ).hexdigest().upper(),
            self.contract["model_input_sha256"],
        )
        self.assertEqual(
            [str(label) for label in root_cause_service.classes],
            self.contract["class_order"],
        )
        self.assertEqual(
            str(root_cause_service.classes[best_index]),
            self.contract["predicted_class"],
        )
        self.assertAlmostEqual(
            float(probabilities[best_index]),
            self.contract["confidence"],
            delta=self.contract[
                "confidence_absolute_tolerance"
            ],
        )
        self.assertEqual(
            details["error_type"],
            self.contract["detected_error"]["error_type"],
        )
        self.assertEqual(
            details["failed_file"],
            self.contract["detected_error"]["failed_file"],
        )
        self.assertEqual(
            details["failed_line"],
            self.contract["detected_error"]["failed_line"],
        )


if __name__ == "__main__":
    unittest.main()
