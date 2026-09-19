"""APScheduler 集成入口：SchedulerService 组合根与作业执行编排。

原 3495 行上帝文件已按职责拆分为同目录下各 mixin 模块（scheduling/windows/prompts/
upstream/delivery/alerts/backups/deploy/parsing/types/errors/common），本文件只保留
调度器状态、`_run_job` 执行编排与向后兼容的再导出。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from zoneinfo import ZoneInfo

from ..db import session_scope
from ..models.disk_monitor import DiskIoRecord
from ..models.execution import Execution
from ..models.github_deployment import GithubDeployment
from ..models.job import Job
from ..models.task import Task
from ..services import alert_service, disk_monitor_service
from ..services.github_view_url import build_view_url
from ..utils import message_stats as message_stats_utils
from ..utils.prompt_metrics import compute_prompt_usage, count_tokens

from .alerts import AlertFlowMixin
from .backups import BackupMixin
from .common import (
    EMPTY_CHATLOG_ERROR_MESSAGE,
    UPSTREAM_MAX_AGE_HOURS,
    UPSTREAM_MAX_TOPICS,
    job_repo,
    settings,
    webhook_repo,
)
from .deploy import DeployMixin
from .delivery import DeliveryMixin
from .errors import AIOutputValidationError, _format_exception_message
from .parsing import _parse_int_list, _parse_str_list
from .prompts import PromptFlowMixin
from .scheduling import SchedulingMixin
from .types import AiSummaryResult, GithubUploadArtifact, HtmlArtifactPlan, IntervalPlan, ModelSequenceItem
from .upstream import (
    UpstreamMixin,
    _extract_report_topic_sections,
    _extract_report_topic_titles,
    _resolve_card_input_source,
)
from .windows import WindowMixin


class SchedulerService(
    SchedulingMixin,
    WindowMixin,
    PromptFlowMixin,
    UpstreamMixin,
    DeliveryMixin,
    AlertFlowMixin,
    BackupMixin,
    DeployMixin,
):
    """Wrapper around APScheduler with domain-specific execution."""

    def __init__(self) -> None:
        job_defaults = {
            "coalesce": False,
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone, job_defaults=job_defaults)
        self._started = False
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tz = ZoneInfo(settings.timezone)
        self._backup_dir = Path(settings.local_backup_dir).expanduser().resolve()
        self._auto_reload_job_id = "scheduler-auto-reload"
        self._ima_auto_sync_job_id = "ima-auto-sync"
        self._ima_sync_job_prefix = "ima-sync-job-"
        self._disk_inspection_job_prefix = "disk-inspection-job-"

    async def run_job_immediately(
        self, job_id: int, selected_topic: Optional[str] = None
    ) -> Optional[int]:
        """Trigger a job execution and wait for completion."""
        return await self._run_job(job_id, is_manual=True, selected_topic=selected_topic)

    async def _run_job(
        self,
        job_id: int,
        is_manual: bool = False,
        window_override: Optional[dict] = None,
        selected_topic: Optional[str] = None,
    ) -> Optional[int]:
        logger.info("Running job {}", job_id)
        execution_id: Optional[int] = None
        with session_scope() as db:
            job = job_repo.get_by_id(db, job_id)
            if not job or not job.is_enabled:
                logger.warning("Job {} not found or disabled", job_id)
                return None
            if not self._is_within_active_range(job):
                logger.info("Job {} is outside active range, skipping execution", job_id)
                return None
            task = job.task
            if not task or not task.is_active:
                logger.warning("Task for job {} is inactive", job_id)
                return None
            talkers = _parse_str_list(task.talkers)
            stored_names = _parse_str_list(getattr(task, "talker_names", None))
            if not talkers:
                logger.error("Task {} has no talkers configured", task.id)
                alert_service.create_alert(
                    db,
                    task_id=task.id,
                    job_id=job.id,
                    category="configuration",
                    message="任务未配置群聊",
                )
                await self._notify_alert_webhooks(
                    db,
                    task,
                    job,
                    "任务未配置群聊（请在任务设置中选择至少一个群聊）",
                )
                return
            talker_names = stored_names if stored_names and len(stored_names) == len(talkers) else talkers

            exported_files: List[dict[str, Any]] = []
            execution = Execution(
                task_id=task.id,
                job_id=job.id,
                status="running",
                scheduled_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                is_manual=is_manual,
            )
            db.add(execution)
            db.flush()
            execution_id = execution.id
            db.commit()
            db.refresh(execution)
            db.refresh(job)

            max_retry = max(int(job.max_retry or 0), 0)
            attempts = max_retry + 1
            retry_interval = max(int(job.retry_interval_sec or 0), 1)
            attempt = 0
            chatlog_path: Optional[str] = None
            deployment_record: Optional[GithubDeployment] = None
            stats_exported = False
            try:
                disk_io_context = disk_monitor_service.start_execution_io(db, execution=execution, task=task, job=job)
            except Exception:
                logger.exception("磁盘 IO 开始采样失败 execution_id={}", execution.id)
                disk_io_context = None
            chat_record_telemetry: dict[str, Any] = {}
            try:
                while attempt < attempts:
                    attempt += 1
                    allow_outer_retry = True
                    chatlog_path = None
                    time_window = None
                    summary_snapshot: Optional[str] = None
                    message_stats_result: Optional[message_stats_utils.MessageStats] = None
                    execution.error_msg = None
                    try:
                        time_window = self._calculate_time_window(job, window_override=window_override, is_manual=is_manual)
                        card_input_source = _resolve_card_input_source(task)
                        report_content_meta: Optional[Dict[str, Any]] = None
                        if card_input_source == "report":
                            # 纯日报内容模式：不拉聊天记录，直接用上游日报话题全文作为模型输入
                            chatlog_text, report_content_meta = self._load_upstream_report_content(db, task)
                        else:
                            chatlog_text = await self._collect_chatlog(talkers, time_window, telemetry=chat_record_telemetry)
                            if not chatlog_text.strip():
                                raise RuntimeError(EMPTY_CHATLOG_ERROR_MESSAGE)

                            chatlog_artifacts = self._store_chatlog_backup(task, job, execution, chatlog_text, time_window)
                            if chatlog_artifacts:
                                primary = chatlog_artifacts[0].get("path")
                                if primary:
                                    execution.chatlog_path = primary
                                exported_files.extend(chatlog_artifacts)
                        stats_needed = (
                            card_input_source != "report" and self._should_compute_message_stats(task, job)
                        )
                        message_stats_result = (
                            message_stats_utils.compute_message_stats(chatlog_text) if stats_needed else None
                        )
                        if not stats_exported:
                            message_stats_artifacts = self._export_message_stats_files(
                                task,
                                job,
                                execution,
                                time_window,
                                message_stats_result,
                            )
                            if message_stats_artifacts:
                                exported_files.extend(message_stats_artifacts)
                                stats_exported = True
                        prompt_meta: Dict[str, Any] = {
                            "task_name": task.name,
                            "chatlog_range": time_window["time_str"],
                            "chatlog_label": f"{', '.join(talker_names)} 路 {time_window['time_str']}",
                            "talkers": talker_names,
                            "task_prompt": task.prompt,
                        }
                        if message_stats_result:
                            prompt_meta["message_count"] = message_stats_result.total_messages
                        if getattr(task, "task_type", "report") == "export":
                            await self._sync_stats_and_collect(
                                db,
                                task=task,
                                job=job,
                                execution=execution,
                                time_window=time_window,
                                message_stats_result=message_stats_result,
                                exported_files=exported_files,
                            )
                            execution.raw_request = json.dumps(
                                {
                                    **prompt_meta,
                                    "task_type": "export",
                                    "llm_skipped": True,
                                },
                                ensure_ascii=False,
                            )
                            execution.status = "success"
                            execution.summary_md = "数据导出完成，未调用 LLM。"
                            execution.summary_path = None
                            execution.prompt_usage = json.dumps(
                                {"chars": {"total": 0}, "tokens": {"total": 0}},
                                ensure_ascii=False,
                            )
                            execution.prompt_chars = 0
                            execution.prompt_tokens = 0
                            execution.completion_tokens = 0
                            execution.llm_model_name = None
                            self._clear_deploy_fields(execution)
                            self._log_retry_success(job, attempt)
                            break
                        # 阶段性提交：释放 SQLite 写事务，避免长事务阻塞其他作业与页面写入。
                        db.commit()
                        system_instruction_for_usage: Optional[str] = None
                        system_instruction_text = self._build_system_instruction(
                            task,
                            job,
                            talker_names,
                            time_window,
                            message_stats_result,
                        )
                        system_instruction_for_usage = system_instruction_text
                        html_required = self._job_requires_html_output(job)
                        allow_outer_retry = False
                        if card_input_source == "report":
                            # 纯日报内容模式：话题全文已是模型输入本身，无需再注入标题清单
                            upstream_suffix = ""
                            if report_content_meta:
                                prompt_meta["upstream_report"] = report_content_meta
                                logger.info(
                                    "Job {} 纯日报内容模式：已载入 {} 个话题（来源执行 {}）",
                                    job.id,
                                    report_content_meta.get("topic_count"),
                                    report_content_meta.get("upstream_execution_id"),
                                )
                        else:
                            upstream_suffix, upstream_meta = self._build_upstream_topic_injection(db, task)
                            if upstream_meta:
                                prompt_meta["upstream_report"] = upstream_meta
                                if upstream_meta.get("injected"):
                                    logger.info(
                                        "Job {} 上游日报注入：已注入 {} 个话题（来源执行 {}）",
                                        job.id,
                                        upstream_meta["topic_count"],
                                        upstream_meta.get("upstream_execution_id"),
                                    )
                                else:
                                    logger.warning(
                                        "Job {} 上游日报注入：未注入（{}）",
                                        job.id,
                                        upstream_meta.get("reason"),
                                    )
                        # 单话题运行：在文案提示词末尾注入选题指令，模型只写所选话题的一张卡
                        # （省去先输出全部话题再过滤的 token；下游 _select_*_by_topic 仍作兜底过滤）
                        topic_instruction = (
                            "\n\n## 本次运行要求（最高优先级）\n"
                            f"本次为单话题运行：只处理话题「{selected_topic}」，"
                            "只输出该话题对应的一张卡片内容（单个内容块），"
                            "禁止输出其他任何话题的内容块或文字。\n"
                        ) if selected_topic else ""
                        ai_result = await self._generate_summary_with_model_sequence(
                            db=db,
                            task=task,
                            job=job,
                            talker_names=talker_names,
                            time_window=time_window,
                            chatlog_text=chatlog_text,
                            system_instruction_text=system_instruction_text,
                            message_stats_result=message_stats_result,
                            html_required=html_required,
                            max_ai_requests=attempts,
                            extra_prompt=(upstream_suffix or "") + topic_instruction,
                        )
                        summary = ai_result.summary
                        prompt_tokens = ai_result.prompt_tokens
                        completion_tokens = ai_result.completion_tokens
                        prompt_meta.update(ai_result.prompt_meta)
                        usage_stats = compute_prompt_usage(task.prompt, system_instruction_for_usage or "", chatlog_text)
                        execution.raw_request = json.dumps(prompt_meta, ensure_ascii=False)
                        # 卡片任务（topic_card/image_card）的生图与推送耗时很长，此时保持 running，
                        # 待 _handle_*_result 完成后再置 success；否则进程中途重启会留下
                        # 「显示成功但从未推送」的执行记录。
                        card_task = getattr(task, "task_type", "report") in ("topic_card", "image_card")
                        execution.status = "running" if card_task else "success"
                        execution.summary_md = summary
                        summary_snapshot = summary
                        execution.summary_path = None
                        model_output_artifacts = self._store_model_output_backups(
                            task,
                            job,
                            execution,
                            summary_snapshot or "",
                            time_window,
                        )
                        model_output_paths = [item.get("path") for item in model_output_artifacts if item.get("path")]
                        if model_output_artifacts:
                            exported_files.extend(model_output_artifacts)
                        await self._sync_execution_outputs_to_ima(
                            db,
                            task=task,
                            job=job,
                            execution=execution,
                            file_paths=model_output_paths,
                        )
                        execution.prompt_usage = json.dumps(usage_stats, ensure_ascii=False)
                        execution.prompt_chars = usage_stats["chars"]["total"]
                        execution.prompt_tokens = prompt_tokens
                        final_completion_tokens = completion_tokens
                        if final_completion_tokens is None and summary_snapshot:
                            final_completion_tokens = count_tokens(summary_snapshot)
                        execution.completion_tokens = final_completion_tokens
                        execution.llm_model_name = ai_result.model.provider if ai_result.model else None
                        # 阶段性提交：生成结果先落库并释放写事务，后续推送/生图阶段不再长期持锁。
                        db.commit()
                        if getattr(task, "task_type", "report") == "topic_card":
                            summary = await self._handle_topic_card_result(
                                db=db,
                                task=task,
                                job=job,
                                execution=execution,
                                raw_response=summary_snapshot or "",
                                selected_topic=selected_topic,
                            )
                            summary_snapshot = summary
                            execution.summary_md = summary
                            execution.summary_path = None
                            self._reset_card_delivery_fields(execution)
                            await self._sync_stats_and_collect(
                                db,
                                task=task,
                                job=job,
                                execution=execution,
                                time_window=time_window,
                                message_stats_result=message_stats_result,
                                exported_files=exported_files,
                            )
                            self._log_retry_success(job, attempt)
                            execution.status = "success"
                            db.commit()
                            break
                        if getattr(task, "task_type", "report") == "image_card":
                            await self._handle_image_card_result(
                                db=db,
                                task=task,
                                job=job,
                                execution=execution,
                                raw_response=summary_snapshot or "",
                                selected_topic=selected_topic,
                            )
                            self._reset_card_delivery_fields(execution)
                            await self._sync_stats_and_collect(
                                db,
                                task=task,
                                job=job,
                                execution=execution,
                                time_window=time_window,
                                message_stats_result=message_stats_result,
                                exported_files=exported_files,
                            )
                            self._log_retry_success(job, attempt)
                            execution.status = "success"
                            db.commit()
                            break
                        html_plan: Optional[HtmlArtifactPlan] = None
                        html_content: Optional[str] = None
                        if html_required:
                            html_plan = self._render_html_plan(job, execution, datetime.now(tz=self._tz), time_window)
                            html_content = self._extract_html_document(summary)

                        if job.html_backup_enabled and html_content and html_plan:
                            execution.html_backup_path = self._store_html_report(
                                task,
                                job,
                                execution,
                                html_content,
                                time_window,
                                html_plan,
                            )
                            if execution.html_backup_path:
                                exported_files.append(
                                    {
                                        "type": "html_backup",
                                        "label": "HTML 备份",
                                        "path": execution.html_backup_path,
                                    }
                                )
                        else:
                            execution.html_backup_path = None

                        if job.github_deploy_enabled:
                            if deployment_record is None:
                                deployment_record = GithubDeployment(
                                    execution_id=execution.id,
                                    job_id=job.id,
                                    task_id=task.id,
                                    github_config_id=job.github_config_id,
                                    job_name=job.name,
                                    task_name=task.name,
                                    config_name=job.github_config.name if job.github_config else None,
                                    artifact_type="html_report",
                                    artifact_label="HTML 日报",
                                    repo_full_name=(
                                        f"{job.github_config.owner}/{job.github_config.repo}"
                                        if job.github_config
                                        else None
                                    ),
                                    branch=(
                                        (job.github_config.branch or "main").strip() or "main"
                                        if job.github_config
                                        else None
                                    ),
                                    status="running",
                                    started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                                )
                                db.add(deployment_record)
                                db.flush()
                            if not html_content or not html_plan:
                                raise RuntimeError("GitHub 部署要求模型返回完整 HTML")
                            try:
                                deploy_artifact = await self._retry_async(
                                    lambda: self._deploy_html_to_github(
                                        job=job,
                                        execution=execution,
                                        html_content=html_content,
                                        plan=html_plan,
                                    ),
                                    retries=max_retry,
                                    retry_interval=retry_interval,
                                    label="GitHub HTML 日报上传",
                                )
                                if deployment_record:
                                    deployment_record.status = "success"
                                    deployment_record.pages_url = deploy_artifact.pages_url
                                    deployment_record.repo_path = deploy_artifact.repo_path
                                    deployment_record.repo_full_name = deploy_artifact.repo_full_name
                                    deployment_record.branch = deploy_artifact.branch
                                    deployment_record.github_file_url = deploy_artifact.github_file_url
                                    deployment_record.error_msg = None
                                    deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                                view_url = (
                                    build_view_url(deployment_record, fallback_url=deploy_artifact.pages_url)
                                    if deployment_record
                                    else deploy_artifact.pages_url
                                )
                                execution.deploy_status = "success"
                                execution.deploy_url = view_url
                                execution.deploy_error = None
                                execution.github_config_id = job.github_config_id
                                exported_files.append(
                                    {
                                        "type": "github",
                                        "label": "GitHub 页面",
                                        "url": view_url,
                                        "path": deploy_artifact.repo_path,
                                        "repo_path": deploy_artifact.repo_path,
                                        "repo": deploy_artifact.repo_full_name,
                                        "branch": deploy_artifact.branch,
                                        "github_file_url": deploy_artifact.github_file_url,
                                        "deployment_record_id": deployment_record.id if deployment_record else None,
                                        "deployment_status": "success",
                                    }
                                )
                            except Exception as deploy_exc:
                                deploy_error = _format_exception_message("GitHub HTML 日报上传", deploy_exc)
                                execution.deploy_status = "failed"
                                execution.deploy_error = deploy_error
                                execution.github_config_id = job.github_config_id
                                if deployment_record:
                                    deployment_record.status = "failed"
                                    deployment_record.error_msg = deploy_error
                                    deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                                raise
                        else:
                            self._clear_deploy_fields(execution)

                        await self._sync_stats_and_collect(
                            db,
                            task=task,
                            job=job,
                            execution=execution,
                            time_window=time_window,
                            message_stats_result=message_stats_result,
                            exported_files=exported_files,
                        )

                        push_webhook_ids = _parse_int_list(task.push_webhook_ids)
                        if push_webhook_ids:
                            webhooks = webhook_repo.get_by_ids(db, push_webhook_ids)
                            logger.info("准备推送飞书 job_id={} job_name={}", job.id, job.name)
                            feishu_content = summary
                            if html_required:
                                feishu_content = self._build_html_report_push_content(task, job, execution)
                            await self._retry_async(
                                lambda: self._push_feishu(
                                    webhooks=webhooks,
                                    task=task,
                                    job=job,
                                    summary=feishu_content,
                                    raise_on_failure=True,
                                ),
                                retries=max_retry,
                                retry_interval=retry_interval,
                                label="飞书推送",
                            )
                        self._log_retry_success(job, attempt)
                        db.commit()
                        break
                    except asyncio.CancelledError as exc:
                        db.rollback()
                        if summary_snapshot:
                            execution.summary_md = summary_snapshot
                        execution.chatlog_path = execution.chatlog_path or chatlog_path
                        execution.status = "failed"
                        if not execution.error_msg:
                            reason = str(exc).strip()
                            if reason:
                                execution.error_msg = f"执行被取消：{reason}"
                            else:
                                execution.error_msg = "执行被取消：可能由于服务重启或进程退出"
                        if deployment_record and execution.deploy_status != "success":
                            deployment_record.status = "failed"
                            if execution.deploy_error:
                                deployment_record.error_msg = execution.deploy_error
                            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                        if not execution.raw_request:
                            fallback_meta = self._fallback_prompt_meta(
                                task,
                                talker_names,
                                time_window,
                                message_stats_result,
                                separator="·",
                            )
                            if fallback_meta:
                                execution.raw_request = json.dumps(fallback_meta, ensure_ascii=False)
                        logger.warning("Job {} 执行被取消: {}", job.id, exc)
                        raise
                    except Exception as exc:  # pragma: no cover - protect scheduler
                        db.rollback()
                        raw_summary = getattr(exc, "raw_summary", None)
                        if raw_summary and not summary_snapshot:
                            summary_snapshot = raw_summary
                        if summary_snapshot:
                            execution.summary_md = summary_snapshot
                        execution.error_msg = _format_exception_message("执行", exc)
                        execution.chatlog_path = execution.chatlog_path or chatlog_path
                        if allow_outer_retry and attempt <= max_retry:
                            logger.warning(
                                "Job {} 第 {}/{} 次执行失败，将在 {} 秒后重试: {}",
                                job.id,
                                attempt,
                                attempts,
                                retry_interval,
                                execution.error_msg,
                            )
                            await asyncio.sleep(retry_interval)
                            db.refresh(execution)
                            db.refresh(job)
                            continue

                        execution.status = "failed"
                        if deployment_record and execution.deploy_status != "success":
                            deployment_record.status = "failed"
                            if execution.deploy_error:
                                deployment_record.error_msg = execution.deploy_error
                            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                        if not execution.raw_request:
                            fallback_meta = self._fallback_prompt_meta(
                                task,
                                talker_names,
                                time_window,
                                message_stats_result,
                                separator="路",
                            )
                            if fallback_meta:
                                execution.raw_request = json.dumps(fallback_meta, ensure_ascii=False)
                        alert_service.create_alert(
                            db,
                            task_id=task.id,
                            job_id=job.id,
                            execution_id=execution.id,
                            category="execution",
                            message=execution.error_msg,
                            payload={"job_id": job.id},
                        )
                        await self._notify_alert_webhooks(db, task, job, execution.error_msg)
                        logger.exception("Job {} failed finally", job.id)
                        break
            finally:
                execution.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                execution.duration_ms = int(
                    (execution.finished_at - (execution.started_at or execution.finished_at)).total_seconds() * 1000
                )
                execution.exported_files = (
                    json.dumps(exported_files, ensure_ascii=False) if exported_files else None
                )
                disk_record: Optional[DiskIoRecord] = None
                try:
                    disk_record = disk_monitor_service.finish_execution_io(
                        db,
                        context=disk_io_context,
                        execution=execution,
                        task=task,
                        job=job,
                        exported_files=exported_files,
                        chat_record_telemetry=chat_record_telemetry,
                    )
                except Exception:
                    logger.exception("记录磁盘 IO 失败 execution_id={}", execution.id)
                if disk_record:
                    await self._handle_job_disk_alert(
                        db=db,
                        task=task,
                        job=job,
                        execution=execution,
                        disk_record=disk_record,
                    )
                db.add(execution)
                job.last_run_at = execution.finished_at
                if job.interval_enabled:
                    next_run = self._schedule_job(job)
                    job.next_run_at = next_run
                else:
                    job.next_run_at = self._calculate_next_run(job)
                db.add(job)
                db.commit()
        return execution_id

    @staticmethod
    def _clear_deploy_fields(execution: Execution) -> None:
        """本次执行未走 GitHub 部署时，把部署相关字段归位为未部署状态。"""
        execution.deploy_status = "none"
        execution.deploy_url = None
        execution.deploy_error = None
        execution.github_config_id = None

    @classmethod
    def _reset_card_delivery_fields(cls, execution: Execution) -> None:
        """卡片任务完成后的统一收尾：清空 HTML 备份路径与部署字段。"""
        execution.html_backup_path = None
        cls._clear_deploy_fields(execution)

    async def _sync_stats_and_collect(
        self,
        db,
        *,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        message_stats_result,
        exported_files: List[dict],
    ) -> None:
        """各分支共同的收尾：消息统计上传 GitHub 并把产物登记进 exported_files。"""
        artifact = await self._sync_message_stats_to_github(
            db=db,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            stats=message_stats_result,
        )
        if artifact:
            exported_files.append(artifact)

    @staticmethod
    def _log_retry_success(job: Job, attempt: int) -> None:
        if attempt > 1:
            logger.info("Job {} 在第 {} 次重试后成功", job.id, attempt)

    @staticmethod
    def _fallback_prompt_meta(
        task: Task,
        talker_names: List[str],
        time_window: Optional[dict],
        message_stats_result,
        *,
        separator: str,
    ) -> Optional[dict]:
        """异常路径下 raw_request 缺失时的兜底元数据；cancelled 与 failed 的分隔符沿用历史行为。"""
        if not time_window:
            return None
        meta = {
            "task_name": task.name,
            "chatlog_range": time_window.get("time_str"),
            "chatlog_label": f"{', '.join(talker_names)} {separator} {time_window.get('time_str')}",
            "talkers": talker_names,
            "task_prompt": task.prompt,
        }
        if message_stats_result:
            meta["message_count"] = message_stats_result.total_messages
        return meta


# 向后兼容再导出：保持历史 `from app.scheduler.service import X` 引用不变。
__all__ = [
    "AIOutputValidationError",
    "AiSummaryResult",
    "EMPTY_CHATLOG_ERROR_MESSAGE",
    "GithubUploadArtifact",
    "HtmlArtifactPlan",
    "IntervalPlan",
    "ModelSequenceItem",
    "SchedulerService",
    "UPSTREAM_MAX_AGE_HOURS",
    "UPSTREAM_MAX_TOPICS",
    "_extract_report_topic_sections",
    "_extract_report_topic_titles",
    "_format_exception_message",
    "job_repo",
    "scheduler_service",
    "session_scope",
    "settings",
    "webhook_repo",
]

scheduler_service = SchedulerService()
