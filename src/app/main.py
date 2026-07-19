"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .db_migrations import ensure_schema
from .routers import api_router
from .scheduler.service import scheduler_service


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

    @app.get("/healthz")
    def healthcheck():
        return {"status": "ok"}

    @app.on_event("startup")
    async def startup_event() -> None:
        scheduler_service.start()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        scheduler_service.shutdown()

    return app


app = create_app()
