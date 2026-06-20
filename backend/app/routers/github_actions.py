from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubRunUrlError,
    github_actions_service,
)


router = APIRouter(
    prefix="/api/github/actions",
    tags=["GitHub Actions"],
)


class GitHubRunRequest(BaseModel):
    run_url: str = Field(min_length=1, max_length=500)


@router.post("/resolve")
async def resolve_github_actions_run(request: GitHubRunRequest):
    try:
        return await github_actions_service.resolve_run(request.run_url)
    except GitHubRunUrlError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except GitHubActionsApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
