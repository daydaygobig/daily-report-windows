"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from .config import get_settings
from .db import Base, engine
from .db_migrations import ensure_schema
from .errors import AppError
from .routers import api_router
from .scheduler.service import scheduler_service


def _mark_interrupted_executions() -> None:
    """进程重启后，把遗留的 running 执行标记为失败（上次进程中断，未完成推送）。"""
    from sqlalchemy import text

    from .db import SessionLocal

    db = SessionLocal()
    try:
        result = db.execute(
            text("UPDATE executions SET status = 'failed', error_msg = :msg WHERE status = 'running'"),
            {"msg": "进程重启导致执行中断，未完成生成或推送"},
        )
        db.commit()
        if result.rowcount:
            logger.warning("已把 {} 条中断的 running 执行标记为失败", result.rowcount)
    finally:
        db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)

    app.include_router(api_router, prefix="/api")

    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError):
        """领域异常 → 与历史 HTTPException(detail={code, message}) 完全相同的响应体。"""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": str(exc)}},
        )

    @app.get("/healthz")
    def healthcheck():
        return {"status": "ok"}

    @app.on_event("startup")
    async def startup_event() -> None:
        _mark_interrupted_executions()
        scheduler_service.start()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        scheduler_service.shutdown()

    return app


app = create_app()
