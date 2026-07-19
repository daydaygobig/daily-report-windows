"""Routes for GitHub configuration management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..integrations.github import GithubAPIError
from ..schemas.github_config import (
    GithubConfigCreate,
    GithubConfigUpdate,
    GithubTokenTestRequest,
)
from ..services import github_config_service
from ..utils.responses import success_response

router = APIRouter(prefix="/github-configs", tags=["github"])


@router.get("/", response_model=dict)
def list_configs(db: Session = Depends(get_db)):
    items = github_config_service.list_configs(db)
    return success_response([item.model_dump() for item in items])


@router.post("/", response_model=dict)
def create_config(payload: GithubConfigCreate, db: Session = Depends(get_db)):
    try:
        config = github_config_service.create_config(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(config.model_dump(), message="配置已创建")


@router.put("/{config_id}", response_model=dict)
def update_config(config_id: int, payload: GithubConfigUpdate, db: Session = Depends(get_db)):
    try:
        config = github_config_service.update_config(db, config_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(config.model_dump(), message="配置已更新")


@router.delete("/{config_id}", response_model=dict)
def delete_config(config_id: int, db: Session = Depends(get_db)):
    try:
        github_config_service.delete_config(db, config_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(message="配置已删除")


@router.post("/test", response_model=dict)
async def test_token(payload: GithubTokenTestRequest, db: Session = Depends(get_db)):
    try:
        result = await github_config_service.test_token(db, payload)
    except GithubAPIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(result.model_dump(), message="Token 测试成功")
