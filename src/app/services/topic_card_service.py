"""Topic card parsing, markdown rendering, and image rendering orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from loguru import logger

TopicTextLayout = Literal["per_topic", "merged", "auto"]
TopicImageLayout = Literal["single", "collection", "auto"]


DEFAULT_TOPIC_STYLE_CONFIG: dict[str, dict[str, str]] = {
    "industry_business": {"style_key": "style_a", "theme": "amber"},
    "work_methods": {"style_key": "style_b", "theme": "blue"},
    "career_growth": {"style_key": "style_c", "theme": "green"},
    "mind_wellbeing": {"style_key": "style_d", "theme": "neutral"},
}

VALID_STYLE_KEYS = {"style_a", "style_b", "style_c", "style_d"}
VALID_THEMES = {"amber", "blue", "green", "neutral"}

REQUIRED_FIELDS = {
    "topic_type",
    "tags",
    "time_range",
    "title",
    "initiator",
    "initiator_label",
    "trigger_quote",
    "summary",
    "points",
    "participants",
    "highlight_quote",
    "highlight_speaker",
}

@dataclass
class RenderedImage:
    path: Path
    width: int
    height: int
    size_bytes: int
    engine: str
    layout: str


def parse_topic_cards(raw: str, *, style_config: Any = None) -> list[dict[str, Any]]:
    data = _parse_json(_strip_json_fence(raw))
    cards = data.get("cards")
    if not isinstance(cards, list):
        raise ValueError("模型返回 JSON 缺少 cards 数组")
    resolved_style_config = normalize_topic_style_config(style_config)
    normalized = [_normalize_card(card, index, style_config=resolved_style_config) for index, card in enumerate(cards)]
    return normalized


def normalize_topic_style_config(value: Any = None) -> dict[str, dict[str, str]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = None
    source = value if isinstance(value, dict) else {}
    normalized: dict[str, dict[str, str]] = {}
    for topic_type, defaults in DEFAULT_TOPIC_STYLE_CONFIG.items():
        item = source.get(topic_type) if isinstance(source.get(topic_type), dict) else {}
        style_key = str(item.get("style_key") or defaults["style_key"]).strip()
        theme = str(item.get("theme") or defaults["theme"]).strip()
        normalized[topic_type] = {
            "style_key": style_key if style_key in VALID_STYLE_KEYS else defaults["style_key"],
            "theme": theme if theme in VALID_THEMES else defaults["theme"],
        }
    return normalized


def build_text_messages(cards: list[dict[str, Any]], *, layout: TopicTextLayout, threshold: int) -> list[str]:
    if not cards:
        return []
    resolved = _resolve_layout(layout, len(cards), threshold, single="per_topic", merged="merged")
    if resolved == "merged":
        return [_join_cards_markdown(cards)]
    return [_card_markdown(card) for card in cards]


def resolve_image_layout(layout: TopicImageLayout, card_count: int, threshold: int) -> Literal["single", "collection"]:
    return _resolve_layout(layout, card_count, threshold, single="single", merged="collection")


async def render_images(
    cards: list[dict[str, Any]],
    *,
    engine: str,
    layout: Literal["single", "collection"],
) -> list[RenderedImage]:
    if not cards:
        return []
    renderer_dir = _renderer_dir()
    script = renderer_dir / "render.mjs"
    if not script.exists():
        raise RuntimeError(f"话题卡片渲染脚本不存在：{script}")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 Node.js，无法生成话题卡片图片")

    with tempfile.TemporaryDirectory(prefix="topic-card-") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / "cards.json"
        output_dir = tmp_dir / "out"
        input_path.write_text(json.dumps({"cards": cards}, ensure_ascii=False), encoding="utf-8")
        cmd = [
            node,
            str(script),
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--engine",
            engine,
            "--layout",
            layout,
        ]
        logger.info("开始渲染话题卡片图片 engine={} layout={} cards={}", engine, layout, len(cards))
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=str(renderer_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"话题卡片图片渲染失败：{detail}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"话题卡片渲染器输出不是合法 JSON：{result.stdout[:300]}") from exc

        rendered: list[RenderedImage] = []
        for item in payload.get("images", []):
            source = Path(item["path"])
            if not source.exists():
                raise RuntimeError(f"渲染器返回的图片不存在：{source}")
            target = _copy_to_stable_temp_file(source)
            rendered.append(
                RenderedImage(
                    path=target,
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    size_bytes=target.stat().st_size,
                    engine=str(item.get("engine") or engine),
                    layout=str(item.get("layout") or layout),
                )
            )
        return rendered


def cleanup_images(images: Iterable[RenderedImage]) -> None:
    for image in images:
        try:
            image.path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("清理话题卡片临时图片失败 path={} error={}", image.path, exc)


def _renderer_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tools" / "topic-card-renderer"


def _copy_to_stable_temp_file(source: Path) -> Path:
    fd, target_name = tempfile.mkstemp(prefix="topic-card-", suffix=".png")
    os.close(fd)
    target = Path(target_name)
    try:
        shutil.copyfile(source, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError("模型返回 JSON 顶层必须是对象")
    return data


def _normalize_card(card: Any, index: int, *, style_config: dict[str, dict[str, str]]) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError(f"第 {index + 1} 张卡片不是对象")
    missing = [field for field in REQUIRED_FIELDS if field not in card]
    if missing:
        raise ValueError(f"第 {index + 1} 张卡片缺少字段：{', '.join(missing)}")
    points = card.get("points")
    participants = card.get("participants")
    if not isinstance(points, list) or not all(isinstance(item, str) for item in points):
        raise ValueError(f"第 {index + 1} 张卡片 points 必须是字符串数组")
    if not isinstance(participants, list) or not all(isinstance(item, str) for item in participants):
        raise ValueError(f"第 {index + 1} 张卡片 participants 必须是字符串数组")
    tags = _normalize_tags(card.get("tags"))
    topic_type = _resolve_topic_type(card, tags)
    style = style_config.get(topic_type) or DEFAULT_TOPIC_STYLE_CONFIG[topic_type]
    normalized_participants = [_clip(name, 24) for name in participants]
    if len(normalized_participants) > 16:
        normalized_participants = normalized_participants[:15] + ["等"]
    return {
        "id": str(card.get("id") or f"card-{index + 1:02d}"),
        "topic_type": topic_type,
        "style_key": style["style_key"],
        "theme": style["theme"],
        "tags": tags,
        "time_range": _clip(card.get("time_range"), 32),
        "title": _clip(card.get("title"), 60),
        "initiator": _clip(card.get("initiator"), 32),
        "initiator_label": _clip(card.get("initiator_label"), 16),
        "trigger_quote": _clip(card.get("trigger_quote"), 160),
        "summary": _clip(card.get("summary"), 260),
        "points": [_clip(point, 120) for point in points[:5]],
        "participants": normalized_participants,
        "highlight_quote": _clip(card.get("highlight_quote"), 180),
        "highlight_speaker": _clip(card.get("highlight_speaker"), 32),
        "section1_title": "抛出探讨",
        "highlight_label": "高光时刻",
    }


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_tags = value
    else:
        text = str(value or "").strip()
        raw_tags = [
            item.strip()
            for item in text.replace("，", "、").replace(",", "、").replace("/", "、").replace("|", "、").split("、")
        ]
    tags: list[str] = []
    for raw in raw_tags:
        tag = _clip(raw, 8)
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= 3:
            break
    return tags or ["职场观察"]


def _resolve_topic_type(card: dict[str, Any], tags: list[str]) -> str:
    """根据大类或短标签选择 V5 卡片样式；兜底走工作方法 Style B。"""
    raw_type = str(card.get("topic_type") or "").strip()
    type_aliases = {
        "industry_business": "industry_business",
        "行业商业": "industry_business",
        "行业分析": "industry_business",
        "work_methods": "work_methods",
        "工作方法": "work_methods",
        "方法工具": "work_methods",
        "career_growth": "career_growth",
        "求职发展": "career_growth",
        "职业发展": "career_growth",
        "mind_wellbeing": "mind_wellbeing",
        "心理认知": "mind_wellbeing",
        "状态认知": "mind_wellbeing",
        "认知状态": "mind_wellbeing",
    }
    if raw_type in type_aliases:
        return type_aliases[raw_type]

    title = str(card.get("title") or "").strip()
    text = f"{' '.join(tags)} {title}"

    topic_type_rules = [
        ("work_methods", ("工作方法", "工作效率", "向上管理", "沟通", "协作", "产品", "项目", "复盘", "工具", "AI", "汇报", "流程", "实操")),
        ("career_growth", ("求职", "面试", "简历", "Offer", "职业路径", "职业规划", "跳槽", "转型", "人际", "技能提升")),
        ("mind_wellbeing", ("心理", "健康", "精力", "情绪", "认知", "习惯", "成长", "压力", "内耗", "价值观")),
        ("industry_business", ("商业", "行业", "组织", "管理哲学", "组织管理", "趋势", "战略", "经营", "创业", "团队治理")),
    ]
    for resolved, keywords in topic_type_rules:
        if any(keyword in text for keyword in keywords):
            return resolved
    return "work_methods"


def _resolve_layout(layout: str, count: int, threshold: int, *, single: str, merged: str):
    if layout == "auto":
        return single if count <= max(1, threshold) else merged
    if layout in {single, merged}:
        return layout
    return single


def _join_cards_markdown(cards: list[dict[str, Any]]) -> str:
    return "\n\n---\n\n".join(_card_markdown(card) for card in cards)


def _card_markdown(card: dict[str, Any]) -> str:
    points = "\n".join(f"{index + 1}、{_with_at(point)}" for index, point in enumerate(card["points"]))
    participants = " ".join(_name_at(name) for name in card["participants"])
    speaker = _name_at(card["highlight_speaker"])
    return "\n".join(
        [
            f"### {_theme_dot(card['theme'])} {card['title']}",
            "",
            "**1、讨论时段：**",
            f"<font color='purple'>{card['time_range']}</font>",
            "",
            "**2、爬楼关键词：**",
            f"<font color='blue-700'>**{card['trigger_quote']}**</font>",
            "",
            "**3、发起人：**",
            _name_at(card["initiator"]),
            "",
            "**4、聊了什么：**",
            card["summary"],
            "",
            "**5、核心观点：**",
            points or "无",
            "",
            "**6、主要参与者：**",
            participants or "无",
            "",
            "**7、高光时刻：**",
            f"> {card['highlight_quote']}",
            f"> —— {speaker}",
        ]
    )


def _theme_dot(theme: str) -> str:
    return {
        "amber": "🟠",
        "blue": "🔵",
        "green": "🟢",
        "neutral": "🟣",
    }.get(theme, "🟣")


def _name_at(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return text if text.startswith("@") else f"@{text} "


def _with_at(point: str) -> str:
    text = str(point or "").strip()
    if " —— @" in text or "——@" in text:
        return text
    if " —— " in text:
        body, speaker = text.rsplit(" —— ", 1)
        return f"{body} —— {_name_at(speaker).strip()}"
    return text
