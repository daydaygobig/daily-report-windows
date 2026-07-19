"""Common response helpers."""

from typing import Any, Optional

from fastapi import HTTPException, status


def success_response(data: Any = None, message: str = "ok", code: int = 0) -> dict:
    return {"code": code, "message": message, "data": data}


def error_response(message: str, *, code: int = 1, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})
