"""Routers package."""

from fastapi import APIRouter

from . import (
    alerts,
    chat_records,
    disk_monitor,
    executions,
    github_configs,
    github_deployments,
    ima,
    models,
    prompt_templates,
    system,
    tasks,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(models.router)
api_router.include_router(webhooks.router)
api_router.include_router(tasks.router)
api_router.include_router(executions.router)
api_router.include_router(alerts.router)
api_router.include_router(chat_records.router)
api_router.include_router(disk_monitor.router)
api_router.include_router(prompt_templates.router)
api_router.include_router(github_configs.router)
api_router.include_router(github_deployments.router)
api_router.include_router(ima.router)
