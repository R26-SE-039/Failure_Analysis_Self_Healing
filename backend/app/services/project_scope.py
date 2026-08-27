from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Query
from sqlalchemy.orm import Query as SqlAlchemyQuery


@dataclass(frozen=True)
class ProjectScope:
    organization_id: Optional[UUID] = None
    project_id: Optional[UUID] = None

    @property
    def is_scoped(self) -> bool:
        return self.organization_id is not None and self.project_id is not None


def get_project_scope(
    organization_id: UUID = Query(...),
    project_id: UUID = Query(...),
) -> ProjectScope:
    return ProjectScope(
        organization_id=organization_id,
        project_id=project_id,
    )


def apply_failure_scope(query: SqlAlchemyQuery, model, scope: ProjectScope):
    if not isinstance(scope, ProjectScope):
        return query
    return query.filter(
        model.organization_id == scope.organization_id,
        model.project_id == scope.project_id,
    )


def apply_child_failure_scope(
    query: SqlAlchemyQuery,
    child_model,
    failure_model,
    scope: ProjectScope,
):
    if not isinstance(scope, ProjectScope):
        return query
    return (
        query.join(failure_model, child_model.failure_id == failure_model.id)
        .filter(
            failure_model.organization_id == scope.organization_id,
            failure_model.project_id == scope.project_id,
        )
    )


def apply_repair_attempt_scope(
    query: SqlAlchemyQuery,
    repair_attempt_model,
    failure_model,
    scope: ProjectScope,
):
    if not isinstance(scope, ProjectScope):
        return query
    return (
        query.join(
            failure_model,
            repair_attempt_model.failure_id == failure_model.id,
        )
        .filter(
            failure_model.organization_id == scope.organization_id,
            failure_model.project_id == scope.project_id,
        )
    )


def ensure_failure_in_scope(db, failure_model, failure_id: Optional[int], scope: ProjectScope) -> None:
    if not isinstance(scope, ProjectScope):
        return
    if failure_id is None:
        raise HTTPException(status_code=404, detail="Resource not found.")
    exists = (
        db.query(failure_model)
        .filter(
            failure_model.id == failure_id,
            failure_model.organization_id == scope.organization_id,
            failure_model.project_id == scope.project_id,
        )
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Resource not found.")
