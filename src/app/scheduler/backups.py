"""本地产物备份与命名（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from bs4 import BeautifulSoup
from loguru import logger

from ..integrations import github
from ..integrations.security import decrypt_value
from ..models.execution import Execution
from ..models.github_deployment import GithubDeployment
from ..models.job import Job
from ..models.task import Task
from ..services import topic_card_service
from ..utils import message_stats as message_stats_utils

from .errors import (
    _format_exception_message,
)
from .parsing import (
    _is_weekly_report,
    _parse_str_list,
    _sanitize_filename,
    _strip_markdown_fence,
)
from .types import (
    HtmlArtifactPlan,
)

class BackupMixin:
    """聊天记录/模型输出/HTML/话题卡图片等本地产物落盘。"""

    def _ensure_html_document(self, content: str) -> str:
        text = (content or "").lstrip("\ufeff").strip()
        if not text:
            raise RuntimeError("HTML 内容为空")
        lower = text.lstrip().lower()
        if not (lower.startswith("<!doctype html") or lower.startswith("<html")):
            raise RuntimeError("模型需返回完整 HTML（缺少 <!DOCTYPE html> 或 <html>）")
        if not text.rstrip().lower().endswith("</html>"):
            raise RuntimeError("模型需返回完整 HTML（缺少 </html>）")
        try:
            BeautifulSoup(text, "html5lib")
        except Exception as exc:
            raise RuntimeError("HTML 内容解析失败") from exc
        return text

    def _extract_html_document(self, content: str) -> str:
        html_source = _strip_markdown_fence(content)
        try:
            return self._ensure_html_document(html_source)
        except RuntimeError as first_error:
            text = (content or "").lstrip("\ufeff").strip()
            lower = text.lower()
            start = lower.find("<!doctype html")
            if start < 0:
                start = lower.find("<html")
            end = lower.rfind("</html>")
            if start < 0 or end < 0 or end < start:
                raise first_error
            end += len("</html>")
            return self._ensure_html_document(text[start:end])

    def _render_html_plan(
        self,
        job: Job,
        execution: Execution,
        generated_at: datetime,
        time_window: Optional[dict],
    ) -> HtmlArtifactPlan:
        template = getattr(job, "github_filename_template", None)
        if not template and job.github_config and job.github_config.filename_template:
            template = job.github_config.filename_template
        template = (template or "新茧群日报_{YYYY-MM-DD}.html").strip()
        days_offset = 0 if _is_weekly_report(job) else int(getattr(job, "days_offset", 0) or 0)
        target_date = generated_at + timedelta(days=days_offset)
        task_rel = getattr(job, "task", None)
        task_name = getattr(task_rel, "name", "") if task_rel else ""
        job_name = getattr(job, "name", "") or ""
        start_dt = target_date
        end_dt = target_date
        if time_window:
            maybe_start = time_window.get("start")
            if isinstance(maybe_start, datetime):
                start_dt = maybe_start
            maybe_end = time_window.get("end")
            if isinstance(maybe_end, datetime):
                end_dt = maybe_end
        end_reference = end_dt - timedelta(seconds=1) if end_dt > start_dt else end_dt
        replacements = {
            "{YYYY-MM-DD HH:MM}": target_date.strftime("%Y-%m-%d %H:%M"),
            "{YYYY-MM-DD}": target_date.strftime("%Y-%m-%d"),
            "{YYYYMMDD_HHmmss}": target_date.strftime("%Y%m%d_%H%M%S"),
            "{YYYYMMDD}": target_date.strftime("%Y%m%d"),
            "{task_name}": task_name,
            "{job_name}": job_name,
            "{job_id}": str(job.id),
            "{task_id}": str(job.task_id),
            "{execution_id}": str(execution.id or ""),
            "{week_start}": self._format_week_label(start_dt),
            "{week_end}": self._format_week_label(end_reference),
        }
        filename = template
        for placeholder, value in replacements.items():
            filename = filename.replace(placeholder, value)
        filename = _sanitize_filename(filename)
        if not filename.lower().endswith(".html"):
            filename = f"{filename}.html"
        return HtmlArtifactPlan(filename=filename, target_date=target_date, generated_at=generated_at)

    def _store_chatlog_backup(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        if not chatlog_text.strip():
            return []
        job_flag = getattr(job, "chatlog_backup_enabled", None)
        if job_flag is None:
            if not getattr(task, "store_chatlog", False):
                return []
            return self._store_chatlog_backup_legacy(task, job, chatlog_text, time_window)
        if not job_flag:
            return []
        return self._store_chatlog_backup_modern(task, job, execution, chatlog_text, time_window)

    def _store_chatlog_backup_legacy(
        self,
        task: Task,
        job: Job,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        try:
            subdir = self._backup_dir / f"task_{task.id}" / "chatlogs"
            subdir.mkdir(parents=True, exist_ok=True)

            start_label, end_label = self._format_window_labels(time_window)
            filename = f"{start_label} - {end_label}.txt" if end_label else f"{start_label}.txt"
            path = subdir / filename
            if path.exists():
                stamp = datetime.now(tz=self._tz).strftime("%Y%m%d_%H%M%S")
                filename = f"{start_label} - {end_label} ({stamp}).txt" if end_label else f"{start_label} ({stamp}).txt"
                path = subdir / filename
            normalized = self._format_chatlog_for_export(chatlog_text)
            path.write_text(normalized, encoding="utf-8")
            return [
                {
                    "type": "chatlog",
                    "label": "聊天记录（TXT）",
                    "path": str(path),
                }
            ]
        except Exception:
            logger.exception("Failed to store chatlog backup for task {} job {}", task.id, job.id)
            return []

    def _store_chatlog_backup_modern(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        try:
            formats = _parse_str_list(getattr(job, "chatlog_backup_formats", None)) or ["txt"]
            directory = self._resolve_output_dir(getattr(job, "chatlog_backup_path", None), "chatlogs")
            template = getattr(job, "chatlog_backup_filename_template", None) or "聊天记录_{week_start}_{week_end}"
            offset = int(getattr(job, "chatlog_backup_filename_date_offset_days", 0) or 0)
            base_name = self._render_output_basename(
                template,
                task=task,
                job=job,
                execution=execution,
                time_window=time_window or {},
                offset_days=offset,
                fallback="聊天记录",
                reference_dt=self._get_offset_reference_datetime(execution, time_window),
            )
            normalized = self._format_chatlog_for_export(chatlog_text)
            artifacts: List[Dict[str, str]] = []
            for fmt in formats:
                ext = fmt.lower()
                if ext not in {"md", "txt"}:
                    ext = "txt"
                filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
                path = self._ensure_unique_path(directory / filename)
                path.write_text(normalized, encoding="utf-8")
                artifacts.append(
                    {
                        "type": "chatlog",
                        "label": f"聊天记录（{ext.upper()}）",
                        "path": str(path),
                    }
                )
            return artifacts
        except Exception:
            logger.exception("Failed to store chatlog backup for task {} job {}", task.id, job.id)
            return []

    def _format_chatlog_for_export(self, chatlog_text: str) -> str:
        if not chatlog_text:
            return chatlog_text
        lines = chatlog_text.splitlines()
        if not lines:
            return chatlog_text
        formatted: List[str] = []
        sender_pattern = message_stats_utils.SENDER_PATTERN
        for line in lines:
            stripped = line.strip()
            if stripped and sender_pattern.match(stripped):
                if formatted and formatted[-1] != "":
                    formatted.append("")
            formatted.append(line)
        return "\n".join(formatted).rstrip() + "\n"

    def _should_compute_message_stats(self, task: Task, job: Job) -> bool:
        task_requires_count = bool(
            getattr(task, "system_prompt_custom_enabled", False)
            and getattr(task, "system_prompt_include_message_count", False)
        )
        return task_requires_count or bool(getattr(job, "message_stats_enabled", False)) or bool(
            getattr(job, "message_stats_github_enabled", False)
        )

    def _export_message_stats_files(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        stats: Optional[message_stats_utils.MessageStats],
    ) -> List[Dict[str, str]]:
        if not getattr(job, "message_stats_enabled", False) or not stats:
            return []
        formats = _parse_str_list(getattr(job, "message_stats_formats", None))
        if not formats:
            formats = ["md"]
        directory = self._resolve_output_dir(getattr(job, "message_stats_path", None), "message_reports")
        template = getattr(job, "message_stats_filename_template", None) or "每日群成员发言数量统计_{YYYY-MM-DD}"
        raw_offset = getattr(job, "message_stats_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="每日群成员发言数量统计",
            reference_dt=self._get_offset_reference_datetime(execution, time_window),
        )
        time_label = self._format_time_range_label(time_window)
        artifacts: List[Dict[str, str]] = []
        for fmt in formats:
            ext = fmt.lower()
            if ext not in {"md", "csv", "xlsx"}:
                ext = "md"
            filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
            path = self._ensure_unique_path(directory / filename)
            if ext == "md":
                content = message_stats_utils.render_markdown_report(
                    stats,
                    report_title=base_name,
                    time_range_label=time_label,
                )
                message_stats_utils.write_markdown(path, content)
            elif ext == "csv":
                message_stats_utils.export_csv(path, stats)
            elif ext == "xlsx":
                message_stats_utils.export_xlsx(path, stats)
            artifacts.append(
                {
                    "type": "message_stats",
                    "label": f"消息统计（{ext.upper()}）",
                    "path": str(path),
                }
            )
        return artifacts

    async def _sync_message_stats_to_github(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        stats: Optional[message_stats_utils.MessageStats],
    ) -> Optional[Dict[str, str]]:
        if not getattr(job, "message_stats_github_enabled", False):
            return None
        if not getattr(job, "message_stats_enabled", False):
            return None
        if not stats:
            return None

        config = getattr(job, "message_stats_github_config", None)
        if not config:
            raise RuntimeError("消息统计 GitHub 配置缺失")

        token = decrypt_value(config.token_cipher)
        branch = (config.branch or "main").strip() or "main"
        template = (
            getattr(job, "message_stats_github_filename_template", None)
            or "每日群成员发言数量统计_{YYYY-MM-DD}"
        )
        raw_offset = getattr(job, "message_stats_github_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        reference_dt = self._get_offset_reference_datetime(execution, time_window)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="每日群成员发言数量统计",
            reference_dt=reference_dt,
        )
        filename = base_name if base_name.lower().endswith(".md") else f"{base_name}.md"

        target_dt = reference_dt
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=self._tz)
        target_dt = target_dt + timedelta(days=offset)
        year_label = target_dt.strftime("%Y")
        year_short = target_dt.strftime("%y")
        month_label = str(int(target_dt.strftime("%m")))
        root = (getattr(job, "message_stats_github_root", None) or "xinjian").strip().strip("/ ")
        if not root:
            root = "xinjian"
        relative_dir = f"{root}/{year_label}年/{year_short}年{month_label}月消息统计"
        relative_path = f"{relative_dir}/{filename}"
        relative_path = self._compose_content_path(config.path_prefix, relative_path)
        repo_full_name = f"{config.owner}/{config.repo}"
        github_file_url = self._build_github_file_url(config, branch, relative_path)
        deployment_record = GithubDeployment(
            execution_id=execution.id,
            job_id=job.id,
            task_id=task.id,
            github_config_id=getattr(config, "id", None),
            job_name=job.name,
            task_name=task.name,
            config_name=config.name,
            artifact_type="message_stats",
            artifact_label="GitHub 消息统计",
            repo_full_name=repo_full_name,
            branch=branch,
            repo_path=relative_path,
            github_file_url=github_file_url,
            status="running",
            started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
        )
        db.add(deployment_record)
        db.flush()
        time_label = self._format_time_range_label(time_window)
        content = message_stats_utils.render_markdown_report(
            stats,
            report_title=base_name,
            time_range_label=time_label,
        )
        commit_message = f"feat: sync message stats job {job.id} execution {execution.id}"
        max_retry = max(int(getattr(job, "max_retry", 0) or 0), 0)
        retry_interval = max(int(getattr(job, "retry_interval_sec", 0) or 0), 1)
        try:
            await self._retry_async(
                lambda: github.upload_text_file(
                    token=token,
                    owner=config.owner,
                    repo=config.repo,
                    branch=branch,
                    path=relative_path,
                    content=content,
                    commit_message=commit_message,
                ),
                retries=max_retry,
                retry_interval=retry_interval,
                label="GitHub 消息统计上传",
            )
        except Exception as exc:
            error_message = _format_exception_message("GitHub 消息统计上传", exc)
            deployment_record.status = "failed"
            deployment_record.error_msg = error_message
            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
            raise
        deployment_record.status = "success"
        deployment_record.error_msg = None
        deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
        return {
            "type": "github_message_stats",
            "label": "GitHub 消息统计",
            "path": relative_path,
            "repo_path": relative_path,
            "repo": repo_full_name,
            "branch": branch,
            "github_file_url": github_file_url,
            "deployment_record_id": deployment_record.id,
            "deployment_status": "success",
        }

    async def _sync_execution_outputs_to_ima(
        self,
        db,
        *,
        task: Task,
        job: Job,
        execution: Execution,
        file_paths: Sequence[Optional[str]],
    ) -> None:
        try:
            from ..services import ima_sync_service

            valid_paths = [path for path in file_paths if path]
            await ima_sync_service.sync_execution_outputs(
                db,
                task=task,
                job=job,
                execution=execution,
                file_paths=valid_paths,
            )
        except Exception as exc:  # pragma: no cover - protect main flow
            logger.exception("执行后同步到 IMA 失败 execution_id={}", execution.id)
            execution.ima_sync_status = "failed"
            execution.ima_sync_error = str(exc)
            db.add(execution)
            db.flush()

    def _store_model_output_backups(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        content: str,
        time_window: dict,
    ) -> List[Dict[str, str]]:
        if not getattr(job, "model_output_backup_enabled", False):
            return []
        text = (content or "").strip()
        if not text:
            return []
        formats = _parse_str_list(getattr(job, "model_output_formats", None)) or ["md"]
        directory = self._resolve_output_dir(getattr(job, "model_output_path", None), "model_outputs")
        template = getattr(job, "model_output_filename_template", None) or "模型输出_{YYYY-MM-DD}"
        raw_offset = getattr(job, "model_output_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="模型输出",
            reference_dt=self._get_offset_reference_datetime(execution, time_window),
        )
        normalized = text if text.endswith("\n") else f"{text}\n"
        artifacts: List[Dict[str, str]] = []
        for fmt in formats:
            ext = fmt.lower()
            if ext not in {"md", "txt"}:
                ext = "md"
            filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
            path = self._ensure_unique_path(directory / filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(normalized, encoding="utf-8")
            artifacts.append(
                {
                    "type": "model_output",
                    "label": f"模型返回结果（{ext.upper()}）",
                    "path": str(path),
                }
            )
        return artifacts

    def _backup_topic_card_files(
        self,
        *,
        job: Job,
        cards: List[Dict[str, Any]],
        rendered: Dict[str, List[topic_card_service.RenderedImage]],
    ) -> List[Dict[str, str]]:
        """话题/案例卡片本地备份：图片 PNG + 对应 markdown，按日期分文件夹。

        目录复用 _resolve_output_dir：未配置时落在 backups/topic_cards/ 下。
        """
        if not getattr(job, "topic_image_backup_enabled", False):
            return []
        images: List[topic_card_service.RenderedImage] = []
        seen: set[str] = set()
        for items in rendered.values():
            for image in items:
                key = str(image.path)
                if key not in seen:
                    seen.add(key)
                    images.append(image)
        if not images:
            return []
        date_str = datetime.now(tz=self._tz).strftime("%Y-%m-%d")
        directory = (
            self._resolve_output_dir(getattr(job, "topic_image_backup_path", None), Path("topic_cards")) / date_str
        )
        artifacts: List[Dict[str, str]] = []
        per_card = len(images) == len(cards)
        for index, image in enumerate(images):
            card = cards[index] if per_card else None
            base_name = self._topic_card_backup_basename(date_str, index, card)
            target = self._ensure_unique_path(directory / f"{base_name}{image.path.suffix or '.png'}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image.path, target)
            artifacts.append({"type": "topic_card_image", "label": "卡片图片本地备份", "path": str(target)})
            markdown = self._topic_card_markdown_for(cards, card, per_card)
            if markdown:
                md_path = self._ensure_unique_path(directory / f"{base_name}.md")
                normalized = markdown if markdown.endswith("\n") else f"{markdown}\n"
                md_path.write_text(normalized, encoding="utf-8")
                artifacts.append({"type": "topic_card_markdown", "label": "卡片文本本地备份", "path": str(md_path)})
        return artifacts

    @staticmethod
    def _topic_card_backup_basename(date_str: str, index: int, card: Optional[Dict[str, Any]]) -> str:
        if not card:
            return f"{date_str}_合集_{index + 1:02d}"
        title = re.sub(r'[\\/:*?"<>|\r\n\t]', "", str(card.get("title") or "")).strip()
        title = title[:40].strip() or "卡片"
        return f"{date_str}_{index + 1:02d}_{title}"

    @staticmethod
    def _topic_card_markdown_for(
        cards: List[Dict[str, Any]],
        card: Optional[Dict[str, Any]],
        per_card: bool,
    ) -> str:
        if per_card and card is not None:
            messages = topic_card_service.build_text_messages([card], layout="per_topic", threshold=1)
        else:
            messages = topic_card_service.build_text_messages(cards, layout="merged", threshold=1)
        return "\n\n---\n\n".join(messages)

    def _store_html_report(
        self,
        task,
        job: Job,
        execution: Execution,
        html_content: str,
        time_window: dict | None,
        plan: HtmlArtifactPlan,
    ) -> Optional[str]:
        try:
            custom_dir = getattr(job, "html_backup_path", None)
            default_dir = self._backup_dir / "html_reports" / plan.target_date.strftime("%Y")
            default_dir.mkdir(parents=True, exist_ok=True)
            base_dir = (
                self._resolve_output_dir(custom_dir, default_dir)
                if custom_dir
                else default_dir
            )
            filename = plan.filename
            override_template = getattr(job, "html_backup_filename_template", None)
            if override_template:
                base_name = self._render_output_basename(
                    override_template,
                    task=task,
                    job=job,
                    execution=execution,
                    time_window=time_window or {},
                    offset_days=0 if _is_weekly_report(job) else int(getattr(job, "html_backup_filename_date_offset_days", 0) or 0),
                    fallback=plan.filename.rsplit(".", 1)[0],
                    reference_dt=self._get_offset_reference_datetime(execution, time_window),
                )
                filename = base_name if base_name.lower().endswith(".html") else f"{base_name}.html"
            path = base_dir / filename
            path.write_text(html_content, encoding="utf-8")
            return str(path)
        except Exception:
            logger.exception("Failed to store HTML backup job={} execution={}", job.id, execution.id)
            return None

    def _resolve_output_dir(self, configured_path: Optional[str], default_subdir: str | Path) -> Path:
        base = Path(default_subdir)
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if not candidate.is_absolute():
                candidate = self._backup_dir / candidate
        else:
            candidate = base if base.is_absolute() else self._backup_dir / base
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _render_output_basename(
        self,
        template: Optional[str],
        *,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        offset_days: int,
        fallback: str,
        reference_dt: Optional[datetime] = None,
    ) -> str:
        pattern = (template or fallback or "report").strip()
        start_dt: datetime = time_window.get("start") or datetime.now(tz=self._tz).replace(tzinfo=None)
        end_dt: datetime = time_window.get("end") or start_dt
        anchor = reference_dt or start_dt
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=self._tz)
        target_dt = anchor + timedelta(days=offset_days)
        week_start_label = self._format_week_label(start_dt)
        end_reference = end_dt - timedelta(seconds=1) if end_dt > start_dt else end_dt
        week_end_label = self._format_week_label(end_reference)
        replacements = {
            "{YYYY-MM-DD HH:MM}": target_dt.strftime("%Y-%m-%d %H:%M"),
            "{YYYY-MM-DD}": target_dt.strftime("%Y-%m-%d"),
            "{YYYYMMDD_HHmmss}": target_dt.strftime("%Y%m%d_%H%M%S"),
            "{YYYYMMDD}": target_dt.strftime("%Y%m%d"),
            "{task_name}": task.name or "",
            "{job_name}": job.name or "",
            "{job_id}": str(job.id or ""),
            "{task_id}": str(task.id or ""),
            "{execution_id}": str(execution.id or ""),
            "{week_start}": week_start_label,
            "{week_end}": week_end_label,
        }
        filename = pattern
        for placeholder, value in replacements.items():
            filename = filename.replace(placeholder, value)
        return _sanitize_filename(filename) or fallback

    def _get_offset_reference_datetime(self, execution: Execution, time_window: Optional[dict]) -> datetime:
        candidates: List[Optional[datetime]] = [
            getattr(execution, "finished_at", None),
            getattr(execution, "started_at", None),
        ]
        if time_window:
            candidates.extend([time_window.get("end"), time_window.get("start")])
        for dt in candidates:
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=self._tz)
                return dt
        return datetime.now(tz=self._tz)

    def _format_time_range_label(self, time_window: dict) -> str:
        start = time_window.get("start")
        end = time_window.get("end")
        if isinstance(start, datetime) and isinstance(end, datetime):
            return f"{start.strftime('%Y-%m-%d %H:%M')} 到 {end.strftime('%Y-%m-%d %H:%M')}"
        return time_window.get("time_str") or ""

    def _ensure_unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        timestamp = datetime.now(tz=self._tz).strftime("%Y%m%d_%H%M%S")
        stem = path.stem
        suffix = path.suffix
        counter = 1
        candidate = path.with_name(f"{stem}_{timestamp}{suffix}")
        while candidate.exists():
            counter += 1
            candidate = path.with_name(f"{stem}_{timestamp}_{counter}{suffix}")
        return candidate

    @staticmethod
    def _format_week_label(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    def _format_window_labels(self, time_window: dict | None) -> tuple[str, Optional[str]]:
        def sanitize(label: str) -> str:
            return label.replace(":", "-")

        if not time_window:
            return sanitize("unknown"), None

        start = time_window.get("start")
        end = time_window.get("end")
        if isinstance(start, datetime):
            start_label = sanitize(start.strftime("%Y-%m-%d %H-%M"))
        else:
            start_label = None
        if isinstance(end, datetime):
            end_label = sanitize(end.strftime("%Y-%m-%d %H-%M"))
        else:
            end_label = None

        if not start_label or not end_label:
            time_str = time_window.get("time_str", "")
            if "~" in time_str:
                start_raw, end_raw = [part.strip() for part in time_str.split("~", 1)]
                start_label = start_label or sanitize(start_raw)
                end_label = end_label or sanitize(end_raw)
            else:
                start_label = start_label or sanitize(time_str or "unknown")

        return start_label or "unknown", end_label

