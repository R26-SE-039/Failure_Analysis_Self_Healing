from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel

from app.services.root_cause_service import (
    root_cause_service,
)


router = APIRouter(
    prefix="/api/root-cause",
    tags=["Root Cause Analysis"],
)


class LogAnalysisRequest(BaseModel):
    log_text: str


@router.get("/health")
def root_cause_health():
    return {
        "status": "running",
        "model_loaded": True,
        "supported_classes": [
            str(label)
            for label in root_cause_service.classes
        ],
    }


@router.post("/analyze")
async def analyze_failure_log(
    file: UploadFile = File(...),
):
    try:
        file_content = await file.read()

        log_text = file_content.decode(
            "utf-8",
            errors="ignore",
        )

        result = root_cause_service.analyze(
            log_text
        )

        return {
            "file_name": file.filename,
            **result,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Root-cause analysis failed: "
                f"{error}"
            ),
        ) from error


@router.post("/analyze-text")
def analyze_failure_text(
    request: LogAnalysisRequest,
):
    try:
        return root_cause_service.analyze(
            request.log_text
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Root-cause analysis failed: "
                f"{error}"
            ),
        ) from error
