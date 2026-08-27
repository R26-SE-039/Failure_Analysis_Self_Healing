from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.analyze import AnalyzeRequest, run_analysis_pipeline
from app.services.failure_evidence_service import build_failure_evidence
from app.services.repair_evidence_service import RepairEvidence
from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubActionsService,
    GitHubRunUrlError,
)
from app.services.project_configuration_client import (
    ProjectConfigurationError,
    ProjectGitHubConfiguration,
    project_configuration_client,
)
from app.services.project_scope import ProjectScope, get_project_scope
from app.services.root_cause_service import root_cause_service
from app.services.secret_redaction import redact_secrets


MAX_FAILED_JOBS_FOR_EVIDENCE = 5
ROOT_CAUSE_MODEL_NAME = "best_9class_root_cause_model.joblib"
AUTO_HEAL_BRANCH_PREFIX = "auto-heal/"
AUTO_HEAL_ANALYSIS_REJECTION_MESSAGE = (
    "This workflow run belongs to a Component 3 repair branch and is excluded "
    "from recursive controlled-repair analysis."
)

router = APIRouter(
    prefix="/api/github/actions",
    tags=["GitHub Actions"],
)

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Paste the raw JWT. Swagger sends it as Authorization: Bearer <token>.",
)


def get_bearer_authorization(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Optional[str]:
    if credentials is None:
        return None
    return f"{credentials.scheme} {credentials.credentials}"


class GitHubRunRequest(BaseModel):
    project_id: UUID
    run_url: str = Field(min_length=1, max_length=500)


def _safe_http_exception(error: GitHubActionsApiError) -> HTTPException:
    return HTTPException(
        status_code=getattr(error, "status_code", 502),
        detail=str(error),
    )


async def _github_service_for_scope(
    *,
    scope: ProjectScope,
    authorization: Optional[str],
) -> tuple[ProjectGitHubConfiguration, GitHubActionsService]:
    github_config = await project_configuration_client.get_project_github_configuration(
        project_id=str(scope.project_id),
        authorization_header=authorization,
    )
    return github_config, GitHubActionsService(
        token=github_config.token,
        allowed_repositories={github_config.repository_full_name},
    )


def _failed_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        job for job in jobs
        if str(job.get("conclusion") or "").lower() == "failure"
    ]


def _failed_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        return []
    return [
        {
            "number": step.get("number"),
            "name": step.get("name"),
            "status": step.get("status"),
            "conclusion": step.get("conclusion"),
        }
        for step in steps
        if isinstance(step, dict)
        and str(step.get("conclusion") or "").lower() == "failure"
    ]


def _job_log_error(error: GitHubActionsApiError) -> dict[str, Any]:
    return {
        "status_code": getattr(error, "status_code", 502),
        "message": str(error),
    }


def _find_job_for_run(jobs: list[dict[str, Any]], job_id: int) -> dict[str, Any]:
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    raise HTTPException(
        status_code=404,
        detail="GitHub job was not found in the selected workflow run.",
    )


def _ensure_selected_job_failed(job: dict[str, Any]) -> None:
    conclusion = str(job.get("conclusion") or "").lower()
    if conclusion != "failure":
        raise HTTPException(
            status_code=400,
            detail="Only failed GitHub Actions jobs can be classified.",
        )


def _has_classifiable_evidence(evidence: dict[str, Any]) -> bool:
    return any(
        bool(evidence.get(field))
        for field in ("error_message", "stack_trace", "sanitized_log_excerpt")
    )


def _build_classifier_log_text(
    *,
    run: dict[str, Any],
    job: dict[str, Any],
    evidence: dict[str, Any],
    failed_steps: list[dict[str, Any]],
) -> str:
    pipeline = run.get("name") or run.get("display_title") or "GitHub Actions"
    failed_step_names = [
        str(step.get("name"))
        for step in failed_steps
        if step.get("name")
    ]
    sections = [
        f"pipeline={pipeline}",
        f"stage={evidence.get('failure_stage') or 'unknown'}",
        "severity=MEDIUM",
        "failure_type=GitHub Actions Job Failure",
        "",
        "FAILED JOB:",
        str(job.get("name") or ""),
        "",
        "FAILED STEPS:",
        "\n".join(failed_step_names),
        "",
        "ERROR MESSAGE:",
        str(evidence.get("error_message") or ""),
        "",
        "STACK TRACE:",
        str(evidence.get("stack_trace") or ""),
        "",
        "FULL LOGS:",
        str(evidence.get("sanitized_log_excerpt") or ""),
    ]
    return "\n".join(sections)


