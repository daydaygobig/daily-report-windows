"""模块级解析/格式化工具函数（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from zoneinfo import ZoneInfo

from ..models.job import Job
from ..services import image_card_service


def _time_str_to_minutes(value: str) -> int:
    try:
        hour_str, minute_str = value.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError):
        raise ValueError(f"invalid time format: {value}") from None
    if hour == 24 and minute == 0:
        return 24 * 60
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour * 60 + minute
    raise ValueError(f"invalid time value: {value}")


def _combine_date_minutes(base_date: date, minutes: int, tz: ZoneInfo) -> datetime:
    anchor = datetime(base_date.year, base_date.month, base_date.day, tzinfo=tz)
    return anchor + timedelta(minutes=minutes)


def _load_weekdays(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    result: List[int] = []
    for item in value:
        try:
            val = int(item)
        except (TypeError, ValueError):
            continue
        result.append(val)
    return result


def _filter_cards_by_topic(cards: List[Dict[str, Any]], selected_topic: str) -> List[Dict[str, Any]]:
    """按话题标题（包含匹配，忽略大小写）或 1 起始序号筛选卡片。"""
    stripped = selected_topic.strip()
    if stripped.isdigit():
        index = int(stripped)
        if 1 <= index <= len(cards):
            return [cards[index - 1]]
    keyword = stripped.lower()
    return [
        card
        for card in cards
        if keyword in str(card.get("title") or "").strip().lower()
    ]


def _filter_case_cards_by_topic(case_cards: List[Any], selected_topic: str) -> List[Any]:
    """按 1 起始序号或标题关键词（包含匹配，忽略大小写）筛选案例卡。

    序号对应解析后的案例卡顺序（单卡模式：一个内容块=一张卡）。
    """
    stripped = selected_topic.strip()
    if stripped.isdigit():
        index = int(stripped)
        if 1 <= index <= len(case_cards):
            return [case_cards[index - 1]]
    keyword = stripped.lower()
    return [
        card
        for card in case_cards
        if keyword in str(getattr(card, "title", "") or "").strip().lower()
    ]


def _select_image_blocks(
    blocks: List[str], selected_topic: str, *, job: Job
) -> List[str]:
    """按序号（1 起始的内容块序号）或关键词筛选内容块（单卡模式：一块=一话题=一张卡）。"""
    stripped = selected_topic.strip()
    if stripped.isdigit():
        index = int(stripped)
        if not 1 <= index <= len(blocks):
            return []
        matched_blocks = {index}
    else:
        keyword = stripped.lower()
        matched_blocks = {
            index
            for index, block in enumerate(blocks, start=1)
            if keyword in block.lower()
        }
        if not matched_blocks:
            return []
    return [block for index, block in enumerate(blocks, start=1) if index in matched_blocks]


def _parse_int_list(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [int(item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _parse_str_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _is_weekly_report(job: Job) -> bool:
    return getattr(job, "schedule_type", "") == "weekly_report"


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "report.html"


def _strip_markdown_fence(content: str) -> str:
    if not content:
        return content
    trimmed = content.strip()
    if not trimmed.startswith("```"):
        return content
    lines = trimmed.splitlines()
    if len(lines) < 2:
        return trimmed
    closing_idx = len(lines) - 1
    while closing_idx > 0 and not lines[closing_idx].strip():
        closing_idx -= 1
    if not lines[0].strip().startswith("```") or not lines[closing_idx].strip().startswith("```"):
        return trimmed
    inner = "\n".join(lines[1:closing_idx]).strip()
    return inner or trimmed


def _parse_llm_chunk(chunk: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> tuple[str, Optional[int], Optional[int]]:
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        return chunk, prompt_tokens, completion_tokens

    text = ""
    if "choices" in data and data["choices"]:
        delta = data["choices"][0].get("delta", {})
        text = delta.get("content", "")
        usage = data.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
            completion_tokens = usage.get("completion_tokens", completion_tokens)
    return text, prompt_tokens, completion_tokens
