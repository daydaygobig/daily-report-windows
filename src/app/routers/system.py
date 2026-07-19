"""System status router."""

from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..services.system_service import get_system_status
from ..utils.responses import success_response

router = APIRouter()

LOG_FILES: Dict[str, Path] = {
    "backend": Path("logs/backend.log"),
}


@router.get("/status")
async def system_status():
    status = await get_system_status()
    return success_response(status)


@router.get("/logs")
async def download_logs(name: str = Query("backend")):
    log_path = LOG_FILES.get(name)
    if not log_path:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "未找到指定日志"})
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"code": 404, "message": "日志文件不存在"})
    return FileResponse(log_path, filename=log_path.name, media_type="text/plain")
