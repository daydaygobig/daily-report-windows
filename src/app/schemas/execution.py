"""Pydantic schemas for execution records."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import ORMBase


class ExecutionOut(ORMBase):
    task_id: Optional[int]
    job_id: Optional[int]
    task_name: Optional[str] = None
    job_name: Optional[str] = None
    job_execution_time: Optional[str] = None
    job_created_at: Optional[datetime] = None
    status: str
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    prompt_chars: Optional[int]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    llm_model_name: Optional[str]
    summary_md: Optional[str]
    summary_path: Optional[str]
    chatlog_path: Optional[str]
    html_backup_path: Optional[str]
    error_msg: Optional[str]
    is_manual: bool
    prompt_context: Optional[Dict[str, Any]] = None
    prompt_usage: Optional[Any] = None
    deploy_status: Optional[str] = None
    deploy_url: Optional[str] = None
    deploy_error: Optional[str] = None
    github_config_id: Optional[int] = None
    github_config_name: Optional[str] = None
    deploy_record_id: Optional[int] = None
    deploy_repo_path: Optional[str] = None
    deploy_repo_full_name: Optional[str] = None
    deploy_branch: Optional[str] = None
    deploy_github_file_url: Optional[str] = None
    github_deployments: Optional[List[Dict[str, Any]]] = None
    ima_sync_status: Optional[str] = None
    ima_sync_error: Optional[str] = None
    ima_sync_batch_id: Optional[str] = None
    exported_files: Optional[List[Dict[str, Any]]] = None
    disk_io: Optional[Dict[str, Any]] = None
    topic_card_meta: Optional[Dict[str, Any]] = None
    image_card_meta: Optional[Dict[str, Any]] = None