def _classification_preview_from_root_cause(result: dict[str, Any]) -> dict[str, Any]:
    probabilities = {
        label: round(float(probability) / 100, 4)
        for label, probability in result.get("probabilities", {}).items()
    }
    confidence_percentage = result.get(
        "final_confidence_percentage",
        result.get("ml_confidence_percentage", 0),
    )
    confidence = round(float(confidence_percentage) / 100, 4)
    ml_confidence = round(
        float(result.get("ml_confidence_percentage", 0)) / 100,
        4,
    )

    detected_error = result.get("detected_error")
    if isinstance(detected_error, dict):
        detected_error = {
            key: redact_secrets(value) if isinstance(value, str) else value
            for key, value in detected_error.items()
        }

    return {
        "root_cause": result["final_root_cause"],
        "confidence": confidence,
        "ml_prediction": result.get("ml_prediction"),
        "ml_confidence": ml_confidence,
        "final_confidence": confidence,
        "all_probabilities": probabilities,
        "model_used": ROOT_CAUSE_MODEL_NAME,
        "decision_source": result.get("decision_source"),
        "decision_reason": result.get("decision_reason"),
        "detected_error": detected_error,
        "model_input_sha256": result.get("model_input_sha256"),
    }


def _classifier_input_summary(
    *,
    run: dict[str, Any],
    job: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "test_name": job.get("name"),
        "pipeline": run.get("name") or run.get("display_title") or "GitHub Actions",
        "failure_stage": evidence.get("failure_stage") or "unknown",
        "failure_type": "GitHub Actions Job Failure",
        "error_message": evidence.get("error_message"),
        "stack_trace_present": bool(evidence.get("stack_trace")),
        "logs_excerpt_chars": len(str(evidence.get("sanitized_log_excerpt") or "")),
        "candidate_file": evidence.get("candidate_file"),
        "candidate_line": evidence.get("candidate_line"),
    }


def _source_run_for_analysis(
    *,
    github_config: ProjectGitHubConfiguration,
    run: dict[str, Any],
) -> dict[str, Any]:
    return {
        "owner": github_config.repository_owner,
        "repository": github_config.repository_name,
        "repository_full_name": github_config.repository_full_name,
        "run_id": run.get("run_id"),
        "run_url": run.get("html_url"),
        "head_sha": run.get("head_sha"),
        "head_branch": run.get("head_branch"),
        "default_branch": None,
        "workflow_name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "run_attempt": run.get("run_attempt", 1),
    }


def _repair_evidence_from_github_evidence(evidence: dict[str, Any]) -> RepairEvidence:
    return RepairEvidence(
        log_content_sha256=str(evidence.get("evidence_hash") or ""),
        sanitized_log_excerpt=str(evidence.get("sanitized_log_excerpt") or ""),
        error_type=str(evidence.get("error_type") or "UnknownError"),
        error_message=str(evidence.get("error_message") or "")[:1000],
        candidate_file=str(evidence.get("candidate_file") or "unknown"),
        candidate_line=evidence.get("candidate_line"),
    )


def _is_component_repair_branch(branch: Any) -> bool:
    return str(branch or "").lower().startswith(AUTO_HEAL_BRANCH_PREFIX)


def _exclude_component_repair_branch_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [run for run in runs if not _is_component_repair_branch(run.get("head_branch"))]


def _reject_component_repair_branch_analysis(run: dict[str, Any]) -> None:
    if _is_component_repair_branch(run.get("head_branch")):
        raise HTTPException(
            status_code=409,
            detail=AUTO_HEAL_ANALYSIS_REJECTION_MESSAGE,
        )

@router.get("/failed-runs")
async def list_failed_github_actions_runs(
    limit: int = Query(default=20, ge=1, le=50),
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
):
    try:
        github_config, github_service = await _github_service_for_scope(
            scope=scope,
            authorization=authorization,
        )
        runs = await github_service.list_failed_runs(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            limit=limit,
        )
        runs = _exclude_component_repair_branch_runs(runs)
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error

    return {
        "repository": github_config.repository_full_name,
        "runs": runs,
    }


