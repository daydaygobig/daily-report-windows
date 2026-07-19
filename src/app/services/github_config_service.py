"""Business logic for GitHub configuration management."""

from typing import List

from sqlalchemy.orm import Session

from ..integrations.security import decrypt_value
from ..integrations import github
from ..models.github_config import GithubConfig
from ..models.job import Job
from ..repositories.github_config_repo import GithubConfigRepository
from ..schemas.github_config import (
    GithubConfigCreate,
    GithubConfigOut,
    GithubConfigUpdate,
    GithubTokenTestRequest,
    GithubTokenTestResponse,
)

repo = GithubConfigRepository()


def _to_schema(entity: GithubConfig) -> GithubConfigOut:
    return GithubConfigOut.model_validate(
        {
            "id": entity.id,
            "name": entity.name,
            "owner": entity.owner,
            "repo": entity.repo,
            "branch": entity.branch,
            "path_prefix": entity.path_prefix,
            "filename_template": entity.filename_template,
            "pages_base_url": entity.pages_base_url,
            "view_url_mode": entity.view_url_mode or "github_pages",
            "view_url_template": entity.view_url_template,
            "is_default": bool(entity.is_default),
            "description": entity.description,
            "has_token": bool(entity.token_cipher),
            "token": decrypt_value(entity.token_cipher) if entity.token_cipher else None,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
    )


def list_configs(db: Session) -> List[GithubConfigOut]:
    items = repo.list_all(db)
    return [_to_schema(item) for item in items]


def create_config(db: Session, payload: GithubConfigCreate) -> GithubConfigOut:
    entity = repo.create_with_secret(db, obj_in=payload.model_dump())
    db.flush()
    if payload.is_default:
        repo.clear_other_defaults(db, keep_id=entity.id)
    return _to_schema(entity)


def update_config(db: Session, config_id: int, payload: GithubConfigUpdate) -> GithubConfigOut:
    entity = repo.get(db, config_id)
    if not entity:
        raise ValueError("GitHub 配置不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = repo.update_with_secret(db, entity=entity, obj_in=obj_in)
    if obj_in.get("is_default"):
        repo.clear_other_defaults(db, keep_id=updated.id)
    return _to_schema(updated)


def delete_config(db: Session, config_id: int) -> None:
    entity = repo.get(db, config_id)
    if not entity:
        raise ValueError("GitHub 配置不存在")
    in_use = db.query(Job.id).filter(Job.github_config_id == config_id).first()
    if in_use:
        raise ValueError("仍有作业引用该配置，无法删除")
    repo.delete(db, entity=entity)


async def test_token(db: Session, payload: GithubTokenTestRequest) -> GithubTokenTestResponse:
    result = await github.list_accessible_repos(payload.token, owner_hint=payload.owner, per_page=payload.per_page)
    return GithubTokenTestResponse.model_validate(result)
