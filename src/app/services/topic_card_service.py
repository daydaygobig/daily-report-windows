"""Topic card parsing, markdown rendering, and image rendering orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import re
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
    page_count: int = 0   # 本地 HTML 引擎：小红书 3:4 分页数量（0=无分页）


def parse_topic_cards(raw: str, *, style_config: Any = None) -> list[dict[str, Any]]:
    data = _parse_json(_strip_json_fence(raw))
    cards = data.get("cards")
    if not isinstance(cards, list):
        raise ValueError("模型返回 JSON 缺少 cards 数组")
    resolved_style_config = normalize_topic_style_config(style_config)
    normalized = [_normalize_any_card(card, index, style_config=resolved_style_config) for index, card in enumerate(cards)]
    return normalized


def _normalize_any_card(card: Any, index: int, *, style_config: dict[str, dict[str, str]]) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError(f"第 {index + 1} 张卡片不是对象")
    fmt = str(card.get("card_format") or "").strip().lower()
    if fmt == "case":
        return _normalize_case_card(card, index, style_config=style_config)
    if not fmt and "summary" not in card and ("background" in card or "relationship" in card):
        # 模型漏写 card_format 时按字段特征兜底识别案例格式
        return _normalize_case_card(card, index, style_config=style_config)
    return _normalize_card(card, index, style_config=style_config)


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
        "participants": _normalize_participants(participants),
        "highlight_quote": _clip(card.get("highlight_quote"), 180),
        "highlight_speaker": _clip(card.get("highlight_speaker"), 32),
        "section1_title": "抛出探讨",
        "highlight_label": "高光时刻",
    }


def _normalize_case_card(card: Any, index: int, *, style_config: dict[str, dict[str, str]]) -> dict[str, Any]:
    """案例卡片（六槽位：一句话问题/背景概述/人物关系/分析过程/解决方案/金句）。"""
    required = (
        "title",
        "trigger_quote",
        "background",
        "relationship",
        "analysis",
        "solution",
        "highlight_quote",
        "highlight_speaker",
    )
    missing = [field for field in required if field not in card]
    if missing:
        raise ValueError(f"第 {index + 1} 张案例卡片缺少字段：{', '.join(missing)}")
    analysis = card.get("analysis")
    participants = card.get("participants") or []
    if not isinstance(analysis, list) or not all(isinstance(item, str) for item in analysis):
        raise ValueError(f"第 {index + 1} 张案例卡片 analysis 必须是字符串数组")
    if not isinstance(participants, list) or not all(isinstance(item, str) for item in participants):
        raise ValueError(f"第 {index + 1} 张案例卡片 participants 必须是字符串数组")
    tags = _normalize_tags(card.get("tags"))
    topic_type = _resolve_topic_type(card, tags)
    style = style_config.get(topic_type) or DEFAULT_TOPIC_STYLE_CONFIG[topic_type]
    # 人物姓名/昵称统一脱敏：只保留第一个字符，其余用「某」代替（含网名 ID），
    # 覆盖当事人、参与者、金句署名在正文中的所有出现位置
    raw_initiator = _clip(card.get("initiator"), 32)
    known_names = [raw_initiator, *_normalize_participants(participants), _clip(card.get("highlight_speaker"), 32)]
    masks = _build_name_masks(known_names)

    def _masked(value: Any, limit: int) -> str:
        return _clip(_apply_name_masks(value, masks), limit)

    initiator = dict(masks).get(raw_initiator, raw_initiator)
    background = _masked(card.get("background"), 220)
    relationship = _masked(card.get("relationship"), 240)
    # 截断上限对齐案例卡实际水位：分析 3~5 条、每条 150 字；解决方案 240 字
    analysis_points = [_masked(point, 150) for point in analysis[:5]]
    solution = _masked(card.get("solution"), 240)
    # summary/points 由槽位拼出，保证旧渲染引擎与旧展示路径仍可用
    summary = background if not relationship else f"{background}\n人物关系：{relationship}"
    points = analysis_points + [solution]
    return {
        "id": str(card.get("id") or f"card-{index + 1:02d}"),
        "card_format": "case",
        "topic_type": topic_type,
        "style_key": style["style_key"],
        "theme": style["theme"],
        "tags": tags,
        "time_range": _clip(card.get("time_range"), 32),
        "title": _clip(card.get("title"), 60),
        "initiator": initiator,
        "initiator_label": _clip(card.get("initiator_label") or "当事人", 16),
        "trigger_quote": _masked(card.get("trigger_quote"), 160),
        "summary": summary,
        "background": background,
        "relationship": relationship,
        "analysis": analysis_points,
        "solution": solution,
        "points": points,
        "participants": [_masked(name, 24) for name in _normalize_participants(participants)],
        "highlight_quote": _masked(card.get("highlight_quote"), 180),
        "highlight_speaker": _masked(card.get("highlight_speaker"), 32),
        "section1_title": "抛出探讨",
        "highlight_label": "金句",
    }


def _normalize_participants(participants: list[str]) -> list[str]:
    normalized = [_clip(name, 24) for name in participants]
    if len(normalized) > 16:
        normalized = normalized[:15] + ["等"]
    return normalized


COMPOUND_SURNAMES = (
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫", "万俟", "闻人",
    "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台", "皇甫", "宗政", "濮阳", "公冶",
    "太叔", "申屠", "公孙", "慕容", "仲孙", "钟离", "长孙", "鲜于", "宇文", "司徒",
    "司空", "令狐", "西门", "南门", "百里", "东郭", "呼延",
)


def _mask_person_name(name: str) -> str:
    """姓名/昵称脱敏：只保留第一个字符，其余用「某」代替。

    苏云→苏某，欧阳晨→欧阳某；网名 ID 一并处理：Cici_→C某，阿南plus→阿某。
    """
    text = str(name or "").strip().lstrip("@").strip()
    if not text or len(text) <= 1:
        return text
    for surname in COMPOUND_SURNAMES:
        if text.startswith(surname) and len(text) > len(surname):
            return f"{surname}某"
    return f"{text[0]}某"


# 群友A、网友1 这类泛称本身已匿名，保留原样以便区分多个来源
_GENERIC_NAME_PATTERN = re.compile(r"^(?:群友|网友)[0-9A-Za-z]{0,3}$")

# 提示词「匿名化规则」分发的固定化名属于已匿名名称，脱敏时必须原样保留，
# 否则张三→张某会把模型已完成的化名替换再打码一遍
_ANONYMOUS_ALIAS_NAMES = frozenset({
    "张三", "李四", "王二麻子", "赵五", "钱六", "孙七", "周八", "吴九",
    "郑十", "刘十一", "陈十二", "杨十三", "黄十四", "徐十五", "胡十六", "朱十七",
})


def _maybe_mask_name(name: str) -> str:
    text = str(name or "").strip().lstrip("@").strip()
    if _GENERIC_NAME_PATTERN.fullmatch(text) or text in _ANONYMOUS_ALIAS_NAMES:
        return text
    return _mask_person_name(text)


def _build_name_masks(names: Iterable[str]) -> list[tuple[str, str]]:
    """构建 姓名/昵称→脱敏名 映射，按名字长度降序替换，避免短名先替换破坏长名匹配。"""
    masks: dict[str, str] = {}
    for name in names:
        text = str(name or "").strip().lstrip("@").strip()
        if not text or text in masks:
            continue
        masked = _maybe_mask_name(text)
        if masked != text:
            masks[text] = masked
    return sorted(masks.items(), key=lambda item: len(item[0]), reverse=True)


def _apply_name_masks(text: Any, masks: list[tuple[str, str]]) -> str:
    """把文本中出现过的人物名字替换为脱敏形式（含 @ 提及）。"""
    body = str(text or "")
    for raw, masked in masks:
        body = body.replace(f"@{raw}", f"@{masked}").replace(raw, masked)
    return body


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
    if card.get("card_format") == "case":
        return _case_card_markdown(card)
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


def _case_card_markdown(card: dict[str, Any]) -> str:
    analysis = "\n".join(f"{index + 1}、{_with_at(point)}" for index, point in enumerate(card["analysis"]))
    speaker = _name_at(card["highlight_speaker"])
    tags = "、".join(card.get("tags") or [])
    lines = [
        f"### {_theme_dot(card['theme'])} {card['title']}",
        "",
    ]
    if tags:
        lines.append(f"**关键词：**{tags}")
        lines.append("")
    lines.extend(
        [
            "**背景概述：**",
            card["background"],
            "",
            "**人物关系：**",
            card["relationship"],
            "",
            "**分析过程：**",
            analysis or "无",
            "",
            "**解决方案：**",
            card["solution"],
            "",
            "**金句：**",
            f"> {card['highlight_quote']}",
            f"> —— {speaker}",
        ]
    )
    return "\n".join(lines)


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
