"""提示词组装与模型序列 LLM 调用（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import json
from typing import Any, List, Optional

from loguru import logger

from ..integrations import llm
from ..models.job import Job
from ..models.model import Model
from ..models.task import Task
from ..services import chat_record_service
from ..services import html_case_card_service, image_card_service, topic_card_service
from ..utils import message_stats as message_stats_utils

from .errors import (
    AIOutputValidationError,
)
from .parsing import (
    _parse_llm_chunk,
)
from .types import (
    AiSummaryResult,
    ModelSequenceItem,
)

class PromptFlowMixin:
    """聊天记录→系统指令→模型序列重试→AI 摘要的生成流程。"""

    async def _collect_chatlog(self, talkers: List[str], time_window: dict, telemetry: Optional[dict] = None) -> str:
        return await chat_record_service.collect_messages(talkers, time_window, telemetry=telemetry)

    def _compose_prompt(self, prompt_template: str, system_instruction: str, chatlog_text: str) -> str:
        return f"聊天记录:\n{chatlog_text}\n\n{system_instruction}\n\n{prompt_template}"

    def _job_requires_html_output(self, job: Job) -> bool:
        return bool(getattr(job, "github_deploy_enabled", False) or getattr(job, "html_backup_enabled", False))

    def _resolve_model_sequence(self, db, task: Task) -> List[ModelSequenceItem]:
        raw_sequence = getattr(task, "model_sequence", None)
        items: list[dict[str, Any]] = []
        if raw_sequence:
            try:
                parsed = json.loads(raw_sequence) if isinstance(raw_sequence, str) else raw_sequence
                if isinstance(parsed, list):
                    items = [item for item in parsed if isinstance(item, dict)]
            except json.JSONDecodeError:
                items = []
        if not items and getattr(task, "model_id", None):
            items = [{"model_id": task.model_id, "max_attempts": 2}]
        sequence: List[ModelSequenceItem] = []
        for item in items:
            model_id = int(item.get("model_id") or 0)
            if model_id <= 0:
                continue
            model = db.query(Model).filter(Model.id == model_id).first()
            if not model:
                raise RuntimeError(f"模型不存在：{model_id}")
            max_attempts = max(int(item.get("max_attempts") or 2), 1)
            sequence.append(ModelSequenceItem(model=model, max_attempts=max_attempts))
        if not sequence:
            raise RuntimeError("任务未绑定模型")
        return sequence

    def _resolve_image_model_sequence(self, db, task: Task) -> List[ModelSequenceItem]:
        raw_sequence = getattr(task, "image_model_sequence", None)
        items: list[dict[str, Any]] = []
        if raw_sequence:
            try:
                parsed = json.loads(raw_sequence) if isinstance(raw_sequence, str) else raw_sequence
                if isinstance(parsed, list):
                    items = [item for item in parsed if isinstance(item, dict)]
            except json.JSONDecodeError:
                items = []
        if not items and getattr(task, "image_model_id", None):
            items = [{"model_id": task.image_model_id, "max_attempts": 2}]
        sequence: List[ModelSequenceItem] = []
        for item in items:
            model_id = int(item.get("model_id") or 0)
            if model_id <= 0:
                continue
            model = db.query(Model).filter(Model.id == model_id).first()
            if not model:
                raise RuntimeError(f"图片模型不存在：{model_id}")
            if (getattr(model, "model_type", "text") or "text") != "image":
                raise RuntimeError(f"所选模型不是图片模型：{model.provider}")
            max_attempts = max(int(item.get("max_attempts") or 2), 1)
            sequence.append(ModelSequenceItem(model=model, max_attempts=max_attempts))
        if not sequence:
            raise RuntimeError("任务未绑定图片模型")
        return sequence

    async def _generate_summary_with_model_sequence(
        self,
        *,
        db,
        task: Task,
        job: Job,
        talker_names: List[str],
        time_window: dict,
        chatlog_text: str,
        system_instruction_text: str,
        message_stats_result: Optional[message_stats_utils.MessageStats],
        html_required: bool,
        max_ai_requests: int,
        extra_prompt: str = "",
    ) -> AiSummaryResult:
        sequence = self._resolve_model_sequence(db, task)
        attempt_meta: list[dict[str, Any]] = []
        requests_used = 0
        last_error: Optional[Exception] = None
        for entry in sequence:
            model_attempts = 0
            while model_attempts < entry.max_attempts and requests_used < max_ai_requests:
                model_attempts += 1
                requests_used += 1
                model = entry.model
                try:
                    prompt = self._compose_prompt(task.prompt + extra_prompt, system_instruction_text, chatlog_text)
                    summary, prompt_tokens, completion_tokens = await self._invoke_llm(model, prompt)
                    prompt_meta = {
                        "chunked": False,
                        "system_instruction": system_instruction_text,
                    }
                    try:
                        self._validate_ai_output(
                            task=task,
                            job=job,
                            summary=summary,
                            html_required=html_required,
                        )
                    except Exception as exc:
                        raise AIOutputValidationError(str(exc), raw_summary=summary) from exc
                    attempt_meta.append(
                        {
                            "model_id": model.id,
                            "model_name": model.provider,
                            "attempt": model_attempts,
                            "status": "success",
                        }
                    )
                    prompt_meta["model_attempts"] = attempt_meta
                    prompt_meta["selected_model_id"] = model.id
                    prompt_meta["selected_model_name"] = model.provider
                    return AiSummaryResult(
                        summary=summary,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        model=model,
                        prompt_meta=prompt_meta,
                    )
                except Exception as exc:
                    last_error = exc
                    attempt_meta.append(
                        {
                            "model_id": getattr(entry.model, "id", None),
                            "model_name": getattr(entry.model, "provider", None),
                            "attempt": model_attempts,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    logger.warning(
                        "Job {} 模型 {} 第 {} 次 AI 请求失败（总请求 {}/{}）：{}",
                        job.id,
                        getattr(entry.model, "provider", None),
                        model_attempts,
                        requests_used,
                        max_ai_requests,
                        exc,
                    )
                    if requests_used >= max_ai_requests:
                        break
            if requests_used >= max_ai_requests:
                break
        if isinstance(last_error, AIOutputValidationError):
            raise AIOutputValidationError(
                f"AI 请求全部失败：{last_error}",
                raw_summary=last_error.raw_summary,
            ) from last_error
        raise RuntimeError(f"AI 请求全部失败：{last_error}") from last_error

    def _validate_ai_output(self, *, task: Task, job: Job, summary: str, html_required: bool) -> None:
        if getattr(task, "task_type", "report") == "topic_card":
            if image_card_service.BLOCK_START in summary:
                # 内容块格式（V5/V6 案例卡提示词）：话题卡片改走本地 HTML 引擎渲染，
                # 此处只校验内容块结构与槽位可解析性，不要求 JSON
                blocks = image_card_service.parse_content_blocks(summary, split_enabled=True, max_count=12)
                case_cards = html_case_card_service.parse_case_blocks(blocks)
                if not case_cards or not any(
                    card.facts or card.relations or card.analysis for card in case_cards
                ):
                    raise ValueError("内容块格式无法解析出案例卡：缺少槽位内容（背景概述/人物关系/分析过程等）")
                return
            style_config = topic_card_service.normalize_topic_style_config(getattr(task, "topic_style_config", None))
            topic_card_service.parse_topic_cards(summary, style_config=style_config)
            return
        if getattr(task, "task_type", "report") == "image_card":
            image_card_service.parse_content_blocks(
                summary,
                split_enabled=bool(getattr(job, "image_split_enabled", False)),
                max_count=max(int(getattr(job, "max_image_count", 6) or 6), 1),
            )
            return
        if html_required:
            self._extract_html_document(summary)

    def _build_system_instruction(
        self,
        task: Task,
        job: Job,
        talkers: List[str],
        time_window: dict,
        message_stats: Optional[message_stats_utils.MessageStats],
    ) -> str:
        default_prompt = (
            "请基于聊天记录，根据提示词完成任务。\n"
            f"时间范围: {time_window['time_str']}\n"
            f"群聊: {', '.join(talkers)}\n"
        )
        result = default_prompt
        if getattr(task, "system_prompt_custom_enabled", False):
            template = (getattr(task, "system_prompt_template", "") or "").strip()
            if template:
                replacements = {
                    "${time_range}": time_window.get("time_str", ""),
                    "${chatroom_name}": ", ".join(talkers),
                    "${message_count}": "",
                }
                if getattr(task, "system_prompt_include_message_count", False) and message_stats:
                    replacements["${message_count}"] = str(message_stats.total_messages)
                result = template
                for token, value in replacements.items():
                    result = result.replace(token, value)
        if getattr(task, "task_type", "report") == "image_card":
            image_rules: List[str] = []
            if bool(getattr(job, "image_split_enabled", False)):
                split_prompt = image_card_service.expand_split_prompt(getattr(job, "image_split_prompt", None))
                image_rules.append(f"图片内容拆分规则（必须遵守）：\n{split_prompt}")
            image_rules.append(
                f"图片卡片空内容规则（必须遵守）：\n{image_card_service.NO_IMAGE_CONTENT_INSTRUCTION}"
            )
            result = f"{result.rstrip()}\n\n" + "\n\n".join(image_rules)
        return result or default_prompt

    async def _invoke_llm(self, model, prompt: str) -> tuple[str, Optional[int], Optional[int]]:
        if not model:
            raise RuntimeError("任务未绑定模型")
        extra_payload = json.loads(model.extra) if model.extra else None
        result_chunks: List[str] = []
        prompt_tokens = None
        completion_tokens = None
        async for chunk in llm.stream_completion(model, prompt=prompt, extra_payload=extra_payload):
            text, prompt_tokens, completion_tokens = _parse_llm_chunk(
                chunk, prompt_tokens, completion_tokens
            )
            if text:
                result_chunks.append(text)

        summary = "".join(result_chunks).strip()
        if not summary:
            raise RuntimeError("模型返回为空")
        return summary, prompt_tokens, completion_tokens
