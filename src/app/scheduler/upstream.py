"""上游日报话题提取与注入（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..models.execution import Execution
from ..models.task import Task

from .common import (
    UPSTREAM_MAX_AGE_HOURS,
    UPSTREAM_MAX_TOPICS,
)

class UpstreamMixin:
    """卡片任务的纯日报内容模式与上游话题清单注入。"""

    def _load_upstream_report_content(self, db, task: Task) -> Tuple[str, Dict[str, Any]]:
        """纯日报内容模式：载入上游日报最近一次成功执行的话题全文，作为卡片任务的 LLM 输入。

        与标题注入不同，日报全文是该模式下模型的唯一事实来源，任何环节缺失都直接抛错
        （任务失败、不回退聊天记录）。
        """
        upstream_id = getattr(task, "upstream_task_id", None)
        if not upstream_id:
            raise ValueError("纯日报内容模式的卡片任务必须绑定上游日报任务")
        upstream_task = db.query(Task).filter(Task.id == int(upstream_id)).first()
        if not upstream_task:
            raise ValueError("纯日报内容模式绑定的上游日报任务不存在")
        execution = (
            db.query(Execution)
            .filter(
                Execution.task_id == upstream_task.id,
                Execution.status == "success",
                Execution.finished_at.isnot(None),
            )
            .order_by(Execution.finished_at.desc())
            .first()
        )
        if not execution:
            raise ValueError(f"上游日报任务「{upstream_task.name}」还没有成功生成的日报")
        finished_at = execution.finished_at
        age_hours = (datetime.now() - finished_at).total_seconds() / 3600 if finished_at else None
        if age_hours is None or age_hours > UPSTREAM_MAX_AGE_HOURS:
            raise ValueError(
                f"上游日报任务「{upstream_task.name}」最近一次成功日报已超过 {UPSTREAM_MAX_AGE_HOURS} 小时，"
                "纯日报内容模式拒绝执行"
            )
        sections = _extract_report_topic_sections(execution.summary_md or "")[:UPSTREAM_MAX_TOPICS]
        if not sections:
            raise ValueError(f"未能从上游日报任务「{upstream_task.name}」的输出中提取到话题内容")
        blocks = []
        for index, section in enumerate(sections, start=1):
            body = "\n".join(section["lines"]).strip()
            if body:
                blocks.append(f"### 话题{index}：{section['title']}\n{body}")
            else:
                blocks.append(f"### 话题{index}：{section['title']}")
        finished_text = finished_at.isoformat(sep=" ", timespec="minutes") if finished_at else ""
        content = (
            f"以下是漫道日报（任务「{upstream_task.name}」，生成于 {finished_text}）中 "
            f"{len(sections)} 个深度话题的完整内容，按日报中的顺序排列。\n\n" + "\n\n".join(blocks)
        )
        meta = {
            "mode": "report_content",
            "upstream_task_id": int(upstream_id),
            "upstream_execution_id": execution.id,
            "upstream_finished_at": finished_at.isoformat(sep=" ", timespec="minutes") if finished_at else None,
            "injected": True,
            "topics": [section["title"] for section in sections],
            "topic_count": len(sections),
        }
        return content, meta

    def _build_upstream_topic_injection(self, db, task: Task) -> Tuple[str, Optional[Dict[str, Any]]]:
        """查询上游日报任务最近一次成功执行，产出话题清单提示词后缀与元信息。

        返回 (suffix, meta)：查不到合格上游时 suffix 为空串、meta 记录原因，
        卡片任务随之自然回退为提示词中的「自行选题」分支。
        """
        if getattr(task, "task_type", "report") not in ("topic_card", "image_card"):
            return "", None
        upstream_id = getattr(task, "upstream_task_id", None)
        if not upstream_id:
            return "", None
        meta: Dict[str, Any] = {"upstream_task_id": int(upstream_id)}
        upstream_task = db.query(Task).filter(Task.id == int(upstream_id)).first()
        if not upstream_task:
            meta.update({"injected": False, "reason": "上游日报任务不存在"})
            return "", meta
        execution = (
            db.query(Execution)
            .filter(
                Execution.task_id == upstream_task.id,
                Execution.status == "success",
                Execution.finished_at.isnot(None),
            )
            .order_by(Execution.finished_at.desc())
            .first()
        )
        if not execution:
            meta.update({"injected": False, "reason": "上游任务还没有成功完成的日报"})
            return "", meta
        finished_at = execution.finished_at
        meta["upstream_execution_id"] = execution.id
        meta["upstream_finished_at"] = finished_at.isoformat(sep=" ", timespec="minutes") if finished_at else None
        age_hours = (datetime.now() - finished_at).total_seconds() / 3600 if finished_at else None
        if age_hours is None or age_hours > UPSTREAM_MAX_AGE_HOURS:
            meta.update({"injected": False, "reason": f"最近一次成功日报已超过 {UPSTREAM_MAX_AGE_HOURS} 小时，不注入"})
            return "", meta
        titles = _extract_report_topic_titles(execution.summary_md or "")
        if not titles:
            meta.update({"injected": False, "reason": "未能从上游日报中提取到话题标题"})
            return "", meta
        meta.update({"injected": True, "topics": titles, "topic_count": len(titles)})
        numbered = "\n".join(f"{index}. {title}" for index, title in enumerate(titles, start=1))
        suffix = (
            "\n\n## 日报话题清单（系统自动注入，本次视为「已提供日报话题清单」）\n\n"
            f"来源：任务「{upstream_task.name}」于 {meta['upstream_finished_at']} 成功生成的漫道日报，"
            f"共 {len(titles)} 个深度话题，按日报中的顺序排列：\n"
            f"{numbered}\n\n"
            "本次必须按上方「第零步」执行：案例卡片与该清单一一对应，"
            "话题数量、顺序、标题完全一致，不得增删、合并、拆分或另选话题。"
        )
        return suffix, meta



_TOPIC_HEADING_TAGS = ("h2", "h3", "h4")


def _resolve_card_input_source(task: Task) -> str:
    """卡片任务输入来源：report=纯日报内容模式，其余（含缺失/非法值）一律回落聊天记录模式。"""
    source = (getattr(task, "card_input_source", None) or "chatlog").strip()
    return "report" if source == "report" else "chatlog"


def _extract_report_topic_titles(summary: str) -> List[str]:
    """从上游日报输出中提取深度话题标题：HTML 日报取 h4（buildToc 目录同源），markdown 标题兜底。"""
    if not summary:
        return []
    titles: List[str] = []
    for raw in re.findall(r"<h4[^>]*>(.*?)</h4>", summary, flags=re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", raw)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            titles.append(text)
    if not titles:
        for line in summary.splitlines():
            match = re.match(r"^#{3,4}\s+(.+?)\s*$", line)
            if not match:
                continue
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text:
                titles.append(text)
    deduped: List[str] = []
    for title in titles:
        if title not in deduped:
            deduped.append(title)
    return deduped[:UPSTREAM_MAX_TOPICS]


def _extract_report_topic_sections(summary: str) -> List[Dict[str, Any]]:
    """从上游日报输出中提取深度话题的标题与正文（纯日报内容模式的输入）。

    HTML 日报按 h4 切分话题、逐块转纯文本；markdown 日报按 ###/#### 标题兜底。
    返回 [{"title": str, "lines": List[str]}]，提取不到时返回空列表。
    """
    if not summary:
        return []
    if "<h4" in summary.lower():
        sections = _extract_topic_sections_from_html(summary)
        if sections:
            return sections
    return _extract_topic_sections_from_markdown(summary)


def _extract_topic_sections_from_html(summary: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(summary, "html5lib")
    headings = soup.find_all(list(_TOPIC_HEADING_TAGS))
    if not headings:
        return []
    # 定位「职通时刻・深度话题」栏目（栏目标题可能是 h2 或 h3），只取该栏目内的 h4；
    # 找不到栏目时退回全部 h4（与标题提取同源）
    topic_heads: List[Any] = []
    scope_index: Optional[int] = None
    for index, el in enumerate(headings):
        if el.name in ("h2", "h3"):
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if "深度话题" in text or "职通时刻" in text:
                scope_index = index
                break
    if scope_index is None:
        topic_heads = [el for el in headings if el.name == "h4"]
    else:
        for el in headings[scope_index + 1 :]:
            if el.name in ("h2", "h3"):
                break
            if el.name == "h4":
                topic_heads.append(el)
    sections: List[Dict[str, Any]] = []
    for head in topic_heads:
        title = re.sub(r"\s+", " ", head.get_text(" ", strip=True)).strip()
        sections.append({"title": title, "lines": _html_topic_body_lines(head)})
    return [s for s in sections if s["title"] or s["lines"]]


def _html_topic_body_lines(head: Any) -> List[str]:
    """收集一个 h4 话题标题到下一个标题之间的正文，按块级元素转成文本行。"""
    lines: List[str] = []
    for el in head.next_elements:
        name = getattr(el, "name", None)
        if name in _TOPIC_HEADING_TAGS:
            break
        if not name:
            continue
        if name == "div":
            cls = " ".join(el.get("class") or [])
            if "content-preview" in cls or "content-full" in cls:
                # 日报「详细内容」正文没有 p/li 结构，用 <b>/<br> 组织，按 <br> 断行提取
                inner = re.sub(r"<br\s*/?>", "\n", el.decode_contents(), flags=re.IGNORECASE)
                for chunk in inner.split("\n"):
                    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)).strip()
                    if text and text not in lines:
                        lines.append(text)
            continue
        if name not in ("p", "li", "blockquote", "h5"):
            continue
        if name == "p" and el.find_parent("blockquote"):
            # blockquote 整体捕获，跳过其内部段落避免重复
            continue
        if name == "li" and el.find_parent("li"):
            # 嵌套列表只保留最外层条目
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not text:
            continue
        prefix = ""
        if name == "li":
            prefix = "- "
        elif name == "blockquote":
            prefix = "> "
        line = prefix + text
        if line not in lines:
            lines.append(line)
    return lines


def _extract_topic_sections_from_markdown(summary: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw in summary.splitlines():
        match = re.match(r"^(#{2,6})\s+(.+?)\s*$", raw)
        if match:
            level = len(match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if level <= 2:
                # 栏目标题：离开当前栏目
                current = None
                continue
            # 与标题提取同源：###/#### 都视为话题标题
            current = {"title": title, "lines": []}
            sections.append(current)
            continue
        if current is not None and raw.strip():
            current["lines"].append(raw.strip())
    return [s for s in sections if s["title"] or s["lines"]]
