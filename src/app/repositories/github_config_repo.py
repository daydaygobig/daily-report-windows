"""Repository helpers for GitHub configurations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..integrations.security import encrypt_value
from ..models.github_config import GithubConfig
from .base import CRUDRepository


class GithubConfigRepository(CRUDRepository[GithubConfig]):
    def __init__(self) -> None:
        super().__init__(GithubConfig)

    def list_all(self, db: Session):
        return (
            db.query(GithubConfig)
            .order_by(GithubConfig.is_default.desc(), GithubConfig.created_at.desc())
            .all()
        )

    def create_with_secret(self, db: Session, *, obj_in: dict) -> GithubConfig:
        payload = self._prepare_payload(obj_in)
        return super().create(db, obj_in=payload)

    def update_with_secret(self, db: Session, *, entity: GithubConfig, obj_in: dict) -> GithubConfig:
        payload = self._prepare_payload(obj_in, allow_missing=True)
        return super().update(db, entity=entity, obj_in=payload)

    def clear_other_defaults(self, db: Session, *, keep_id: int) -> None:
        db.execute(
            update(GithubConfig)
            .where(GithubConfig.id != keep_id)
            .where(GithubConfig.is_default.is_(True))
            .values(is_default=False)
        )

    @staticmethod
    def _prepare_payload(obj_in: dict, allow_missing: bool = False) -> dict:
        payload = obj_in.copy()
        if "token" in payload:
            token = payload.pop("token")
            if token is None and allow_missing:
                payload.pop("token", None)
            else:
                payload["token_cipher"] = encrypt_value(token or "")
        elif not allow_missing:
            raise ValueError("缺少 GitHub Token")

        if "path_prefix" in payload:
            payload["path_prefix"] = _normalize_prefix(payload["path_prefix"])
        if "filename_template" in payload and payload["filename_template"]:
            payload["filename_template"] = _normalize_template(payload["filename_template"])
        elif "filename_template" in payload:
            payload["filename_template"] = "新茧群日报_{YYYY-MM-DD}.html"
        if "view_url_mode" in payload:
            payload["view_url_mode"] = payload["view_url_mode"] or "github_pages"
        if "view_url_template" in payload and payload["view_url_template"]:
            payload["view_url_template"] = payload["view_url_template"].strip()
        elif "view_url_template" in payload:
            payload["view_url_template"] = None

        owner = payload.get("owner")
        repo = payload.get("repo")
        pages_base_url = payload.get("pages_base_url")
        if owner and repo and not pages_base_url:
            payload["pages_base_url"] = _ensure_trailing_slash(f"https://{owner}.github.io/{repo}/")
        elif pages_base_url:
            payload["pages_base_url"] = _ensure_trailing_slash(pages_base_url)
        return payload


def _normalize_prefix(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.replace("\\", "/").strip()
    cleaned = cleaned.strip("/")
    return cleaned or None


def _normalize_template(value: str) -> str:
    template = value.strip() or "新茧群日报_{YYYY-MM-DD}.html"
    return template


def _ensure_trailing_slash(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    if not text.endswith("/"):
        text += "/"
    return text
