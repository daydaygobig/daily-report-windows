"""执行异常的归一化描述与 AI 输出校验异常（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import re
from typing import Optional

import httpx

from ..integrations import github


def _format_exception_message(label: str, exc: BaseException, *, attempts: Optional[int] = None) -> str:
    detail = _exception_detail(exc)
    if detail.startswith(f"{label}失败："):
        return detail
    if label == "执行":
        return detail
    attempt_text = f"，已尝试 {attempts} 次" if attempts and attempts > 1 else ""
    return f"{label}失败：{detail}{attempt_text}"


def _exception_detail(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "请求超时，可能是网络问题"
    if isinstance(exc, httpx.ConnectError):
        return "连接失败，可能是网络问题"
    if isinstance(exc, github.GithubAPIError):
        return _format_github_api_error(str(exc).strip())

    detail = str(exc).strip()
    if detail:
        return detail
    return f"异常类型 {type(exc).__name__}"


def _format_github_api_error(detail: str) -> str:
    status_match = re.match(r"^(\d{3})\b", detail)
    status_code = int(status_match.group(1)) if status_match else None
    if status_code in {401, 403}:
        return "GitHub 认证或权限失败，请检查 Token 是否有效且有仓库写入权限"
    if status_code == 404:
        return "GitHub 仓库、分支或文件路径不存在，请检查 owner/repo/branch 配置"
    if status_code in {429, 500, 502, 503, 504}:
        return f"GitHub 服务暂时不可用或限流（HTTP {status_code}），请稍后重试"
    if status_code:
        return f"GitHub 返回错误（HTTP {status_code}）：{detail}"
    return detail or "GitHub 返回了未知错误"


class AIOutputValidationError(RuntimeError):
    """Model returned text, but the business validator rejected it."""

    def __init__(self, message: str, *, raw_summary: str) -> None:
        super().__init__(message)
        self.raw_summary = raw_summary
