from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import joblib


class RootCauseService:
    """Analyze GitHub Actions logs using the trained nine-class model."""

    def __init__(self) -> None:
        # Current file:
        # backend/app/services/root_cause_service.py
        #
        # parents[3] points to the project root.
        project_root = Path(__file__).resolve().parents[3]

        model_path = (
            project_root
            / "research"
            / "models"
            / "best_9class_root_cause_model.joblib"
        )

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {model_path}"
            )

        self.model = joblib.load(model_path)

        if hasattr(self.model, "classes_"):
            self.classes = self.model.classes_
        else:
            self.classes = (
                self.model.named_steps["classifier"].classes_
            )

        print(f"Root-cause model loaded from: {model_path}")
        print(f"Supported classes: {self.classes}")

    @staticmethod
    def remove_ansi(text: str) -> str:
        """Remove terminal colour/control characters."""

        return re.sub(
            r"\x1b\[[0-9;]*m",
            "",
            text,
        )

    @staticmethod
    def detect_stage(log: str) -> str:
        lower_log = log.lower()

        if any(
            value in lower_log
            for value in [
                "secret scanning",
                "security gate",
                "sast",
                "npm audit",
                "vulnerability",
            ]
        ):
            return "security"

        if any(
            value in lower_log
            for value in [
                "kubectl",
                "imagepullbackoff",
                "rollout",
                "deployment",
                "readiness probe",
                "helm upgrade",
            ]
        ):
            return "deploy"

        if any(
            value in lower_log
            for value in [
                "pip install",
                "npm install",
                "npm ci",
                "requirements.txt",
                "package-lock.json",
            ]
        ):
            return "dependency"

        if any(
            value in lower_log
            for value in [
                "pytest",
                "jest",
                "test session starts",
                "complete job name: test",
            ]
        ):
            return "test"

        if "build" in lower_log:
            return "build"

        return "unknown"

    @staticmethod
    def detect_language(log: str) -> str:
        lower_log = log.lower()

        if ".py" in lower_log or "pytest" in lower_log:
            return "Python"

        if (
            ".js" in lower_log
            or ".ts" in lower_log
            or "npm " in lower_log
            or "jest" in lower_log
        ):
            return "NodeJS"

        if ".java" in lower_log or "maven" in lower_log:
            return "Java"

        if ".go" in lower_log:
            return "Go"

        if ".rs" in lower_log or "cargo" in lower_log:
            return "Rust"

        if ".cpp" in lower_log:
            return "C++"

        return "unknown"

    @staticmethod
    def find_failed_file(log: str) -> tuple[str, str]:
        patterns = [
            # File ".../app/user_service.py", line 10
            r'File\s+"[^"]*?'
            r"((?:app|src|tests?)/[^\"']+)"
            r'",\s+line\s+(\d+)',

            # file .../tests/test_user_service.py, line 6
            r"file\s+.*?"
            r"((?:app|src|tests?)/[^,\s]+),"
            r"\s+line\s+(\d+)",

            # tests/test_user_service.py:6
            r"((?:app|src|tests?)/[^\s:]+):(\d+)",
        ]

        matches: list[tuple[str, str]] = []

        for pattern in patterns:
            matches.extend(
                re.findall(
                    pattern,
                    log,
                    flags=re.IGNORECASE,
                )
            )

        if not matches:
            return "unknown", "unknown"

        file_name, line_number = matches[-1]

        return (
            file_name.replace("\\", "/"),
            str(line_number),
        )

    def extract_error_details(
        self,
        raw_log: str,
    ) -> dict[str, Any]:
        clean_log = self.remove_ansi(raw_log)
        lower_log = clean_log.lower()

        failed_file, failed_line = self.find_failed_file(
            clean_log
        )

        missing_fixture_match = re.search(
            r"fixture ['\"]([^'\"]+)['\"] not found",
            clean_log,
            flags=re.IGNORECASE,
        )

        missing_module_match = re.search(
            r"No module named ['\"]([^'\"]+)['\"]",
            clean_log,
            flags=re.IGNORECASE,
        )

        missing_fixture = None
        missing_module = None

        if missing_fixture_match:
            missing_fixture = missing_fixture_match.group(1)

            error_type = "FixtureError"
            error_message = (
                f"fixture '{missing_fixture}' not found"
            )

        elif missing_module_match:
            missing_module = missing_module_match.group(1)

            error_type = "ModuleNotFoundError"
            error_message = (
                f"No module named '{missing_module}'"
            )

            # Local package exists in the repository but cannot
            # be imported by GitHub Actions.
            if missing_module.lower() in {"app", "src"}:
                failed_file = ".github/workflows/test.yml"
                failed_line = "unknown"

        else:
            error_patterns = [
                (
                    "SyntaxError",
                    r"SyntaxError:\s*(.+)",
                ),
                (
                    "DependencyResolutionError",
                    r"ResolutionImpossible|"
                    r"npm ERR!.*ERESOLVE|"
                    r"package-lock\.json.*not.*sync",
                ),
                (
                    "NetworkError",
                    r"EAI_AGAIN|"
                    r"ConnectTimeout|"
                    r"Connection reset by peer|"
                    r"Connection refused|"
                    r"502 Bad Gateway|"
                    r"503 Service Unavailable|"
                    r"504 Gateway Timeout",
                ),
                (
                    "InfrastructureResourceError",
                    r"no space left on device|"
                    r"out of memory|"
                    r"exit code 137|"
                    r"maximum execution time",
                ),
                (
                    "DeploymentError",
                    r"ImagePullBackOff|"
                    r"rollout.*timed out|"
                    r"readiness probe failed|"
                    r"migration.*failed",
                ),
                (
                    "SecurityPolicyError",
                    r"secret scanning.*failed|"
                    r"security gate failed|"
                    r"critical.*vulnerability|"
                    r"SAST.*failed",
                ),
                (
                    "WorkflowEnvironmentError",
                    r"environment variable .* not defined|"
                    r"permission denied|"
                    r"working directory.*not found",
                ),
                (
                    "AssertionError",
                    r"AssertionError:\s*(.+)",
                ),
                (
                    "TypeError",
                    r"TypeError:\s*(.+)",
                ),
                (
                    "NameError",
                    r"NameError:\s*(.+)",
                ),
            ]

            error_type = "UnknownError"
            error_message = "Unrecognized failure"

            for candidate_type, pattern in error_patterns:
                match = re.search(
                    pattern,
                    clean_log,
                    flags=re.IGNORECASE,
                )

                if match:
                    error_type = candidate_type

                    matching_lines = [
                        line.strip()
                        for line in clean_log.splitlines()
                        if re.search(
                            pattern,
                            line,
                            flags=re.IGNORECASE,
                        )
                    ]

                    if matching_lines:
                        error_message = matching_lines[-1]
                    else:
                        error_message = candidate_type

                    break

        important_patterns = [
            r"##\[error\]",
            r"\bERROR\b",
            r"\bFAILED\b",
            r"Traceback",
            r"Exception",
            r"SyntaxError",
            r"ModuleNotFoundError",
            r"fixture .* not found",
            r"EAI_AGAIN",
            r"timed out",
            r"connection refused",
            r"connection reset",
            r"no space left",
            r"out of memory",
            r"ImagePullBackOff",
            r"vulnerability",
            r"security gate",
            r"Process completed with exit code",
        ]

        important_lines = [
            line.strip()
            for line in clean_log.splitlines()
            if any(
                re.search(
                    pattern,
                    line,
                    flags=re.IGNORECASE,
                )
                for pattern in important_patterns
            )
        ]

        if important_lines:
            log_excerpt = "\n".join(
                important_lines[-40:]
            )
        else:
            log_excerpt = "\n".join(
                clean_log.splitlines()[-80:]
            )

        if failed_file != "unknown":
            stack_trace = (
                f"{failed_file}:{failed_line}"
            )
        else:
            stack_trace = "unknown"

        return {
            "stage": self.detect_stage(clean_log),
            "language": self.detect_language(clean_log),
            "error_type": error_type,
            "error_message": error_message,
            "failed_file": failed_file,
            "failed_line": failed_line,
            "stack_trace": stack_trace,
            "missing_fixture": missing_fixture,
            "missing_module": missing_module,
            "log_excerpt": log_excerpt,
        }

    @staticmethod
    def build_model_input(
        details: dict[str, Any],
    ) -> str:
        """Build the same input structure used for training."""

        return " | ".join(
            [
                f"stage={details['stage']}",
                f"language={details['language']}",
                f"error_type={details['error_type']}",
                f"error_message={details['error_message']}",
                f"stack_trace={details['stack_trace']}",
                f"failed_file={details['failed_file']}",
                f"log={details['log_excerpt']}",
                (
                    "context=attempt=1; "
                    "elapsed_ms=0; worker_slot=1"
                ),
            ]
        )

    @staticmethod
    def choose_action(
        root_cause: str,
    ) -> str:
        actions = {
            "application_defect":
                "start_mcp_code_repair",

            "test_script_issue":
                "send_to_test_script_component",

            "network_issue":
                "recommend_retry",

            "dependency_issue":
                "dependency_patch_or_manual_review",

            "workflow_environment_issue":
                "review_workflow_configuration",

            "infrastructure_resource_issue":
                "retry_or_resource_review",

            "deployment_issue":
                "rollback_or_deployment_review",

            "security_policy_issue":
                "block_and_security_review",

            "other_or_unknown":
                "manual_review",
        }

        return actions.get(
            root_cause,
            "manual_review",
        )

    def apply_clear_rules(
        self,
        details: dict[str, Any],
        ml_prediction: str,
    ) -> tuple[str, str]:
        """Validate only highly deterministic failures."""

        if ml_prediction != "other_or_unknown":
            return (
                ml_prediction,
                "machine_learning",
            )

        error_type = details["error_type"].lower()
        failed_file = details["failed_file"].lower()
        missing_module = (
            details["missing_module"] or ""
        ).lower()

        if (
            error_type == "fixtureerror"
            and failed_file.startswith(
                ("test/", "tests/")
            )
        ):
            return (
                "test_script_issue",
                "deterministic_rule",
            )

        if (
            error_type == "syntaxerror"
            and failed_file.startswith(
                ("app/", "src/")
            )
        ):
            return (
                "application_defect",
                "deterministic_rule",
            )

        if (
            error_type == "syntaxerror"
            and failed_file.startswith(
                ("test/", "tests/")
            )
        ):
            return (
                "test_script_issue",
                "deterministic_rule",
            )

        if (
            error_type == "modulenotfounderror"
            and missing_module in {"app", "src"}
        ):
            return (
                "workflow_environment_issue",
                "deterministic_rule",
            )

        return (
            ml_prediction,
            "machine_learning",
        )

    def analyze(
        self,
        raw_log: str,
    ) -> dict[str, Any]:
        if not raw_log.strip():
            raise ValueError(
                "The uploaded log file is empty."
            )

        details = self.extract_error_details(
            raw_log
        )

        model_input = self.build_model_input(
            details
        )

        probabilities = self.model.predict_proba(
            [model_input]
        )[0]

        best_index = int(
            probabilities.argmax()
        )

        ml_prediction = str(
            self.classes[best_index]
        )

        ml_confidence = float(
            probabilities[best_index]
        )

        final_root_cause, decision_source = (
            self.apply_clear_rules(
                details,
                ml_prediction,
            )
        )

        probability_map = {
            str(label): round(
                float(probability) * 100,
                2,
            )
            for label, probability in zip(
                self.classes,
                probabilities,
            )
        }

        final_confidence_percentage = probability_map.get(
            final_root_cause,
            round(ml_confidence * 100, 2),
        )

        return {
            "detected_error": {
                "error_type":
                    details["error_type"],

                "error_message":
                    details["error_message"],

                "failed_file":
                    details["failed_file"],

                "failed_line":
                    details["failed_line"],

                "missing_fixture":
                    details["missing_fixture"],

                "missing_module":
                    details["missing_module"],
            },

            "ml_prediction":
                ml_prediction,

            "ml_confidence_percentage":
                round(ml_confidence * 100, 2),

            "final_confidence_percentage":
                final_confidence_percentage,

            "probabilities":
                probability_map,

            "final_root_cause":
                final_root_cause,

            "decision_source":
                decision_source,

            "action":
                self.choose_action(
                    final_root_cause
                ),
        }


root_cause_service = RootCauseService()
