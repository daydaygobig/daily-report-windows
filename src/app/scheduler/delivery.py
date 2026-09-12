"""卡片处理、飞书推送与结果投递（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from loguru import logger

from ..integrations import feishu, image_generation
from ..integrations.security import decrypt_value
from ..models.execution import Execution
from ..models.job import Job
from ..models.model import Model
from ..models.task import Task
from ..services import alert_service
from ..services import image_card_service, topic_card_service
from ..schemas.webhook import CARD_COLOR_OPTIONS
from ..utils import qr_overlay

from .common import (
    settings,
    webhook_repo,
)
from .errors import (
    _exception_detail,
    _format_exception_message,
)
from .parsing import (
    _filter_cards_by_topic,
    _parse_int_list,
    _select_image_blocks,
)

class DeliveryMixin:
    """图片卡/话题卡结果处理与 webhook 投递。"""

    @staticmethod
    def _load_push_webhooks(db, task: Task):
        """读取任务配置的推送 webhook 列表（未配置时返回空列表）。"""
        push_webhook_ids = _parse_int_list(task.push_webhook_ids)
        return webhook_repo.get_by_ids(db, push_webhook_ids) if push_webhook_ids else []

    @staticmethod
    def _job_retry_params(job: Job) -> tuple[int, int]:
        return (
            max(int(getattr(job, "max_retry", 0) or 0), 0),
            max(int(getattr(job, "retry_interval_sec", 0) or 0), 1),
        )

    async def _skip_image_run_with_notice(
        self,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        *,
        raw_response: str,
    ) -> None:
        """文本模型判定本次无生图内容：推送提示语并记录跳过元数据。"""
        notice = image_card_service.NO_IMAGE_CONTENT_NOTICE
        execution.summary_md = notice
        webhooks = self._load_push_webhooks(db, task)
        notice_pushed = False
        if webhooks:
            notice_pushed = await self._push_feishu(
                webhooks=webhooks,
                task=task,
                job=job,
                summary=notice,
            )
        execution.raw_response = json.dumps(
            {
                "type": "image_card",
                "block_count": 0,
                "skipped": "no_image_content",
                "skip_reason": "文本模型判定本次没有符合条件的内容",
                "model_output": raw_response,
                "notice": notice,
                "notice_pushed": notice_pushed,
                "deliveries": [],
            },
            ensure_ascii=False,
        )
        logger.info("图片卡片无符合条件内容，跳过生图 task={} job={}", task.id, job.id)

    async def _report_delivery_failures(
        self,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        *,
        category: str,
        message: str,
        failures: List[Dict[str, Any]],
    ) -> None:
        """卡片投递存在失败时的统一处理：标记执行失败 + 建告警 + 通知告警 webhook。"""
        execution.status = "failed"
        execution.error_msg = message
        alert_service.create_alert(
            db,
            task_id=task.id,
            job_id=job.id,
            execution_id=execution.id,
            category=category,
            message=message,
            payload={"job_id": job.id, "failures": failures},
        )
        await self._notify_alert_webhooks(db, task, job, message)

    def _resolve_card_header(self, webhook, task: Task, job: Optional[Job]) -> tuple[str, str, str]:
        mode = (getattr(webhook, "card_mode", "markdown") or "markdown").lower()
        color = getattr(webhook, "card_header_color", None)
        template = color if color in CARD_COLOR_OPTIONS else "blue"
        default_title = (job.name if job and job.name else None) or task.name
        replacements = {
            "{task_name}": task.name or "",
            "{job_name}": job.name if job else "",
        }

        def apply_template(template_text: Optional[str], fallback: str) -> str:
            if not template_text:
                return fallback
            result = template_text
            for token, value in replacements.items():
                result = result.replace(token, value)
            result = result.strip()
            return result or fallback

        if mode != "markdown":
            return default_title, "", template

        if not bool(getattr(webhook, "card_header_enabled", False)):
            return default_title, "", template

        title = apply_template(getattr(webhook, "card_header_title", None), default_title)
        subtitle = apply_template(getattr(webhook, "card_header_subtitle", None), "")
        return title, subtitle, template

    def _build_html_report_push_content(self, task: Task, job: Job, execution: Execution) -> str:
        generated_at = datetime.now(tz=self._tz).strftime("%Y-%m-%d %H:%M")
        lines = [
            "✅ **日报已生成**",
            "",
            f"**任务**：{task.name}",
            f"**作业**：{job.name}",
            f"**生成时间**：{generated_at}",
        ]
        deploy_url = (getattr(execution, "deploy_url", None) or "").strip()
        if deploy_url:
            # 归档路径含中文目录，飞书卡片链接需要 URL 编码才能点击
            encoded_url = quote(deploy_url, safe=":/?&=%#")
            lines += ["", f"📖 [点击在线阅读日报]({encoded_url})"]
        else:
            backup_path = getattr(execution, "html_backup_path", None)
            if backup_path:
                lines += ["", f"HTML 备份已保存至：{backup_path}"]
        return "\n".join(lines)


    async def _push_feishu(self, webhooks, task: Task, job: Optional[Job], summary: str, *, raise_on_failure: bool = False) -> bool:
        if not webhooks:
            return False
        succeeded = False
        failures: List[str] = []
        for webhook in webhooks:
            title, subtitle, template = self._resolve_card_header(webhook, task, job)
            try:
                await feishu.send_markdown(
                    webhook=webhook,
                    title=title,
                    subtitle=subtitle,
                    template=template,
                    content=summary,
                )
                succeeded = True
            except Exception as exc:
                failures.append(str(exc))
                logger.exception(
                    "推送飞书失败 webhook_id={} task={} job={}",
                    getattr(webhook, "id", None),
                    task.id,
                    getattr(job, "id", None),
                )
        if raise_on_failure and failures:
            raise RuntimeError("飞书推送失败：" + "；".join(failures))
        return succeeded

    async def _retry_async(self, operation, *, retries: int, retry_interval: int, label: str):
        attempt = 0
        total = retries + 1
        while True:
            attempt += 1
            try:
                return await operation()
            except Exception as exc:
                if attempt >= total:
                    raise RuntimeError(_format_exception_message(label, exc, attempts=total)) from exc
                logger.warning(
                    "{} 第 {}/{} 次失败，将在 {} 秒后重试：{}",
                    label,
                    attempt,
                    total,
                    retry_interval,
                    _exception_detail(exc),
                )
                await asyncio.sleep(retry_interval)

    async def _deliver_image_bytes(
        self,
        *,
        webhook,
        app_id: str,
        app_secret: str,
        image_bytes: bytes,
        filename: str,
        retries: int,
        retry_interval: int,
        label: str,
    ) -> str:
        async def operation() -> str:
            image_key = await feishu.upload_image(
                app_id=app_id,
                app_secret=app_secret,
                image_bytes=image_bytes,
                filename=filename,
            )
            await feishu.send_image(webhook, image_key=image_key, max_retries=1)
            return image_key

        return await self._retry_async(
            operation,
            retries=retries,
            retry_interval=retry_interval,
            label=label,
        )

    async def _deliver_topic_card_image(
        self,
        *,
        webhook,
        app_id: str,
        app_secret: str,
        image: topic_card_service.RenderedImage,
        retries: int,
        retry_interval: int,
    ) -> Dict[str, Any]:
        image_key = await self._deliver_image_bytes(
            webhook=webhook,
            app_id=app_id,
            app_secret=app_secret,
            image_bytes=image.path.read_bytes(),
            filename=image.path.name,
            retries=retries,
            retry_interval=retry_interval,
            label="话题卡片图片推送",
        )
        return {
            "image_key": image_key,
            "width": image.width,
            "height": image.height,
            "size_bytes": image.size_bytes,
            "engine": image.engine,
            "layout": image.layout,
        }

    async def _handle_image_card_result(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        raw_response: str,
        selected_topic: Optional[str] = None,
    ) -> None:
        max_count = max(int(getattr(job, "max_image_count", 6) or 6), 1)
        blocks = image_card_service.parse_content_blocks(
            raw_response,
            split_enabled=bool(getattr(job, "image_split_enabled", False)),
            max_count=max_count,
        )
        block_total = len(blocks)
        blocks_kinds = [image_card_service.block_card_kind(block) for block in blocks]
        blocks_preview = [
            {"index": index, "text": block[:60]} for index, block in enumerate(blocks, start=1)
        ]
        if selected_topic:
            selected_blocks = _select_image_blocks(blocks, selected_topic, job=job)
            if not selected_blocks:
                raise RuntimeError(
                    f"未找到匹配的内容块「{selected_topic}」，"
                    f"可用内容块：{'; '.join(item['text'] for item in blocks_preview)}"
                )
            blocks = selected_blocks
        if not blocks:
            await self._skip_image_run_with_notice(
                db,
                task,
                job,
                execution,
                raw_response=raw_response,
            )
            return
        image_prompt = (getattr(job, "image_prompt", None) or "").strip()
        if not image_prompt:
            raise RuntimeError("图片卡片作业未配置图片提示词模板")
        image_sequence = self._resolve_image_model_sequence(db, task)
        head_model = image_sequence[0].model
        image_model_id = int(getattr(head_model, "id", 0) or 0)
        image_model = head_model

        webhooks = self._load_push_webhooks(db, task)
        if not webhooks:
            raise RuntimeError("图片卡片任务没有可用的推送 Webhook")
        webhook_credentials = []
        for webhook in webhooks:
            app_id = (getattr(webhook, "feishu_app_id", None) or "").strip()
            secret_cipher = getattr(webhook, "feishu_app_secret_cipher", None)
            if not app_id or not secret_cipher:
                raise RuntimeError(f"Webhook「{webhook.name}」未配置飞书应用 App ID / App Secret")
            webhook_credentials.append((webhook, app_id, decrypt_value(secret_cipher)))

        aspect_ratio = getattr(job, "image_aspect_ratio", "auto") or "auto"
        resolution = getattr(job, "image_resolution", "auto") or "auto"
        image_size = image_card_service.resolve_image_size(aspect_ratio, resolution)
        max_retry, retry_interval = self._job_retry_params(job)
        meta: Dict[str, Any] = {
            "type": "image_card",
            "block_count": len(blocks),
            "block_total": block_total,
            "blocks_kinds": blocks_kinds,
            "blocks_preview": blocks_preview,
            "selected_topic": selected_topic,
            "image_model_id": image_model_id,
            "image_model_name": image_model.provider,
            "image_model_sequence": [
                {"model_id": entry.model.id, "model_name": entry.model.provider, "max_attempts": entry.max_attempts}
                for entry in image_sequence
            ],
            "image_prompt_template_id": getattr(job, "image_prompt_template_id", None),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "size": image_size,
            "request_params": {
                "model": image_model.provider,
                "n": 1,
                "size": image_size,
                "output_format": "png",
            },
            "deliveries": [],
        }
        failures: List[Dict[str, Any]] = []

        # 阶段一：逐块生成图片（任一块彻底失败即抛错终止）
        generated_items: List[Dict[str, Any]] = []
        for index, block in enumerate(blocks, start=1):
            image_prompt_text = image_card_service.compose_image_prompt(image_prompt, block)
            generated = None
            used_model: Optional[Model] = None
            image_attempt_meta: List[Dict[str, Any]] = []
            last_error: Optional[Exception] = None
            connect_failures = 0
            for entry_index, entry in enumerate(image_sequence):
                for attempt in range(1, entry.max_attempts + 1):
                    try:
                        generated = await image_generation.generate_image(
                            entry.model,
                            prompt=image_prompt_text,
                            size=image_size,
                        )
                        used_model = entry.model
                        image_attempt_meta.append(
                            {
                                "model_id": entry.model.id,
                                "model_name": entry.model.provider,
                                "attempt": attempt,
                                "status": "success",
                            }
                        )
                        break
                    except Exception as exc:
                        last_error = exc
                        attempt_record = {
                            "model_id": entry.model.id,
                            "model_name": entry.model.provider,
                            "attempt": attempt,
                            "status": "failed",
                            "error": _format_exception_message("图片生成", exc),
                        }
                        # 连接类失败（本机网络/系统代理瞬断）时各接口走同一条本地
                        # 链路，背靠背重试会一起失败——递增退避后再试，给链路恢复
                        # 留出窗口；其余错误维持原有立即重试
                        later_attempts = (entry.max_attempts - attempt) + sum(
                            later.max_attempts for later in image_sequence[entry_index + 1 :]
                        )
                        if later_attempts > 0 and image_generation.is_connect_failure(exc):
                            connect_failures += 1
                            backoff_sec = min(30 * connect_failures, 120)
                            attempt_record["backoff_sec"] = backoff_sec
                            await asyncio.sleep(backoff_sec)
                        image_attempt_meta.append(attempt_record)
                        generated = None
                if generated is not None:
                    break
            if generated is None:
                error_message = _format_exception_message("图片生成", last_error) if last_error else "图片生成失败"
                meta["deliveries"].append(
                    {
                        "image_index": index,
                        "status": "failed",
                        "requested_size": image_size,
                        "error": error_message,
                        "model_attempts": image_attempt_meta,
                        "webhooks": [],
                    }
                )
                meta["generation_error"] = {
                    "image_index": index,
                    "error": error_message,
                    "model_attempts": image_attempt_meta,
                }
                # 已生成的半卡先落盘再抛错，失败执行也能事后取图补拼，不白跑
                if generated_items:
                    try:
                        partial_backup = image_card_service.backup_execution_images(
                            getattr(execution, "id", None),
                            halves=[item["image"].content for item in generated_items],
                            source_text=raw_response,
                        )
                    except Exception as exc:
                        logger.warning(
                            "失败执行的部分半卡落盘失败：{}",
                            _format_exception_message("图片备份", exc),
                        )
                        partial_backup = {}
                    if partial_backup:
                        meta["partial_backup"] = partial_backup
                execution.raw_response = json.dumps(meta, ensure_ascii=False)
                raise RuntimeError(f"第 {index} 张图片生成失败：{error_message}") from last_error
            generated_items.append(
                {
                    "block_index": index,
                    "image": generated,
                    "model": used_model,
                    "attempts": image_attempt_meta,
                }
            )

        # 阶段二：拼卡。1:3 比例下，同一话题的上卡+下卡上下拼接成一张长图。
        # 带拼卡标记的内容按标记配对（错序在 parse 阶段已拦截），无标记的历史内容
        # 退回按生成顺序相邻两张配对。拼接由代码完成（像素级对齐），不依赖生图模型输出可拼接的图。
        stitch_pairs = aspect_ratio == "1:3" and len(generated_items) > 1
        final_images: List[Dict[str, Any]] = []
        if stitch_pairs:
            card_groups = image_card_service.resolve_card_pairs(
                blocks,
                split_enabled=bool(getattr(job, "image_split_enabled", False)),
            )
            if not image_card_service.has_card_markers(blocks):
                meta["stitch_warning"] = "内容块无【拼卡·上/下】标记，按相邻位置配对"
            for group_indexes in card_groups:
                group = [generated_items[index - 1] for index in group_indexes]
                merged_content = await asyncio.to_thread(
                    image_card_service.stitch_images_vertically,
                    [item["image"].content for item in group],
                )
                final_images.append(
                    {
                        "parts": [item["block_index"] for item in group],
                        "image": image_generation.GeneratedImage(content=merged_content),
                        "models": [item["model"] for item in group],
                        "attempts": [item["attempts"] for item in group],
                    }
                )
            meta["stitch"] = {
                "enabled": True,
                "mode": "vertical_pair",
                "pairs": [item["parts"] for item in final_images],
            }
        else:
            if aspect_ratio == "1:3":
                meta["stitch"] = {"enabled": False, "reason": "内容块不足两张，按单卡输出"}
            for item in generated_items:
                final_images.append(
                    {
                        "parts": [item["block_index"]],
                        "image": item["image"],
                        "models": [item["model"]],
                        "attempts": [item["attempts"]],
                    }
                )

        try:
            backup_meta = image_card_service.backup_execution_images(
                getattr(execution, "id", None),
                halves=[item["image"].content for item in generated_items],
                cards=[item["image"].content for item in final_images],
                source_text=raw_response,
            )
        except Exception as exc:
            logger.warning(
                "案例卡图片落盘备份失败：{}",
                _format_exception_message("图片备份", exc),
            )
            backup_meta = {}
        if backup_meta:
            meta["local_backup"] = backup_meta

        # 阶段三：二维码叠加（叠加在拼接后的成图上，每张长图一个码）
        for position, item in enumerate(final_images, start=1):
            generated = item["image"]
            qr_overlay_applied = False
            if settings.qr_code_enabled and settings.qr_code_url:
                try:
                    overlaid = await asyncio.to_thread(
                        qr_overlay.apply_qr_overlay,
                        generated.content,
                        url=settings.qr_code_url,
                        caption=settings.qr_code_caption,
                        size_ratio=settings.qr_code_size_ratio,
                    )
                    generated = image_generation.GeneratedImage(
                        content=overlaid.content,
                        mime_type=overlaid.mime_type,
                        revised_prompt=generated.revised_prompt,
                    )
                    qr_overlay_applied = True
                except Exception as exc:
                    logger.warning(
                        "案例卡二维码叠加失败，使用原图推送：{}",
                        _format_exception_message("二维码叠加", exc),
                    )

            actual_dimensions = image_generation.detect_image_dimensions(generated.content, generated.mime_type)
            actual_width = actual_dimensions[0] if actual_dimensions else None
            actual_height = actual_dimensions[1] if actual_dimensions else None
            actual_size = f"{actual_width}x{actual_height}" if actual_dimensions else None
            image_meta: Dict[str, Any] = {
                "image_index": position,
                "parts": item["parts"],
                "status": "success",
                "requested_size": image_size,
                "image_model_id": item["models"][0].id if item["models"] and item["models"][0] else None,
                "image_model_name": item["models"][0].provider if item["models"] and item["models"][0] else None,
                "model_attempts": [attempt for sub in item["attempts"] for attempt in sub],
                "actual_width": actual_width,
                "actual_height": actual_height,
                "actual_size": actual_size,
                "size_bytes": generated.size_bytes,
                "mime_type": generated.mime_type,
                "qr_code_overlay": qr_overlay_applied,
                "webhooks": [],
            }
            for webhook, app_id, app_secret in webhook_credentials:
                delivery = {
                    "webhook_id": getattr(webhook, "id", None),
                    "webhook_name": getattr(webhook, "name", None),
                    "status": "pending",
                }
                try:
                    image_key = await self._deliver_image_bytes(
                        webhook=webhook,
                        app_id=app_id,
                        app_secret=app_secret,
                        image_bytes=generated.content,
                        filename=f"image-card-{position}.png",
                        retries=max_retry,
                        retry_interval=retry_interval,
                        label="图片卡片推送",
                    )
                    delivery.update({"status": "success", "image_key": image_key})
                except Exception as exc:
                    error_message = _format_exception_message("图片卡片推送", exc)
                    delivery.update({"status": "failed", "error": error_message})
                    failures.append(
                        {
                            "image_index": position,
                            "webhook_id": getattr(webhook, "id", None),
                            "webhook_name": getattr(webhook, "name", None),
                            "error": error_message,
                        }
                    )
                image_meta["webhooks"].append(delivery)
            meta["deliveries"].append(image_meta)

        if failures:
            error_message = "图片卡片推送失败：" + "；".join(
                f"第 {item['image_index']} 张 / {item.get('webhook_name') or item.get('webhook_id')}：{item['error']}"
                for item in failures
            )
            await self._report_delivery_failures(
                db,
                task,
                job,
                execution,
                category="image_card",
                message=error_message,
                failures=failures,
            )
        execution.raw_response = json.dumps(meta, ensure_ascii=False)

    def _build_topic_card_image_failure_message(self, failures: List[Dict[str, Any]]) -> str:
        if not failures:
            return "话题卡片图片推送失败"
        if len(failures) == 1:
            return str(failures[0].get("error") or "话题卡片图片推送失败")
        details = []
        for item in failures:
            name = item.get("webhook_name") or f"Webhook {item.get('webhook_id') or '-'}"
            error = item.get("error") or "未知错误"
            details.append(f"{name}：{error}")
        return "话题卡片图片推送失败：" + "；".join(details)

    async def _handle_topic_card_result(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        raw_response: str,
        selected_topic: Optional[str] = None,
    ) -> str:
        webhooks = self._load_push_webhooks(db, task)
        meta: Dict[str, Any] = {
            "type": "topic_card",
            "text_layout": getattr(job, "topic_text_layout", "per_topic") or "per_topic",
            "image_enabled": bool(getattr(job, "topic_image_enabled", False)),
            "image_layout": getattr(job, "topic_image_layout", "single") or "single",
            "deliveries": [],
        }
        style_config = topic_card_service.normalize_topic_style_config(getattr(task, "topic_style_config", None))
        meta["style_config"] = style_config
        try:
            cards = topic_card_service.parse_topic_cards(raw_response, style_config=style_config)
        except Exception as exc:
            logger.exception("话题卡片 JSON 解析失败 task={} job={}", task.id, job.id)
            meta["parse_error"] = str(exc)
            execution.raw_response = json.dumps(meta, ensure_ascii=False)
            raise RuntimeError(f"话题卡片 JSON 解析失败：{exc}") from exc

        meta["cards"] = cards
        if selected_topic:
            all_cards = cards
            cards = _filter_cards_by_topic(all_cards, selected_topic)
            meta["selected_topic"] = selected_topic
            meta["selected_cards"] = cards
            if not cards:
                titles = [str(card.get("title") or "") for card in all_cards]
                raise RuntimeError(
                    f"未找到匹配话题「{selected_topic}」，本次可用话题：{'; '.join(t for t in titles if t)}"
                )
        if not cards:
            summary = "本时段无职场话题讨论"
            meta["skipped"] = "empty_cards"
            execution.raw_response = json.dumps(meta, ensure_ascii=False)
            if webhooks:
                await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=summary)
            return summary

        text_messages = topic_card_service.build_text_messages(
            cards,
            layout=getattr(job, "topic_text_layout", "per_topic") or "per_topic",
            threshold=int(getattr(job, "topic_text_merge_threshold", 3) or 3),
        )
        summary = "\n\n---\n\n".join(text_messages)

        if webhooks and text_messages:
            if len(text_messages) == 1:
                await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=text_messages[0])
            else:
                for message in text_messages:
                    await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=message)

        rendered_by_engine: dict[str, list[topic_card_service.RenderedImage]] = {}
        image_failures: List[Dict[str, Any]] = []
        if bool(getattr(job, "topic_image_enabled", False)) and webhooks:
            image_layout = topic_card_service.resolve_image_layout(
                getattr(job, "topic_image_layout", "single") or "single",
                len(cards),
                int(getattr(job, "topic_image_merge_threshold", 3) or 3),
            )
            max_retry, retry_interval = self._job_retry_params(job)
            try:
                for webhook in webhooks:
                    delivery: Dict[str, Any] = {
                        "webhook_id": getattr(webhook, "id", None),
                        "webhook_name": getattr(webhook, "name", None),
                        "status": "pending",
                    }
                    try:
                        app_id = (getattr(webhook, "feishu_app_id", None) or "").strip()
                        secret_cipher = getattr(webhook, "feishu_app_secret_cipher", None)
                        if not app_id or not secret_cipher:
                            raise RuntimeError("Webhook 未配置飞书应用 App ID / App Secret，无法上传图片")
                        app_secret = decrypt_value(secret_cipher)
                        engine = getattr(webhook, "image_render_engine", "satori") or "satori"
                        cache_key = f"{engine}:{image_layout}"
                        if cache_key not in rendered_by_engine:
                            rendered_by_engine[cache_key] = await topic_card_service.render_images(
                                cards,
                                engine=engine,
                                layout=image_layout,
                            )
                        image_items = []
                        for image in rendered_by_engine[cache_key]:
                            image_items.append(
                                await self._deliver_topic_card_image(
                                    webhook=webhook,
                                    app_id=app_id,
                                    app_secret=app_secret,
                                    image=image,
                                    retries=max_retry,
                                    retry_interval=retry_interval,
                                )
                            )
                        delivery["status"] = "success"
                        delivery["images"] = image_items
                    except Exception as exc:
                        error_message = _format_exception_message("话题卡片图片推送", exc)
                        logger.exception(
                            "话题卡片图片推送失败 webhook={} task={} job={}",
                            getattr(webhook, "id", None),
                            task.id,
                            job.id,
                        )
                        delivery["status"] = "failed"
                        delivery["error"] = error_message
                        image_failures.append(
                            {
                                "webhook_id": getattr(webhook, "id", None),
                                "webhook_name": getattr(webhook, "name", None),
                                "error": error_message,
                            }
                        )
                    meta["deliveries"].append(delivery)
                if rendered_by_engine:
                    try:
                        backups = self._backup_topic_card_files(job=job, cards=cards, rendered=rendered_by_engine)
                        if backups:
                            meta["local_backups"] = backups
                            logger.info(
                                "话题卡片本地备份完成 job={} files={}",
                                job.id,
                                [item["path"] for item in backups],
                            )
                    except Exception:
                        logger.exception("话题卡片本地备份失败 job={}", job.id)
            finally:
                for images in rendered_by_engine.values():
                    topic_card_service.cleanup_images(images)

        if image_failures:
            error_message = self._build_topic_card_image_failure_message(image_failures)
            await self._report_delivery_failures(
                db,
                task,
                job,
                execution,
                category="topic_card_image",
                message=error_message,
                failures=image_failures,
            )

        execution.raw_response = json.dumps(meta, ensure_ascii=False)
        return summary