@router.get("/runs/{run_id}")
async def get_github_actions_run_failed_jobs(
    run_id: int = Path(..., gt=0),
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
):
    try:
        github_config, github_service = await _github_service_for_scope(
            scope=scope,
            authorization=authorization,
        )
        run = await github_service.get_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        jobs = await github_service.list_jobs_for_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error

    return {
        "repository": github_config.repository_full_name,
        "run": run,
        "jobs": jobs,
        "failed_jobs": _failed_jobs(jobs),
    }


@router.get("/runs/{run_id}/evidence")
async def preview_github_actions_failure_evidence(
    run_id: int = Path(..., gt=0),
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
):
    try:
        github_config, github_service = await _github_service_for_scope(
            scope=scope,
            authorization=authorization,
        )
        run = await github_service.get_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        jobs = await github_service.list_jobs_for_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error

    evidence_jobs = []
    for job in _failed_jobs(jobs)[:MAX_FAILED_JOBS_FOR_EVIDENCE]:
        job_id = job.get("job_id")
        failed_steps = _failed_steps(job)
        preview = {
            "job_id": job_id,
            "job_name": job.get("name"),
            "failed_steps": failed_steps,
            "evidence": None,
        }
        if not isinstance(job_id, int) or job_id <= 0:
            preview["error"] = {
                "status_code": 502,
                "message": "GitHub returned a failed job without a valid job ID.",
            }
            evidence_jobs.append(preview)
            continue

        try:
            log_text = await github_service.download_job_log(
                owner=github_config.repository_owner,
                repository=github_config.repository_name,
                job_id=job_id,
            )
            preview["evidence"] = build_failure_evidence(
                log_text=log_text,
                job_name=job.get("name"),
                failed_steps=failed_steps,
                repository_name=github_config.repository_name,
            )
        except GitHubActionsApiError as error:
            preview["error"] = _job_log_error(error)
        evidence_jobs.append(preview)

    return {
        "repository": github_config.repository_full_name,
        "run": run,
        "failed_job_count": len(_failed_jobs(jobs)),
        "processed_failed_job_count": len(evidence_jobs),
        "max_failed_jobs_processed": MAX_FAILED_JOBS_FOR_EVIDENCE,
        "failed_jobs": evidence_jobs,
    }


@router.post("/runs/{run_id}/jobs/{job_id}/classify")
async def classify_github_actions_failed_job_preview(
    run_id: int = Path(..., gt=0),
    job_id: int = Path(..., gt=0),
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
):
    try:
        github_config, github_service = await _github_service_for_scope(
            scope=scope,
            authorization=authorization,
        )
        run = await github_service.get_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        jobs = await github_service.list_jobs_for_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        selected_job = _find_job_for_run(jobs, job_id)
        _ensure_selected_job_failed(selected_job)
        failed_steps = _failed_steps(selected_job)
        log_text = await github_service.download_job_log(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            job_id=job_id,
        )
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error

    evidence = build_failure_evidence(
        log_text=log_text,
        job_name=selected_job.get("name"),
        failed_steps=failed_steps,
        repository_name=github_config.repository_name,
    )
    if not _has_classifiable_evidence(evidence):
        raise HTTPException(
            status_code=422,
            detail="GitHub job log did not contain enough failure evidence to classify.",
        )

    classifier_log_text = _build_classifier_log_text(
        run=run,
        job=selected_job,
        evidence=evidence,
        failed_steps=failed_steps,
    )
    try:
        root_cause_result = root_cause_service.analyze(classifier_log_text)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="ML classification preview failed.",
        ) from error

    return {
        "repository": github_config.repository_full_name,
        "run": run,
        "job": {
            "job_id": selected_job.get("job_id"),
            "job_name": selected_job.get("name"),
            "status": selected_job.get("status"),
            "conclusion": selected_job.get("conclusion"),
            "html_url": selected_job.get("html_url"),
        },
        "failed_steps": failed_steps,
        "evidence": evidence,
        "classifier_input_summary": _classifier_input_summary(
            run=run,
            job=selected_job,
            evidence=evidence,
        ),
        "classification": _classification_preview_from_root_cause(root_cause_result),
        "saved_to_db": False,
        "healing_invoked": False,
        "repair_eligibility_evaluated": False,
        "repair_agent_invoked": False,
    }


