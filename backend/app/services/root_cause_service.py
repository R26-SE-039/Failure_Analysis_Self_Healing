from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import joblib


MAVEN_COMPILER_DIAGNOSTIC_PATTERN = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}T\S+Z\s+)?(?:\[[A-Z]+\]\s*)?"
    r"(?P<file>(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+\.java):"
    r"\[(?P<line>\d+),(?P<column>\d+)\]\s*(?P<message>.+?)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


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

        if "stage=compile" in lower_log or MAVEN_COMPILER_DIAGNOSTIC_PATTERN.search(log):
            return "compile"

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
    def normalize_failed_source_path(path: str) -> str | None:
        normalized = path.replace("\\", "/").strip().strip('"').strip("'")
        if not normalized:
            return None

        runner_match = re.match(
            r"^/home/runner/work/(?P<repo>[A-Za-z0-9_.-]+)/(?P=repo)/(?P<relative>.+)$",
            normalized,
            flags=re.IGNORECASE,
        )
        if not runner_match:
            runner_match = re.match(
                r"^[A-Za-z]:/a/(?P<repo>[A-Za-z0-9_.-]+)/(?P=repo)/(?P<relative>.+)$",
                normalized,
                flags=re.IGNORECASE,
            )
        if runner_match:
            normalized = runner_match.group("relative")

        if (
            not normalized
            or normalized.startswith("/")
            or normalized.startswith("//")
            or re.match(r"^[A-Za-z]:/", normalized)
        ):
            return None

        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return None
        if not normalized.lower().startswith(("app/", "src/", "test/", "tests/")):
            return None
        return normalized

    @staticmethod
    def find_java_compiler_diagnostic(log: str) -> dict[str, str] | None:
        for line in log.replace("\\", "/").splitlines():
            match = MAVEN_COMPILER_DIAGNOSTIC_PATTERN.search(line.strip())
            if not match:
                continue
            failed_file = RootCauseService.normalize_failed_source_path(
                match.group("file")
            )
            failed_line = match.group("line")
            message = match.group("message").strip()
            if failed_file and failed_line.isdigit() and int(failed_line) > 0 and message:
                return {
                    "error_type": "CompilationError",
                    "error_message": message,
                    "failed_file": failed_file,
                    "failed_line": failed_line,
                }
        return None

    @staticmethod
    def find_failed_file(
        log: str,
        error_type: str,
    ) -> tuple[str, str]:
        """
        Find the file that actually caused the failure.

        Pytest summaries often name the test module last, but SyntaxError
        tracebacks point at the source file that Python could not parse.
        """

        normalized_log = log.replace("\\", "/")
        normalized_error = error_type.lower()

        if normalized_error == "syntaxerror":
            syntax_matches = re.findall(
                r'(?:E\s+)?File\s+"[^"]*?'
                r'((?:app|src|tests?)/[^"]+)",\s+line\s+(\d+)',
                normalized_log,
                flags=re.IGNORECASE,
            )

            if syntax_matches:
                source_matches = [
                    match
                    for match in syntax_matches
                    if match[0].lower().startswith(("app/", "src/"))
                ]

                selected = (
                    source_matches[-1]
                    if source_matches
                    else syntax_matches[-1]
                )

                return (
                    selected[0],
                    str(selected[1]),
                )

        if normalized_error == "fixtureerror":
            fixture_match = re.search(
                r"file\s+.*?"
                r"((?:test|tests)/[^,\s]+),"
                r"\s+line\s+(\d+)",
                normalized_log,
                flags=re.IGNORECASE,
            )

            if fixture_match:
                return (
                    fixture_match.group(1),
                    fixture_match.group(2),
                )

        patterns = [
            # File ".../app/user_service.py", line 10
            r'File\s+"[^"]*?'
            r'((?:app|src|tests?)/[^"]+)",'
            r"\s+line\s+(\d+)",

            # .github/workflows/test.yml
            r"(\.github/workflows/[^\s:]+)()",

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
                    normalized_log,
                    flags=re.IGNORECASE,
                )
            )

        if not matches:
            return "unknown", "unknown"

        file_name, line_number = matches[-1]
        line_number = line_number or "unknown"

        return (
            file_name.replace("\\", "/"),
            str(line_number),
        )

    @staticmethod
    def find_run_context(log: str) -> str | None:
        context_match = re.search(
            r"attempt=\d+;\s*elapsed_ms=\d+;\s*worker_slot=\d+",
            log,
            flags=re.IGNORECASE,
        )

        if not context_match:
            return None

        return context_match.group(0)

    def extract_error_details(
        self,
        raw_log: str,
    ) -> dict[str, Any]:
        clean_log = self.remove_ansi(raw_log)

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
        java_compiler_diagnostic = self.find_java_compiler_diagnostic(clean_log)

        if java_compiler_diagnostic:
            error_type = java_compiler_diagnostic["error_type"]
            error_message = java_compiler_diagnostic["error_message"]

        elif missing_fixture_match:
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
                    "ConfigurationValueError",
                    r"ConfigurationValueError:\s*(.+)|"
                    r"\b[A-Z_]+ contains invalid value|"
                    r"\b[A-Z_]+ must be an integer|"
                    r"points to an invalid endpoint",
                ),
                (
                    "MissingEnvironmentVariable",
                    r"MissingEnvironmentVariable:\s*(.+)|"
                    r"\b[A-Z_]+ is not defined",
                ),
                (
                    "ConfigurationParseError",
                    r"ConfigurationParseError:\s*(.+)|"
                    r"invalid YAML syntax|"
                    r"configuration file is not valid UTF-8|"
                    r"configuration does not match required schema",
                ),
                (
                    "SecretConfigurationError",
                    r"SecretConfigurationError:\s*(.+)|"
                    r"required secret .* is empty",
                ),
                (
                    "ShellNotFoundError",
                    r"ShellNotFoundError:\s*(.+)|"
                    r"pwsh executable not found",
                ),
                (
                    "WorkingDirectoryError",
                    r"WorkingDirectoryError:\s*(.+)|"
                    r"specified working directory does not exist|"
                    r"runner cannot access workspace directory",
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

        if java_compiler_diagnostic:
            failed_file = java_compiler_diagnostic["failed_file"]
            failed_line = java_compiler_diagnostic["failed_line"]
        else:
            failed_file, failed_line = self.find_failed_file(
                clean_log,
                error_type,
            )

        # Local package exists in the repository but cannot be imported
        # by GitHub Actions, so the workflow environment is the target.
        if (
            missing_module
            and missing_module.lower() in {"app", "src"}
        ):
            failed_file = ".github/workflows/test.yml"
            failed_line = "unknown"

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
            "run_context": self.find_run_context(clean_log),
        }

    @staticmethod
    def build_model_input(
        details: dict[str, Any],
    ) -> str:
        """Build the same input structure used for training."""

        parts = [
            f"stage={details['stage']}",
            f"language={details['language']}",
            f"error_type={details['error_type']}",
            f"error_message={details['error_message']}",
            f"stack_trace={details['stack_trace']}",
            f"failed_file={details['failed_file']}",
            f"log={details['log_excerpt']}",
        ]

        if details.get("run_context"):
            parts.append(
                f"context={details['run_context']}"
            )

        return " | ".join(parts)

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

        final_root_cause = ml_prediction
        decision_source = "machine_learning"

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

        model_input_sha256 = hashlib.sha256(
            model_input.encode("utf-8")
        ).hexdigest()

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

            "decision_reason":
                "Selected by the trained nine-class model.",

            "model_input_sha256":
                model_input_sha256,
        }


root_cause_service = RootCauseService()
