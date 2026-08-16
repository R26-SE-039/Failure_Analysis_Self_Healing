from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubActionsService,
    GitHubRunUrlError,
)
from app.services.project_configuration_client import (
    ProjectConfigurationError,
    project_configuration_client,
)


router = APIRouter(
    prefix="/api/github/actions",
    tags=["GitHub Actions"],
)


class GitHubRunRequest(BaseModel):
    project_id: UUID
    run_url: str = Field(min_length=1, max_length=500)


@router.post("/resolve")
async def resolve_github_actions_run(
    request: GitHubRunRequest,
    authorization: str | None = Header(default=None),
):
    try:
        github_config = await project_configuration_client.get_project_github_configuration(
            project_id=str(request.project_id),
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
        raise HTTPException(status_code=502, detail=str(error)) from error
