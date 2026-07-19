"""Pydantic schemas for GitHub deployment configuration."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .base import ORMBase


_DEFAULT_TEMPLATE = "新茧群日报_{YYYY-MM-DD}.html"


class GithubConfigBase(BaseModel):
    name: str = Field(..., max_length=120)
    owner: str = Field(..., max_length=120)
    repo: str = Field(..., max_length=120)
    branch: str = Field(default="main", max_length=80)
    path_prefix: Optional[str] = Field(default=None, max_length=255)
    filename_template: str = Field(default=_DEFAULT_TEMPLATE, max_length=255)
    pages_base_url: Optional[str] = Field(default=None, max_length=255)
    view_url_mode: Literal["github_pages", "custom_template"] = "github_pages"
    view_url_template: Optional[str] = Field(default=None, max_length=500)
    is_default: bool = False
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_template(cls, values: "GithubConfigBase"):
        template = values.filename_template or _DEFAULT_TEMPLATE
        if "{YYYY" not in template:
            raise ValueError("文件名模板需包含日期占位符，例如 {YYYY-MM-DD}")
        if values.view_url_mode == "custom_template" and not (values.view_url_template or "").strip():
            raise ValueError("自定义查看页面链接需填写链接模板")
        return values


class GithubConfigCreate(GithubConfigBase):
    token: str = Field(..., min_length=1, max_length=200)


class GithubConfigUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    owner: Optional[str] = Field(default=None, max_length=120)
    repo: Optional[str] = Field(default=None, max_length=120)
    branch: Optional[str] = Field(default=None, max_length=80)
    path_prefix: Optional[str] = Field(default=None, max_length=255)
    filename_template: Optional[str] = Field(default=None, max_length=255)
    pages_base_url: Optional[str] = Field(default=None, max_length=255)
    view_url_mode: Optional[Literal["github_pages", "custom_template"]] = None
    view_url_template: Optional[str] = Field(default=None, max_length=500)
    is_default: Optional[bool] = None
    description: Optional[str] = None
    token: Optional[str] = Field(default=None, min_length=1, max_length=200)


class GithubConfigOut(ORMBase):
    name: str
    owner: str
    repo: str
    branch: str
    path_prefix: Optional[str]
    filename_template: str
    pages_base_url: Optional[str]
    view_url_mode: str
    view_url_template: Optional[str]
    is_default: bool
    description: Optional[str]
    has_token: bool
    token: Optional[str] = None


class GithubRepoInfo(BaseModel):
    owner: str
    repo: str
    full_name: str
    default_branch: str
    private: bool
    pages_base_url: HttpUrl


class GithubTokenTestRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=200)
    owner: Optional[str] = Field(default=None, max_length=120)
    per_page: int = Field(default=50, ge=1, le=100)


class GithubTokenTestResponse(BaseModel):
    login: str
    repos: List[GithubRepoInfo]
