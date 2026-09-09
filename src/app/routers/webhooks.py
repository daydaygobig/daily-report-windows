"""Routes for webhook management."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..errors import NotFoundError
from ..dependencies import get_db
from ..schemas.webhook import WebhookCreate, WebhookImageTestPayload, WebhookUpdate
from ..services import webhook_service
from ..utils.responses import success_response

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/", response_model=dict)
def list_webhooks(db: Session = Depends(get_db)):
    webhooks = webhook_service.list_webhooks(db)
    return success_response([webhook.model_dump() for webhook in webhooks])


@router.post("/", response_model=dict)
def create_webhook(payload: WebhookCreate, db: Session = Depends(get_db)):
    webhook = webhook_service.create_webhook(db, payload)
    return success_response(webhook.model_dump(), message="Webhook 创建成功")


@router.put("/{webhook_id}", response_model=dict)
def update_webhook(webhook_id: int, payload: WebhookUpdate, db: Session = Depends(get_db)):
    try:
        webhook = webhook_service.update_webhook(db, webhook_id, payload)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return success_response(webhook.model_dump(), message="Webhook 更新成功")


@router.post("/{webhook_id}/test-image", response_model=dict)
async def test_webhook_image(webhook_id: int, payload: WebhookImageTestPayload, db: Session = Depends(get_db)):
    try:
        result = await webhook_service.test_webhook_image(db, webhook_id, payload)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return success_response(result.model_dump(), message=result.message)


@router.delete("/{webhook_id}", response_model=dict)
def delete_webhook(webhook_id: int, db: Session = Depends(get_db)):
    try:
        webhook_service.delete_webhook(db, webhook_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return success_response(message="Webhook 已删除")