@router.post("/runs/{run_id}/jobs/{job_id}/analyze")
async def analyze_github_actions_failed_job(
    run_id: int = Path(..., gt=0),
    job_id: int = Path(..., gt=0),
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
    db: Session = Depends(get_db),
):
    try:
        github_config, github_service = await _github_service_for_scope(
            scope=scope,
            authorization=authorization,
        )
        run = await github_service.get_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        _reject_component_repair_branch_analysis(run)
        jobs = await github_service.list_jobs_for_run(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            run_id=run_id,
        )
        selected_job = _find_job_for_run(jobs, job_id)
        _ensure_selected_job_failed(selected_job)
        failed_steps = _failed_steps(selected_job)
        log_text = await github_service.download_job_log(
            owner=github_config.repository_owner,
            repository=github_config.repository_name,
            job_id=job_id,
        )
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error

    evidence = build_failure_evidence(
        log_text=log_text,
        job_name=selected_job.get("name"),
        failed_steps=failed_steps,
        repository_name=github_config.repository_name,
    )
    if not _has_classifiable_evidence(evidence):
        raise HTTPException(
            status_code=422,
            detail="GitHub job log did not contain enough failure evidence to analyze.",
        )

    analysis_request = AnalyzeRequest(
        organization_id=scope.organization_id,
        project_id=scope.project_id,
        test_name=str(selected_job.get("name") or "GitHub Actions failed job"),
        pipeline=str(run.get("name") or run.get("display_title") or "GitHub Actions"),
        error_message=str(evidence.get("error_message") or "GitHub Actions job failed."),
        stack_trace=str(evidence.get("stack_trace") or ""),
        logs=str(evidence.get("sanitized_log_excerpt") or ""),
        failure_stage=str(evidence.get("failure_stage") or "unknown"),
        failure_type="GitHub Actions Job Failure",
        severity="MEDIUM",
        retry_count=0,
        test_duration_sec=30,
        cpu_usage_pct=50,
        memory_usage_mb=1024,
        is_flaky_test=0,
        old_locator="",
        github_actions_run_url=str(run.get("html_url") or ""),
    )
    source_run = _source_run_for_analysis(
        github_config=github_config,
        run=run,
    )
    result = await run_analysis_pipeline(
        req=analysis_request,
        db=db,
        authorization=authorization,
        source_run_override=source_run,
        project_repair_repositories_override={github_config.repository_full_name},
        repair_evidence_override=_repair_evidence_from_github_evidence(evidence),
    )

    return {
        "source": "github_actions",
        "github": {
            "repository": github_config.repository_full_name,
            "run_id": run.get("run_id"),
            "job_id": selected_job.get("job_id"),
            "run_url": run.get("html_url"),
            "head_sha": run.get("head_sha"),
            "head_branch": run.get("head_branch"),
        },
        "evidence": {
            "candidate_file": evidence.get("candidate_file"),
            "candidate_line": evidence.get("candidate_line"),
            "error_type": evidence.get("error_type"),
            "error_message": evidence.get("error_message"),
            "evidence_hash": evidence.get("evidence_hash"),
        },
        "analysis": result,
        "failure": {
            "test_id": result.get("test_id"),
            "status": result.get("status"),
        },
        "classification": result.get("pipeline", {}).get("classification"),
        "healing": result.get("pipeline", {}).get("healing"),
        "repair": result.get("pipeline", {}).get("repair"),
    }

@router.post("/resolve")
async def resolve_github_actions_run(
    request: GitHubRunRequest,
    scope: ProjectScope = Depends(get_project_scope),
    authorization: Optional[str] = Depends(get_bearer_authorization),
):
    if request.project_id != scope.project_id:
        raise HTTPException(
            status_code=400,
            detail="Request project_id must match the active project scope.",
        )
    try:
        github_config = await project_configuration_client.get_project_github_configuration(
            project_id=str(scope.project_id),
            authorization_header=authorization,
        )
        return await GitHubActionsService(
            token=github_config.token,
            allowed_repositories={github_config.repository_full_name},
        ).resolve_run(request.run_url)
    except ProjectConfigurationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except GitHubRunUrlError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise _safe_http_exception(error) from error
