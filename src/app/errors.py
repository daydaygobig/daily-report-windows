"""领域异常：服务层用它们表达业务错误，全局异常处理器统一转 HTTP 响应。

AppError 继承 ValueError，保证既有 `except ValueError` 调用方（含测试）行为不变。
"""

from __future__ import annotations

from typing import Optional


class AppError(ValueError):
    """业务校验错误，默认映射 HTTP 400（detail.code=1，与历史响应体一致）。"""

    status_code = 400
    code = 1

    def __init__(self, message: str, *, code: Optional[int] = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    """资源不存在，映射 HTTP 404（detail.code=404，与历史响应体一致）。"""

    status_code = 404
    code = 404
