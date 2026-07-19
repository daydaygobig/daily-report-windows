"""Business logic for webhook management."""

from typing import List

from sqlalchemy.orm import Session

from ..integrations import feishu
from ..integrations.security import decrypt_value
from ..repositories.webhook_repo import WebhookRepository
from ..schemas.webhook import WebhookCreate, WebhookImageTestPayload, WebhookImageTestResult, WebhookOut, WebhookUpdate

webhook_repo = WebhookRepository()


def _webhook_to_dict(webhook) -> dict:
    return {
        "id": webhook.id,
        "name": webhook.name,
        "headers": None,
        "card_mode": getattr(webhook, "card_mode", "markdown"),
        "card_header_enabled": bool(getattr(webhook, "card_header_enabled", False)),
        "card_header_title": getattr(webhook, "card_header_title", None),
        "card_header_subtitle": getattr(webhook, "card_header_subtitle", None),
        "card_header_color": getattr(webhook, "card_header_color", None),
        "image_render_engine": getattr(webhook, "image_render_engine", "satori") or "satori",
        "feishu_app_id": getattr(webhook, "feishu_app_id", None),
        "has_feishu_app_secret": bool(getattr(webhook, "feishu_app_secret_cipher", None)),
        "created_at": webhook.created_at,
        "updated_at": webhook.updated_at,
    }


def list_webhooks(db: Session) -> List[WebhookOut]:
    webhooks = webhook_repo.list(db)
    return [WebhookOut.model_validate(_webhook_to_dict(webhook)) for webhook in webhooks]


def create_webhook(db: Session, payload: WebhookCreate) -> WebhookOut:
    webhook = webhook_repo.create_with_secret(db, obj_in=payload.model_dump())
    return WebhookOut.model_validate(_webhook_to_dict(webhook))


def update_webhook(db: Session, webhook_id: int, payload: WebhookUpdate) -> WebhookOut:
    entity = webhook_repo.get(db, webhook_id)
    if not entity:
        raise ValueError("Webhook 不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    webhook = webhook_repo.update_with_secret(db, entity=entity, obj_in=obj_in)
    return WebhookOut.model_validate(_webhook_to_dict(webhook))


def delete_webhook(db: Session, webhook_id: int) -> None:
    entity = webhook_repo.get(db, webhook_id)
    if not entity:
        raise ValueError("Webhook 不存在")
    webhook_repo.delete(db, entity=entity)


async def test_webhook_image(db: Session, webhook_id: int, payload: WebhookImageTestPayload) -> WebhookImageTestResult:
    entity = webhook_repo.get(db, webhook_id)
    if not entity:
        raise ValueError("Webhook 不存在")
    app_id = (payload.app_id or getattr(entity, "feishu_app_id", None) or "").strip()
    app_secret = (payload.app_secret or "").strip()
    if not app_secret and getattr(entity, "feishu_app_secret_cipher", None):
        app_secret = decrypt_value(entity.feishu_app_secret_cipher)
    if not app_id or not app_secret:
        return WebhookImageTestResult(ok=False, message="请先填写飞书应用 App ID 和 App Secret")

    try:
        image_key = await feishu.upload_image(
            app_id=app_id,
            app_secret=app_secret,
            image_bytes=feishu.build_test_png(),
            filename="topic-card-test.png",
        )
        if payload.send_image:
            await feishu.send_image(entity, image_key=image_key)
        return WebhookImageTestResult(ok=True, message="图片上传测试通过" if not payload.send_image else "图片上传并推送成功", image_key=image_key)
    except Exception as exc:
        return WebhookImageTestResult(ok=False, message=str(exc))
