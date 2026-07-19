"""Routes for prompt templates."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplateUpdate,
)
from ..services import prompt_template_service
from ..utils.responses import success_response

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


@router.get("/", response_model=dict)
def list_templates(db: Session = Depends(get_db)):
    templates = prompt_template_service.list_templates(db)
    data = [PromptTemplateOut.model_validate(template).model_dump() for template in templates]
    return success_response(data)


@router.post("/", response_model=dict)
def create_template(payload: PromptTemplateCreate, db: Session = Depends(get_db)):
    try:
        template = prompt_template_service.create_template(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": str(exc)},
        ) from exc
    return success_response(PromptTemplateOut.model_validate(template).model_dump(), message="提示词创建成功")


@router.put("/{template_id}", response_model=dict)
def update_template(template_id: int, payload: PromptTemplateUpdate, db: Session = Depends(get_db)):
    try:
        template = prompt_template_service.update_template(db, template_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "不存在" in str(exc) else status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": str(exc)},
        ) from exc
    return success_response(PromptTemplateOut.model_validate(template).model_dump(), message="提示词已更新")


@router.delete("/{template_id}", response_model=dict)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    try:
        prompt_template_service.delete_template(db, template_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": str(exc)},
        ) from exc
    return success_response(message="提示词已删除")
