"""本地 HTML 案例卡引擎：把 image_card 任务的 CONTENT_BLOCK 文案渲染成零错别字长图。

链路：单卡文案块（一个内容块=一张完整卡） -> 解析成结构化数据 -> 注入 HTML 模板
-> Edge 无头截图 -> PNG。文字由浏览器字体引擎渲染，从机制上消除生图模型的错别字。

设计要点：
- 每个话题一张完整长卡（上卡模块 + 下卡模块一气呵成），固定宽 1080、高度随内容自适应；
- 人物关系图为自动布局的网络图，画型按 html画图PROMPT V1 的 A 组规则选型：
  双方对峙（两方对垒，左右对射、压制粗实线/反弹灰虚线）、组织层级树（〔层级〕标记，
  权力越大越靠上描边越粗、当事人高亮）、多方群像（默认：当事人居中 + 卫星环绕），
  自动布局不完美时可直接手改 card.html 后用 CLI 重渲染，生成器不会覆盖手改内容；
- HTML / card_data.json / PNG 持久化到 settings.html_card_output_dir，便于人工修正与排查；
- 二维码在页脚内直接排版生成（qrcode 库），无需事后叠加。
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from loguru import logger

from ..config import get_settings

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CARD_WIDTH = 1080          # 设计宽度（CSS 像素）
# 关系图画布宽：面板内容区 = 卡片宽 - 左右 body padding(48×2) - 面板边框(3×2) - 面板内边距(8×2)。
# 画布取内容区宽度，贴边元素才不会压在面板边框上。
DIAGRAM_CANVAS_W = CARD_WIDTH - 118
SENTINEL_COLOR = (255, 0, 255)  # 高度哨兵条颜色，渲染后裁掉

# 无形角色启发式关键词：命中即用虚线框节点表达（制度/规律/利益/心理等无形之物）
GHOST_KEYWORDS = (
    "合同", "制度", "规律", "惯例", "成本", "规则", "机制", "流程", "话术",
    "表情包", "赔偿", "奖金", "年终", "责任心", "情绪", "心态", "焦虑", "幻觉", "画饼",
)

_EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


@dataclass
class RelationEdge:
    source: str
    verb: str
    target: str
    why: str = ""


@dataclass
class CaseCard:
    """一个话题的完整案例卡数据（上卡 + 下卡合并）。"""

    title: str = ""
    subtitle: str = ""
    keywords: list[str] = field(default_factory=list)
    gender: str = "男"
    facts: list[tuple[str, str]] = field(default_factory=list)      # (标签, 内容)
    scenes: list[str] = field(default_factory=list)
    question: str = ""
    relations: list[RelationEdge] = field(default_factory=list)
    relation_summary: str = ""
    topology: str = ""            # 关系图拓扑标记：对峙/层级；空=多方群像（默认）
    analysis: list[tuple[str, str]] = field(default_factory=list)   # (标签, 正文)
    solutions: list[tuple[str, str]] = field(default_factory=list)
    quotes: list[tuple[str, str]] = field(default_factory=list)     # (金句, 署名)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "subtitle": self.subtitle, "keywords": self.keywords,
            "gender": self.gender,
            "facts": [list(item) for item in self.facts],
            "scenes": self.scenes, "question": self.question,
            "relations": [
                {"source": r.source, "verb": r.verb, "target": r.target, "why": r.why}
                for r in self.relations
            ],
            "relation_summary": self.relation_summary,
            "topology": self.topology,
            "analysis": [list(item) for item in self.analysis],
            "solutions": [list(item) for item in self.solutions],
            "quotes": [list(item) for item in self.quotes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseCard":
        return cls(
            title=data.get("title", ""), subtitle=data.get("subtitle", ""),
            keywords=list(data.get("keywords", [])), gender=data.get("gender", "男"),
            facts=[(str(a), str(b)) for a, b in data.get("facts", [])],
            scenes=list(data.get("scenes", [])), question=data.get("question", ""),
            relations=[
                RelationEdge(r.get("source", ""), r.get("verb", ""), r.get("target", ""), r.get("why", ""))
                for r in data.get("relations", [])
            ],
            relation_summary=data.get("relation_summary", ""),
            topology=data.get("topology", ""),
            analysis=[(str(a), str(b)) for a, b in data.get("analysis", [])],
            solutions=[(str(a), str(b)) for a, b in data.get("solutions", [])],
            quotes=[(str(a), str(b)) for a, b in data.get("quotes", [])],
        )


@dataclass
class RenderedCard:
    html_path: Path
    png_path: Path
    data_path: Path
    width: int
    height: int
    relation_model: str = ""      # 关系图实际由哪个模型画出（空=SVG 渲染）


# ---------------------------------------------------------------------------
# 一、V5 文案块解析
# ---------------------------------------------------------------------------

_SECTION_HEADERS = ("关键词：", "关键词:", "背景概述：", "背景概述:", "人物关系：", "人物关系:",
                    "分析过程：", "分析过程:", "解决方案：", "解决方案:", "金句：", "金句:")

_RE_IP_ROLE = re.compile(r"^IP角色[:：]\s*(男|女)")
_RE_FACT = re.compile(r"^([^｜|]{1,12})[｜|](.+)$")
_RE_NUMBERED = re.compile(r"^\d+\s*[、.．]\s*[『「'\"]?(.+?)[』」'\"]?\s*[:：]\s*(.+)$")
_RE_EDGE_FWD = re.compile(
    r"^(?P<a>.+?)\s*[-—–]{1,4}\s*[（(](?P<v>.+?)[)）]\s*(?:->|→|⟶|-{0,3}>)\s*(?P<b>.+?)\s*(?:[:：](?P<w>.+))?$"
)
_RE_EDGE_REV = re.compile(
    r"^(?P<a>.+?)\s*(?:<-|←)\s*[-—–]+\s*[（(](?P<v>.+?)[)）]\s*[-—–]+\s*(?P<b>.+?)\s*(?:[:：](?P<w>.+))?$"
)
# 「整体结构：〔对峙〕xxx」里的可选拓扑标记，渲染时切换关系图图型
_RE_TOPOLOGY_MARKER = re.compile(r"^(整体结构[：:])\s*[〔\[【]?\s*(双方对峙|对峙|层级树|层级|树|群像)\s*[〕\]】]?\s*(.*)$")

_TOPOLOGY_ALIASES = {
    "对峙": "对峙", "双方对峙": "对峙",
    "层级": "层级", "层级树": "层级", "树": "层级",
    "群像": "",  # 多方群像是默认图型，标记等价于不标
}


def _split_topology_marker(line: str) -> tuple[str, str]:
    """从「整体结构」行剥离拓扑标记，返回 (干净摘要行, 拓扑)。"""
    match = _RE_TOPOLOGY_MARKER.match(line.strip())
    if not match:
        return line.strip(), ""
    topology = _TOPOLOGY_ALIASES.get(match.group(2), "")
    rest = match.group(3).strip()
    summary = f"{match.group(1)}{rest}" if rest else match.group(1).rstrip("：:")
    return summary, topology


def _lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines()]


def _is_header(line: str) -> Optional[str]:
    for header in _SECTION_HEADERS:
        if line.startswith(header):
            return header.rstrip("：:")
    return None


def parse_case_blocks(blocks: list[str]) -> list[CaseCard]:
    """把 CONTENT_BLOCK 列表解析成案例卡。单卡模式：一个内容块 = 一张完整卡。

    历史数据里可能仍带【拼卡·上/下】标记，strip_block_markers 会剥掉后尽力解析。
    """
    cards = [ _parse_one_card(strip_block_markers(block), "") for block in blocks ]
    return [card for card in cards if _card_is_valid(card)]


def strip_block_markers(block: str) -> str:
    text = re.sub(r"<!--\s*CONTENT_BLOCK_(START|END)\s*-->", "", block or "")
    lines = [ln for ln in _lines(text) if ln not in ("【拼卡·上】", "【拼卡·下】")]
    return "\n".join(lines)


def _card_is_valid(card: CaseCard) -> bool:
    return bool(card.title or card.facts or card.analysis)


def _parse_one_card(top_text: str, bottom_text: str) -> CaseCard:
    card = CaseCard()
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    preamble: list[str] = []

    for line in _lines(top_text):
        if _RE_IP_ROLE.match(line):
            card.gender = _RE_IP_ROLE.match(line).group(1)  # type: ignore[union-attr]
            continue
        header = _is_header(line)
        if header:
            current = header
            sections.setdefault(current, [])
            rest = line[len(header) + 1:].strip()
            if rest:
                sections[current].append(rest)
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)

    # 前导区：标题、副标题（关键词行之前的前两行）
    preamble = [ln for ln in preamble if ln]
    if preamble:
        card.title = preamble[0]
    if len(preamble) > 1:
        card.subtitle = preamble[1]
    card.keywords = [
        tag.strip() for tag in re.split(r"[、,，/|]", ",".join(sections.get("关键词", []))) if tag.strip()
    ][:3]

    # 背景概述：含｜的行为事实字段；以？结尾的为入局问句；其余为场景叙述
    for line in sections.get("背景概述", []):
        if not line:
            continue
        match = _RE_FACT.match(line)
        if match:
            card.facts.append((match.group(1).strip(), match.group(2).strip()))
        elif line.endswith("？") or line.endswith("?"):
            card.question = line
        else:
            card.scenes.append(line)

    # 人物关系
    for line in sections.get("人物关系", []):
        if not line:
            continue
        if line.startswith("整体结构"):
            card.relation_summary, card.topology = _split_topology_marker(line)
            continue
        edge = _parse_relation_line(line)
        if edge:
            card.relations.append(edge)

    # 下卡
    current = None
    for line in _lines(bottom_text):
        header = _is_header(line)
        if header in ("分析过程", "解决方案", "金句"):
            current = header
            sections.setdefault(current, [])
            rest = line[len(header) + 1:].strip()
            if rest:
                sections[current].append(rest)
            continue
        if header:
            current = None
            continue
        if current:
            sections.setdefault(current, []).append(line)

    for line in sections.get("分析过程", []):
        match = _RE_NUMBERED.match(line)
        if match:
            card.analysis.append((match.group(1).strip(), match.group(2).strip()))
    for line in sections.get("解决方案", []):
        match = _RE_NUMBERED.match(line)
        if match:
            card.solutions.append((match.group(1).strip(), match.group(2).strip()))

    quote_lines = sections.get("金句", [])
    i = 0
    while i < len(quote_lines):
        line = quote_lines[i]
        if not line:
            i += 1
            continue
        quote = line
        sig = ""
        if i + 1 < len(quote_lines) and re.match(r"^[—\-–]{1,4}\s*", quote_lines[i + 1]):
            sig = re.sub(r"^[—\-–]{1,4}\s*", "", quote_lines[i + 1]).strip()
            i += 2
        else:
            i += 1
        if quote:
            card.quotes.append((quote, sig))

    return card


def _parse_relation_line(line: str) -> Optional[RelationEdge]:
    text = line.strip()
    match = _RE_EDGE_FWD.match(text)
    if match:
        return RelationEdge(match.group("a").strip(), match.group("v").strip(),
                            match.group("b").strip(), (match.group("w") or "").strip())
    match = _RE_EDGE_REV.match(text)
    if match:
        # A ←—(v)— B：B 对 A 施加 v，箭头方向 B -> A
        return RelationEdge(match.group("b").strip(), match.group("v").strip(),
                            match.group("a").strip(), (match.group("w") or "").strip())
    return None


# ---------------------------------------------------------------------------
# 二、人物关系图自动布局
# ---------------------------------------------------------------------------

def _is_ghost(name: str) -> bool:
    return any(keyword in name for keyword in GHOST_KEYWORDS)


def _node_size(name: str, why: str, font_scale: float = 1.0) -> tuple[int, int]:
    """按文字长度估算节点框尺寸（宽，最小高），度量对齐 .dg-node 的真实 CSS：

    内容宽 = 宽 - 边框3×2 - 内边距20×2；节点名 44px/行（行高约1.4），
    说明 36px×1.45/行外加 margin-top 8；高度另留 8% 渲染余量。
    绝对定位的行距与标签防碰撞都依赖这个估算，宁高勿矮。
    font_scale 为「超界自动缩字」档位（边框不缩放，其余度量等比缩）。
    """
    name_px = 44 * font_scale
    name_width = max(_display_width(name) * name_px, 200 * font_scale) + 56 * font_scale
    width = min(max(name_width, 300 * font_scale), 420 * font_scale)
    inner = width - (6 + 40 * font_scale)
    name_lines = max(1, -(-int(_display_width(name) * name_px) // int(inner)))
    height = 6 + 28 * font_scale + name_lines * 62 * font_scale
    if why:
        why_lines = max(1, -(-int(_display_width(why) * 36 * font_scale) // int(inner)))
        height += (8 + why_lines * 53) * font_scale
    return int(width), int(max(height * 1.08, 175 * font_scale))


def _display_width(text: str) -> int:
    """CJK 记 1，半角记 0.55，向上取整。"""
    total = 0.0
    for char in text:
        total += 1.0 if unicodedata.east_asian_width(char) in ("W", "F") else 0.55
    return int(total + 0.999)


_INK = "#1A1A1A"   # 主线：压向当事人 / 当事人行动
_SOFT = "#6B655C"  # 弱线：反弹觉醒 / 无形约束（虚线）
_REBOUND_VERBS = ("拒绝", "反击", "反制", "反弹", "觉醒", "摊牌", "掀桌",
                  "硬刚", "叫板", "反将", "翻脸", "不忍了", "不伺候")

# 组织层级树的职级分层：数字越小权力越大、行越靠上
_TREE_RANKS: tuple[tuple[str, int], ...] = (
    (r"老板|总裁|董事长|创始人|大老板|总经理|CEO|Owner", 0),
    (r"副总|总监|VP|事业部", 1),
    (r"经理|主管|主任|部长|科长|组长|领导|上级|\+1|\+2|HR|人事|医务科|财务|行政|法务|合规|部门", 2),
)


def _is_rebound_verb(verb: str) -> bool:
    return any(keyword in verb for keyword in _REBOUND_VERBS)


def _edge_visual(rel: RelationEdge, source: dict[str, Any], target: dict[str, Any],
                 center: str) -> dict[str, Any]:
    """线语义（对齐 html画图PROMPT V1 的 A 组关系图）：

    - 压向当事人（强势方）→ 粗实线箭头；
    - 当事人发出的行动 → 细实线箭头；动词带反弹/觉醒含义 → 灰色虚线箭头；
    - 涉及无形角色（制度/规律/利益）→ 灰色虚线箭头；
    - 卫星节点之间 → 虚线圆点（间接/结构关系）。
    """
    if source.get("kind") == "ghost" or target.get("kind") == "ghost":
        return dict(stroke=_SOFT, width=4, dash="22 16", marker="arr", style="solid")
    if rel.target == center and rel.source != center:
        return dict(stroke=_INK, width=6, dash="", marker="arr", style="solid")
    if rel.source == center and rel.target != center:
        if _is_rebound_verb(rel.verb):
            return dict(stroke=_SOFT, width=4, dash="22 16", marker="arr", style="solid")
        return dict(stroke=_INK, width=4, dash="", marker="arr", style="solid")
    return dict(stroke=_INK, width=4, dash="18 14", marker="dot", style="dash")


def _relation_why(relations: list[RelationEdge], name: str) -> str:
    for rel in relations:
        if name in (rel.source, rel.target) and rel.why:
            return rel.why
    return ""


def _pack_rows(names: list[str], sizes: dict[str, tuple[int, int]],
               canvas_w: int, gap: int = 60, limit: int = 8) -> list[list[str]]:
    """把节点按真实宽度贪心打包成行（一行放不下自动折行），返回行列表。"""
    rows: list[list[str]] = []
    for name in names[:limit]:
        used = sum(sizes[n][0] + gap for n in rows[-1]) if rows else 0
        if rows and used + sizes[name][0] <= canvas_w - 40:
            rows[-1].append(name)
        else:
            rows.append([name])
    return rows


def _place_row(nodes: dict[str, dict[str, Any]], row: list[str], row_cy: int,
               sizes: dict[str, tuple[int, int]], relations: list[RelationEdge],
               canvas_w: int, gap: int = 60) -> None:
    """把一行节点按真实宽度居中排布并写入 nodes。"""
    total = sum(sizes[name][0] for name in row) + gap * (len(row) - 1)
    x = canvas_w / 2 - total / 2
    for name in row:
        width, height = sizes[name]
        nodes[name] = dict(cx=int(x + width / 2), cy=row_cy, w=width, h=height,
                           kind="ghost" if _is_ghost(name) else "org", name=name,
                           why=_relation_why(relations, name))
        x += width + gap


def _tree_rank(name: str, center: str) -> int:
    """职级分层：权力越大数字越小、行越靠上；无形角色沉底，当事人固定在普通职员层。"""
    if name == center:
        return 3
    if _is_ghost(name):
        return 4
    for keywords, rank in _TREE_RANKS:
        if re.search(keywords, name):
            return rank
    return 3


def _build_edges(relations: list[RelationEdge], nodes: dict[str, dict[str, Any]],
                 center: str, *, away_from: tuple[int, int],
                 use_curve: bool = True) -> list[dict[str, Any]]:
    """由关系列表生成边几何。person 圆环节点的端点锚到圆环上，其余锚到节点框边；
    use_curve 时与中心相连的辐射线用弧线（凸向远离当事人一侧），短线和卫星线用直线。
    """
    center_radius = 172
    edges: list[dict[str, Any]] = []
    for rel in relations:
        source, target = nodes.get(rel.source), nodes.get(rel.target)
        if not source or not target:
            continue
        involves_center = center in (rel.source, rel.target)
        p1 = _clip_point(source, target)
        p2 = _clip_point(target, source)
        if rel.source == center and source.get("kind") == "person":
            p1 = _circle_point(source, target, center_radius)
        if rel.target == center and target.get("kind") == "person":
            p2 = _circle_point(target, source, center_radius)
        edge = dict(
            x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1],
            verb=rel.verb,
            source=rel.source, target=rel.target,
            **_edge_visual(rel, source, target, center),
        )
        length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        if use_curve and involves_center and length >= 90:
            control = _curve_control_point(p1, p2, away_from=away_from)
            edge["qx"], edge["qy"] = int(control[0]), int(control[1])
            # 初始点取弧顶；最终位置由 _place_verb_labels 全局防碰撞后定稿
            edge["lx"] = int((p1[0] + 2 * control[0] + p2[0]) / 4)
            edge["ly"] = int((p1[1] + 2 * control[1] + p2[1]) / 4)
        else:
            edge["lx"], edge["ly"] = _label_point(p1, p2, source, target, verb=rel.verb)
        edges.append(edge)
    return edges


def _diagram_overflows(layout: dict[str, Any], canvas_w: int) -> bool:
    """边界检查：任何节点框越过画布左右边界 8px 即超界（动词胶囊已被夹在画布内）。"""
    for node in layout["nodes"].values():
        half = 230.0 if node.get("kind") == "person" else node.get("w", 340) / 2
        if node["cx"] - half < 8 or node["cx"] + half > canvas_w - 8:
            return True
    return False


# 「超界自动缩字」档位：图里字号按档等比缩小、节点框与胶囊同步缩小，直到收进边界
_FIT_FONT_SCALES = (1.0, 0.9, 0.8, 0.72)


def layout_diagram(relations: list[RelationEdge], *, person_label: str = "当事人",
                   person_sub: str = "", canvas_w: int = DIAGRAM_CANVAS_W,
                   arrow_style: str = "curve", topology: str = "") -> dict[str, Any]:
    """把关系列表布局成网络图几何，拓扑选型对齐 html画图PROMPT V1 的 A 组关系图：

    - 双方对峙（topology="对峙"，或全图只有两方时自动）：当事人与对手左右对峙、箭头对射；
    - 组织层级树（topology="层级"）：按职级分行，权力越大越靠上、描边越粗，当事人高亮；
    - 多方群像（默认）：当事人（或最高连接度节点）居中，其余环绕。

    画出来的图超出画布边界时，按 _FIT_FONT_SCALES 逐档缩小图内字号重新布局，
    直到收进边界（返回 font_scale，HTML 层用 --dg-fs 变量联动字号）。

    返回 {"canvas_h", "nodes", "edges", "center", "mode", "font_scale"}，
    nodes 含坐标尺寸与 kind（person/ghost/org）；edges 含线段端点、线语义
    （stroke/width/dash/marker）与标签坐标，弧线额外带二次贝塞尔控制点（qx, qy）。
    """
    if not relations:
        return {"canvas_h": 0, "nodes": {}, "edges": [], "center": "",
                "mode": "orbit", "font_scale": 1.0}

    # 中心节点：优先「当事人」，否则取连接度最高的节点
    counter: dict[str, int] = {}
    for rel in relations:
        for endpoint in (rel.source, rel.target):
            counter[endpoint] = counter.get(endpoint, 0) + 1
    center = person_label if person_label in counter else max(counter, key=counter.get)

    mode = "orbit"
    if topology == "对峙":
        mode = "confront"
    elif topology == "层级" and len(counter) >= 2:
        mode = "tree"
    elif not topology and len(counter) == 2:
        mode = "confront"

    layout: dict[str, Any] = {}
    for font_scale in _FIT_FONT_SCALES:
        if mode == "confront":
            layout = _layout_confrontation(relations, center, person_sub, canvas_w,
                                           counter, font_scale=font_scale)
        elif mode == "tree":
            layout = _layout_tree(relations, center, canvas_w, counter,
                                  font_scale=font_scale)
        else:
            layout = _layout_orbit(relations, center, person_sub, canvas_w,
                                   arrow_style, font_scale=font_scale)
        if not _diagram_overflows(layout, canvas_w):
            break
    layout["font_scale"] = font_scale
    return layout


def _layout_orbit(relations: list[RelationEdge], center: str, person_sub: str,
                  canvas_w: int, arrow_style: str, font_scale: float = 1.0) -> dict[str, Any]:
    """多方群像：当事人居中，L1 环绕 + 底部卫星行。"""
    counter: dict[str, int] = {}
    for rel in relations:
        for endpoint in (rel.source, rel.target):
            counter[endpoint] = counter.get(endpoint, 0) + 1
    l1_names: list[str] = []   # 与中心直连的节点
    l2_names: list[str] = []   # 只与其他卫星节点相连的节点
    for name in counter:
        if name == center:
            continue
        for rel in relations:
            if center in (rel.source, rel.target) and name in (rel.source, rel.target):
                l1_names.append(name)
                break
        else:
            l2_names.append(name)

    # 纵向几何按节点实际高度推导。L1 每行最多 2 个（左右对称），放不下自动再加一行，
    # 当事人圆环顶始终低于最后一行 L1 底边 ≥130px；画布高度必须覆盖所有行，
    # 否则绝对定位节点会溢出画布、压到下方模块（分析过程）。
    sizes = {name: _node_size(name, _relation_why(relations, name), font_scale)
             for name in l1_names + l2_names}
    l1_max_h = max([sizes[name][1] for name in l1_names] + [180])

    l1_cy = 190
    row_pitch = l1_max_h + 90
    l1_rows = min(4, max(1, -(-len(l1_names) // 2))) if l1_names else 0
    l1_last_bottom = (l1_cy + l1_max_h / 2 + (l1_rows - 1) * row_pitch) if l1_rows else l1_cy
    person_cy = int(l1_last_bottom + 130 + 172)
    cx = canvas_w // 2

    nodes: dict[str, dict[str, Any]] = {
        center: dict(cx=cx, cy=person_cy, kind="person", name=center, sub=person_sub)
    }

    # L1 槽位：每行左右各一个（0.21/0.79），纵向最多四行——同行同列不会横向重叠；
    # 超出槽位的 L1 节点不丢弃，转入底部卫星行继续摆放（边照常绘制）
    l1_slots = [(fx, int(l1_cy + row * row_pitch))
                for row in range(l1_rows) for fx in (0.21, 0.79)]
    bottom_names = l2_names + l1_names[len(l1_slots):]
    for index, name in enumerate(l1_names[: len(l1_slots)]):
        fx, fy = l1_slots[index]
        width, height = sizes[name]
        nodes[name] = dict(cx=int(canvas_w * fx), cy=fy, w=width, h=height,
                           kind="ghost" if _is_ghost(name) else "org", name=name,
                           why=_relation_why(relations, name))

    # 底部卫星行（L2 + L1 溢出）：按真实宽度从左到右打包居中，一行放不下自动折行，
    # 彻底消除同行节点的横向重叠；画布高度随行数向下堆叠
    bottom_rows = _pack_rows(bottom_names, sizes, canvas_w)
    if bottom_rows:
        row_y = person_cy + 172 + 120 + 90
        for row in bottom_rows:
            row_h = max(sizes[name][1] for name in row)
            _place_row(nodes, row, int(row_y + row_h / 2), sizes, relations, canvas_w)
            row_y += row_h + 70
        canvas_h = int(row_y - 70 + 50)
    else:
        canvas_h = int(person_cy + 172 + 120 + 70)

    edges = _build_edges(relations, nodes, center, away_from=(cx, person_cy),
                         use_curve=str(arrow_style).lower() != "solid")
    # 动词标签全局防碰撞：躲开所有节点、彼此和画布边界后再定稿
    _place_verb_labels(edges, nodes, canvas_w, canvas_h, font_scale)
    return {"canvas_h": canvas_h, "nodes": nodes, "edges": edges,
            "center": center, "mode": "orbit"}


def _layout_confrontation(relations: list[RelationEdge], center: str, person_sub: str,
                          canvas_w: int, counter: dict[str, int],
                          font_scale: float = 1.0) -> dict[str, Any]:
    """双方对峙：当事人（头像圆环）居左、主对手居右；多余角色沉底摆放。

    压向当事人的线从两人上方跨越（粗实线），当事人发出的线从下方反打（反弹动词
    画灰虚线）——上下对射，走廊不挤标签；动词标签骑在弧顶空白处。
    """
    others = [name for name in counter if name != center]
    opponent = max(others, key=lambda n: counter[n])   # 主对手=连接度最高的非中心节点
    extras = [name for name in others if name != opponent]
    sizes = {name: _node_size(name, _relation_why(relations, name), font_scale)
             for name in counter}
    opp_w, opp_h = sizes[opponent]

    main_rels = [r for r in relations if {r.source, r.target} == {center, opponent}]
    into_person = [r for r in main_rels if r.target == center][:3]
    out_edges = [r for r in main_rels if r.target != center][:3]

    # 纵向中轴：上拱弧线的层高（压制线可叠多条）决定 cy，保证弧顶不出画布
    top_need = max(opp_h, 470) // 2 + 90 + max(0, len(into_person) - 1) * 100 + 30
    cy = max(360, top_need)
    person_cx, opp_cx = int(canvas_w * 0.25), int(canvas_w * 0.75)
    nodes: dict[str, dict[str, Any]] = {
        center: dict(cx=person_cx, cy=cy, kind="person", name=center, sub=person_sub),
        opponent: dict(cx=opp_cx, cy=cy, w=opp_w, h=opp_h,
                       kind="ghost" if _is_ghost(opponent) else "org", name=opponent,
                       why=_relation_why(relations, opponent)),
    }

    p_top = (person_cx, cy - 186)            # 当事人圆环顶
    o_top = (opp_cx, cy - opp_h // 2 - 14)   # 对手框顶
    p_bottom = (person_cx, cy + 330)         # 当事人名字/身份下方
    o_bottom = (opp_cx, cy + opp_h // 2 + 14)
    top_apex = cy - max(opp_h, 470) // 2 - 90
    bottom_apex = cy + 330 + 90
    edges: list[dict[str, Any]] = []
    for index, rel in enumerate(into_person):
        apex = top_apex - index * 100
        qx = (o_top[0] + p_top[0]) // 2
        edge = dict(x1=o_top[0], y1=o_top[1], x2=p_top[0], y2=p_top[1],
                    verb=rel.verb, source=rel.source, target=rel.target,
                    qx=qx, qy=apex,
                    **_edge_visual(rel, nodes[rel.source], nodes[rel.target], center))
        edge["lx"] = int((o_top[0] + 2 * qx + p_top[0]) / 4)
        edge["ly"] = int((o_top[1] + 2 * apex + p_top[1]) / 4)
        edges.append(edge)
    for index, rel in enumerate(out_edges):
        apex = bottom_apex + index * 100
        qx = (p_bottom[0] + o_bottom[0]) // 2
        edge = dict(x1=p_bottom[0], y1=p_bottom[1], x2=o_bottom[0], y2=o_bottom[1],
                    verb=rel.verb, source=rel.source, target=rel.target,
                    qx=qx, qy=apex,
                    **_edge_visual(rel, nodes[rel.source], nodes[rel.target], center))
        edge["lx"] = int((p_bottom[0] + 2 * qx + o_bottom[0]) / 4)
        edge["ly"] = int((p_bottom[1] + 2 * apex + o_bottom[1]) / 4)
        edges.append(edge)

    bottom_max = bottom_apex + max(0, len(out_edges) - 1) * 100 + 40
    base_bottom = cy + max(opp_h // 2, 330) + 50
    canvas_h = int(max(base_bottom, bottom_max + 50))

    # 多余角色（第三方/无形角色）：底部打包成行，边几何走通用构建
    bottom_rows = _pack_rows(extras, sizes, canvas_w)
    if bottom_rows:
        row_y = max(cy + max(opp_h // 2, 330), bottom_max) + 130
        for row in bottom_rows:
            row_h = max(sizes[name][1] for name in row)
            _place_row(nodes, row, int(row_y + row_h / 2), sizes, relations, canvas_w)
            row_y += row_h + 70
        canvas_h = int(row_y - 70 + 50)

    extra_rels = [r for r in relations if {r.source, r.target} != {center, opponent}]
    edges += _build_edges(extra_rels, nodes, center, away_from=(person_cx, cy),
                          use_curve=False)
    _place_verb_labels(edges, nodes, canvas_w, canvas_h, font_scale)
    return {"canvas_h": canvas_h, "nodes": nodes, "edges": edges,
            "center": center, "mode": "confront"}


def _layout_tree(relations: list[RelationEdge], center: str, canvas_w: int,
                 counter: dict[str, int], font_scale: float = 1.0) -> dict[str, Any]:
    """组织层级树：按职级分行（权力越大越靠上、节点描边越粗），当事人橙色高亮。

    当事人此时是高亮方框（头像已在背景概述区），无形角色沉在最底行。
    """
    sizes = {name: _node_size(name, _relation_why(relations, name), font_scale)
             for name in counter}
    tiers: dict[int, list[str]] = {}
    for name in counter:
        tiers.setdefault(_tree_rank(name, center), []).append(name)
    # 描边分级拉满对比（权力越大越粗）；行距 130 给动词胶囊留出走廊，避免压字
    border_by_tier = {0: 8, 1: 6, 2: 4, 3: 3, 4: 3}

    nodes: dict[str, dict[str, Any]] = {}
    row_y = 40
    for tier in sorted(tiers):
        for row in _pack_rows(tiers[tier], sizes, canvas_w):
            row_h = max(sizes[name][1] for name in row)
            _place_row(nodes, row, int(row_y + row_h / 2), sizes, relations, canvas_w)
            for name in row:
                nodes[name]["border"] = border_by_tier.get(tier, 3)
                nodes[name]["highlight"] = name == center
            row_y += row_h + 130
    canvas_h = int(row_y - 70 + 40)

    edges = _build_edges(relations, nodes, center,
                         away_from=(canvas_w // 2, canvas_h // 2), use_curve=False)
    _place_verb_labels(edges, nodes, canvas_w, canvas_h, font_scale)
    return {"canvas_h": canvas_h, "nodes": nodes, "edges": edges,
            "center": center, "mode": "tree"}


def _curve_control_point(p1: tuple[int, int], p2: tuple[int, int], *,
                         away_from: tuple[int, int]) -> tuple[float, float]:
    """弧线箭头的二次贝塞尔控制点：垂直于直线偏移，凸向远离 away_from（当事人）的一侧。"""
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    offset = min(max(length * 0.22, 24), 90)
    nx, ny = -dy / length, dx / length
    plus = (mx + nx * offset - away_from[0]) ** 2 + (my + ny * offset - away_from[1]) ** 2
    minus = (mx - nx * offset - away_from[0]) ** 2 + (my - ny * offset - away_from[1]) ** 2
    if plus >= minus:
        return (mx + nx * offset, my + ny * offset)
    return (mx - nx * offset, my - ny * offset)


def _clip_point(node: dict[str, Any], toward: dict[str, Any], *, pad: int = 18) -> tuple[int, int]:
    """从 node 中心指向 toward 中心方向上，node 边界外扩 pad 的交点。"""
    if node.get("kind") == "person":
        return _circle_point(node, toward, 172, pad=pad)
    cx, cy = node["cx"], node["cy"]
    dx, dy = toward["cx"] - cx, toward["cy"] - cy
    tx = (node.get("w", 340) / 2 + pad) / abs(dx) if dx else 1e9
    ty = (node.get("h", 180) / 2 + pad) / abs(dy) if dy else 1e9
    t = min(tx, ty)
    return (int(cx + dx * t), int(cy + dy * t))


def _circle_point(node: dict[str, Any], toward: dict[str, Any], radius: int, *, pad: int = 18) -> tuple[int, int]:
    cx, cy = node["cx"], node["cy"]
    dx, dy = toward["cx"] - cx, toward["cy"] - cy
    distance = (dx * dx + dy * dy) ** 0.5 or 1.0
    r = radius + pad
    return (int(cx + dx / distance * r), int(cy + dy / distance * r))


def _label_point(p1: tuple[int, int], p2: tuple[int, int],
                 node_a: dict[str, Any], node_b: dict[str, Any],
                 verb: str = "") -> tuple[int, int]:
    """动词标签定位：长线取中点骑线；短线（<240px）垂直偏移到线旁，避免盖住箭头。

    偏移距离按标签自身宽度自适应（胶囊半宽 + 余量），确保完整躲开两端节点框。
    """
    length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
    if length >= 240:
        for t in (0.5, 0.62, 0.38, 0.74, 0.26):
            x = p1[0] + (p2[0] - p1[0]) * t
            y = p1[1] + (p2[1] - p1[1]) * t
            if not _inside_node(x, y, node_a, 46) and not _inside_node(x, y, node_b, 46):
                return (int(x), int(y))
        return (int((p1[0] + p2[0]) / 2), int((p1[1] + p2[1]) / 2))

    # 短线：中点沿法线偏移，距离按胶囊宽度自适应，两个方向里选离节点更远的一侧
    mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    if length < 1:
        return (int(mid[0]), int(mid[1]))
    dx, dy = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
    half_width = _display_width(verb) * 19 + 26  # 胶囊半宽估算：字号38px的一半 + 内边距
    best: tuple[float, tuple[float, float]] = (-1.0, mid)
    for sign in (1, -1):
        for distance in (72, 96, 120, 150):
            nx, ny = mid[0] + dy * distance * sign, mid[1] - dx * distance * sign
            if _inside_node(nx, ny, node_a, half_width) or _inside_node(nx, ny, node_b, half_width):
                continue
            score = min(_node_distance(nx, ny, node_a), _node_distance(nx, ny, node_b)) - distance * 0.4
            if score > best[0]:
                best = (score, (nx, ny))
        if best[0] > 0:
            break
    return (int(best[1][0]), int(best[1][1]))


def _node_distance(x: float, y: float, node: dict[str, Any]) -> float:
    return ((x - node["cx"]) ** 2 + (y - node["cy"]) ** 2) ** 0.5


def _inside_node(x: float, y: float, node: dict[str, Any], margin: int) -> bool:
    if node.get("kind") == "person":
        radius = 172 + margin
        dx, dy = x - node["cx"], y - node["cy"]
        return dx * dx + dy * dy <= radius * radius
    half_w = node.get("w", 340) / 2 + margin
    half_h = node.get("h", 180) / 2 + margin
    return abs(x - node["cx"]) <= half_w and abs(y - node["cy"]) <= half_h


def _verb_pill_size(verb: str, font_scale: float = 1.0) -> tuple[int, int]:
    """动词胶囊渲染尺寸估算：38px 字号、内边距 20×2/8×2、边框 3×2、行高约 1.4。"""
    width = (_display_width(verb) * 38 + 46) * font_scale
    return int(width), int(80 * font_scale)


def _node_rect(node: dict[str, Any], margin: float = 0.0) -> tuple[float, float, float, float]:
    """节点可视外接矩形 (l, t, r, b)；person 取头像环 + 下方名字的整体包围盒。"""
    if node.get("kind") == "person":
        return (node["cx"] - 230 - margin, node["cy"] - 170 - margin,
                node["cx"] + 230 + margin, node["cy"] + 310 + margin)
    half_w = node.get("w", 340) / 2 + margin
    half_h = node.get("h", 180) / 2 + margin
    return (node["cx"] - half_w, node["cy"] - half_h,
            node["cx"] + half_w, node["cy"] + half_h)


def _rects_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float], gap: float = 0.0) -> bool:
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _label_candidates(edge: dict[str, Any],
                      base: tuple[float, float]) -> Iterator[tuple[float, float]]:
    """标签候选位置，按偏好排序输出：初始点 → 八向偏移 → 沿线（弧线沿贝塞尔）滑动 ± 法向偏移。"""
    x1, y1 = float(edge["x1"]), float(edge["y1"])
    x2, y2 = float(edge["x2"]), float(edge["y2"])
    yield base
    for dx, dy in ((0, -70), (0, 70), (-70, 0), (70, 0),
                   (-60, -60), (60, -60), (-60, 60), (60, 60)):
        yield (base[0] + dx, base[1] + dy)
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    for t in (0.5, 0.62, 0.38, 0.74, 0.26):
        if "qx" in edge:
            s = 1.0 - t
            px = s * s * x1 + 2 * s * t * float(edge["qx"]) + t * t * x2
            py = s * s * y1 + 2 * s * t * float(edge["qy"]) + t * t * y2
        else:
            px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        yield (px, py)
        for distance in (40, 80, 120, 160):
            yield (px + uy * distance, py - ux * distance)
            yield (px - uy * distance, py + ux * distance)


def _place_verb_labels(edges: list[dict[str, Any]], nodes: dict[str, Any],
                       canvas_w: int, canvas_h: int, font_scale: float = 1.0) -> None:
    """动词标签全局防碰撞放置：依次为每条边选标签中心点，躲开所有节点、
    已放置的其他标签与画布边界；候选全撞时取障碍最少的次优点并夹回画布内。
    """
    placed: list[tuple[float, float, float, float]] = []
    node_rects = [_node_rect(node, 10) for node in nodes.values()]
    for edge in edges:
        pill_w, pill_h = _verb_pill_size(edge["verb"], font_scale)
        best: tuple[float, float, float] = (-1.0, float(edge["lx"]), float(edge["ly"]))
        chosen: Optional[tuple[float, float]] = None
        for x, y in _label_candidates(edge, (float(edge["lx"]), float(edge["ly"]))):
            x = min(max(x, pill_w / 2 + 8), canvas_w - pill_w / 2 - 8)
            y = min(max(y, pill_h / 2 + 8), canvas_h - pill_h / 2 - 8)
            rect = (x - pill_w / 2, y - pill_h / 2, x + pill_w / 2, y + pill_h / 2)
            hit_nodes = sum(1 for nr in node_rects if _rects_overlap(rect, nr))
            hit_labels = sum(1 for pr in placed if _rects_overlap(rect, pr, 4))
            if hit_nodes == 0 and hit_labels == 0:
                chosen = (x, y)
                break
            score = 100.0 - hit_nodes * 10 - hit_labels * 5
            if score > best[0]:
                best = (score, x, y)
        if chosen is None:
            chosen = (best[1], best[2])
        edge["lx"], edge["ly"] = int(chosen[0]), int(chosen[1])
        placed.append((chosen[0] - pill_w / 2, chosen[1] - pill_h / 2,
                       chosen[0] + pill_w / 2, chosen[1] + pill_h / 2))


# ---------------------------------------------------------------------------
# 三、HTML 模板（报刊杂志风 · 浅底 · 1080 宽自适应高 · 正文统一 46px）
# ---------------------------------------------------------------------------

_BRAND = "「漫道」职场群·真实案例分享"
_FOOTER_L1 = "「漫道」职场群"
_FOOTER_L2 = "只聊工作不聊天"
_CTA = "喜欢您来"

def _esc(text: Any) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _person_brief(facts: list[tuple[str, str]]) -> str:
    """从事实字段推导当事人身份简介：身份/职位优先于年龄（如「银行开发10年 · 33岁」）。

    头像下方与关系图中心节点共用，直接展示身份、不带「当事人」前缀；
    找不到匹配字段时回退用第一条事实，仍为空则用「当事人」。
    """
    value = ""
    for label, item in facts:
        if "当事人" in label or "身份" in label or "背景" in label:
            value = item
            break
    if not value and facts:
        value = facts[0][1]
    segments = [seg.strip() for seg in re.split(r"[，,；;]", value) if seg.strip()]

    def _is_age(segment: str) -> bool:
        return bool(re.fullmatch(r"\d{1,3}\s*岁", segment))

    # 身份优先：纯年龄段（"33岁"）排到非年龄段之后
    ordered = [seg for seg in segments if not _is_age(seg)] + [seg for seg in segments if _is_age(seg)]
    picked: list[str] = []
    used = 0
    for segment in ordered:
        width = _display_width(segment)
        if picked and used + width + 3 > 18:
            break
        if not picked and width > 18:
            break
        picked.append(segment)
        used += width + 3
        if used >= 18:
            break
    return " · ".join(picked) or "当事人"


def _split_title(title: str) -> tuple[str, str]:
    """长标题拆两行：优先在首个逗号/问号后断开，否则按长度对半。"""
    text = (title or "").strip()
    if _display_width(text) <= 11:
        return text, ""
    for index, char in enumerate(text):
        if char in "，？?！" and index >= 4:
            return text[: index + 1], text[index + 1:]
    mid = (len(text) + 1) // 2
    return text[:mid], text[mid:]


def build_card_html(card: CaseCard, *, avatar_file: str, qr_file: str,
                    brand: str = _BRAND, footer_l1: str = _FOOTER_L1,
                    footer_l2: str = _FOOTER_L2, cta: str = _CTA,
                    arrow_style: Optional[str] = None,
                    diagram_override: Optional[dict[str, Any]] = None) -> str:
    person_brief = _person_brief(card.facts)
    if arrow_style is None:
        arrow_style = str(get_settings().html_card_arrow_style or "curve")
    diagram = diagram_override or layout_diagram(
        card.relations, person_sub=person_brief, arrow_style=arrow_style,
        topology=card.topology)

    title_l1, title_l2 = _split_title(card.title)
    # 标签列宽按最长标签计算：既不换行，又保证各行黑色正文起始位置对齐
    # （46px/字 > 42px 字号，留出余量；.fact .k 用 var(--k-w) 定宽消费该值）
    label_width = max((_display_width(k) for k, _ in card.facts), default=3)
    k_w = min(max(int(label_width * 46) + 20, 150), 380)
    facts_html = "\n".join(
        f'<div class="fact"><span class="k">{_esc(k)}</span><span class="v">{_esc(v)}</span></div>'
        for k, v in card.facts)
    scenes_html = "\n".join(f'<div class="scene">{_esc(s)}</div>' for s in card.scenes)
    chips_html = '<span class="chip first">关键词</span>' + "".join(
        f'<span class="chip">{_esc(k)}</span>' for k in card.keywords)
    analysis_html = "\n".join(
        f'<div class="item"><div class="badge">{i + 1:02d}</div><div class="body">'
        f'<div class="tagline"><span class="tag">『{_esc(tag)}』</span></div>'
        f'<div class="txt">{_esc(txt)}</div></div></div>'
        for i, (tag, txt) in enumerate(card.analysis))
    solutions_html = "\n".join(
        f'<div class="item"><div class="num serif">{i + 1:02d}</div><div class="body">'
        f'<div class="tagline"><span class="tag">『{_esc(tag)}』</span></div>'
        f'<div class="txt">{_esc(txt)}</div></div></div>'
        for i, (tag, txt) in enumerate(card.solutions))
    quotes_html = "\n".join(
        f'<div class="quote{" main" if i == 0 else ""}"><div class="q">{_esc(q)}</div>'
        f'<div class="sig">—— {_esc(sig)}</div></div>'
        for i, (q, sig) in enumerate(card.quotes))

    diagram_html, canvas_h = _build_diagram_html(diagram, avatar_file)
    relation_block = ""
    if diagram_html:
        summary = f'<div class="rel-sum">{_esc(card.relation_summary)}</div>' if card.relation_summary else ""
        relation_block = (
            '<div class="mod"><div class="mod-head"><span class="sq"></span>'
            '<span class="zh">人物关系</span><span class="en">RELATION MAP</span><span class="line"></span></div>'
            f'<div class="dg-panel">{diagram_html}</div>{summary}</div>'
        )
    question_block = f'<div class="question-band serif">{_esc(card.question)}</div>' if card.question else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{CARD_WIDTH}px; background:#F7F3EC; }}
  body {{ font-family:"Microsoft YaHei","Noto Sans SC",sans-serif; color:#1A1A1A; padding:52px 48px 48px; }}
  .serif {{ font-family:"Noto Serif SC","STSong",serif; }}
  .masthead {{ display:flex; justify-content:space-between; align-items:baseline; }}
  .masthead .brand {{ font-size:44px; font-weight:900; letter-spacing:2px; }}
  .masthead .brand::before {{ content:""; display:inline-block; width:24px; height:24px; background:#E8590C; margin-right:14px; }}
  .rule-thick {{ border-bottom:6px solid #1A1A1A; margin-top:14px; }}
  .rule-thin {{ border-bottom:2px solid #1A1A1A; margin-top:6px; }}
  .title-wrap {{ position:relative; margin-top:40px; }}
  .title-wrap .deco-quote {{ position:absolute; right:0; top:-36px; font-size:250px; line-height:1;
    color:rgba(26,26,26,.08); font-weight:900; user-select:none; }}
  .title {{ font-size:84px; font-weight:900; line-height:1.32; letter-spacing:1px; }}
  .title .l2 {{ color:#E8590C; }}
  .subtitle {{ margin-top:30px; font-size:52px; font-weight:900; line-height:1.4;
    border-left:12px solid #1A1A1A; padding-left:26px; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:36px; }}
  .chip {{ font-size:42px; font-weight:700; padding:12px 28px; border:3px solid #1A1A1A; border-radius:999px; background:#FFFFFF; }}
  .chip.first {{ background:#1A1A1A; color:#FFF; }}
  .mod {{ margin-top:60px; }}
  .mod-head {{ display:flex; align-items:center; gap:18px; margin-bottom:26px; }}
  .mod-head .sq {{ width:22px; height:22px; background:#E8590C; flex:none; }}
  .mod-head .zh {{ font-size:46px; font-weight:900; letter-spacing:3px; }}
  .mod-head .en {{ font-size:36px; color:#A39A8C; letter-spacing:4px; font-weight:700; }}
  .mod-head .line {{ flex:1; border-top:2px solid #1A1A1A; }}
  .facts-avatar {{ display:flex; gap:32px; }}
  .avatar-box {{ flex:none; text-align:center; width:250px; }}
  .avatar-box img {{ width:220px; height:220px; border-radius:50%; object-fit:cover;
    border:6px solid #1A1A1A; background:#FFF; display:block; margin:0 auto; }}
  .avatar-box .note {{ font-size:38px; font-weight:700; margin-top:14px; color:#6B655C; }}
  .facts {{ flex:1; background:#FFFFFF; border:3px solid #1A1A1A; padding:26px 30px; border-radius:24px; }}
  .fact {{ display:flex; align-items:baseline; padding:12px 0; }}
  .fact + .fact {{ border-top:2px dashed #D8D0C2; }}
  .fact .k {{ flex:none; width:var(--k-w,auto); white-space:nowrap; margin-right:24px; font-size:42px; font-weight:900; color:#E8590C; }}
  .fact .v {{ font-size:46px; line-height:1.5; font-weight:500; }}
  .scenes {{ margin-top:26px; background:#FFFFFF; border:3px solid #1A1A1A; padding:30px 34px; border-radius:24px; }}
  .scene {{ font-size:46px; font-weight:700; line-height:1.6; }}
  .scene + .scene {{ margin-top:18px; }}
  .scene::before {{ content:""; display:inline-block; width:18px; height:18px; background:#E8590C; margin-right:18px; }}
  .question-band {{ margin-top:30px; background:#1A1A1A; color:#FFF; padding:32px 36px;
    font-size:54px; font-weight:900; line-height:1.5; border-left:16px solid #E8590C; }}
  .dg-panel {{ background:#FFFFFF; border:3px solid #1A1A1A; padding:8px 0; border-radius:24px; }}
  .dg-canvas {{ position:relative; margin:0 auto; }}
  .dg-node {{ position:absolute; display:flex; flex-direction:column; justify-content:center;
    align-items:center; text-align:center; padding:calc(14px*var(--dg-fs,1)) calc(20px*var(--dg-fs,1)); z-index:2; }}
  .dg-node.ghost {{ border:3px dashed #1A1A1A; background:#FDFCF9; border-radius:18px; }}
  .dg-node.org {{ border:3px solid #1A1A1A; background:#FDFCF9; border-radius:18px; }}
  .dg-node.hl {{ background:#FBE8DC; }}
  .dg-name {{ font-size:calc(44px*var(--dg-fs,1)); font-weight:900; }}
  .dg-why {{ font-size:calc(36px*var(--dg-fs,1)); color:#6B655C; line-height:1.45; margin-top:calc(8px*var(--dg-fs,1)); }}
  .dg-node.person {{ width:460px; }}
  .dg-avatar {{ position:relative; width:340px; height:340px; }}
  .dg-avatar::before {{ content:""; position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
    width:328px; height:328px; border:3px dashed #1A1A1A; border-radius:50%; }}
  .dg-avatar img {{ position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
    width:248px; height:248px; border-radius:50%; object-fit:cover; border:7px solid #1A1A1A; background:#FFF; }}
  .dg-pname {{ font-size:calc(46px*var(--dg-fs,1)); font-weight:900; margin-top:10px; }}
  .dg-psub {{ font-size:calc(36px*var(--dg-fs,1)); color:#6B655C; margin-top:6px; font-weight:500; }}
  .dg-verb {{ position:absolute; transform:translate(-50%,-50%); z-index:3;
    background:#E8590C; color:#FFF; font-size:calc(38px*var(--dg-fs,1)); font-weight:900;
    padding:calc(8px*var(--dg-fs,1)) calc(20px*var(--dg-fs,1));
    border:3px solid #F7F3EC; letter-spacing:2px; border-radius:12px; }}
  .rel-sum {{ margin-top:26px; background:#FBE8DC; border-left:12px solid #E8590C;
    padding:22px 28px; font-size:42px; font-weight:900; line-height:1.5; border-radius:0 24px 24px 0; }}
  .item {{ display:flex; gap:26px; align-items:flex-start; }}
  .badge {{ flex:none; width:80px; height:80px; border:4px solid #E8590C; border-radius:50%;
    color:#E8590C; font-size:44px; font-weight:900; text-align:center; line-height:74px;
    font-family:"Noto Serif SC",serif; }}
  .num {{ flex:none; width:94px; font-size:64px; font-weight:900; color:#E8590C;
    line-height:1.05; font-family:"Noto Serif SC",serif; }}
  .item .body {{ flex:1; }}
  .item .tagline {{ font-size:46px; font-weight:900; margin-bottom:10px; }}
  .item .tagline .tag {{ border-bottom:8px solid #E8590C; padding-bottom:2px; }}
  .item .txt {{ font-size:46px; line-height:1.62; font-weight:500; }}
  .ana-list .item {{ padding:26px 0; }}
  .ana-list .item + .item {{ border-top:3px solid #1A1A1A; }}
  .sol-panel {{ background:#FFFFFF; border:3px solid #1A1A1A; padding:14px 34px; border-radius:24px; }}
  .sol-list .item {{ padding:22px 0; }}
  .sol-list .item + .item {{ border-top:2px dashed #D8D0C2; }}
  .quote {{ background:#FBE8DC; border:3px solid #1A1A1A; padding:28px 34px; border-radius:24px; }}
  .quote + .quote {{ margin-top:24px; }}
  .quote.main {{ background:#1A1A1A; }}
  .quote .q {{ font-size:52px; font-weight:900; line-height:1.55; font-family:"Noto Serif SC",serif; }}
  .quote.main .q {{ color:#FFF; font-size:56px; }}
  .quote .q::before {{ content:"“"; color:#E8590C; font-size:62px; }}
  .quote .sig {{ text-align:right; font-size:42px; font-weight:700; color:#6B655C; margin-top:12px; }}
  .quote.main .sig {{ color:#F3C4A6; }}
  .footer-row {{ margin-top:60px; border-top:4px solid #1A1A1A; padding-top:26px;
    display:flex; align-items:flex-end; justify-content:space-between; gap:30px; }}
  .foot-left {{ flex:1; font-size:40px; font-weight:700; color:#1A1A1A;
    line-height:1.6; align-self:flex-start; }}
  .cta {{ font-size:46px; font-weight:900; margin-bottom:14px; letter-spacing:2px; }}
  .cta::after {{ content:""; display:block; border-bottom:8px solid #E8590C; margin-top:4px; }}
  .qr-box {{ flex:none; width:346px; height:346px; border:4px solid #1A1A1A; background:#FFF; padding:12px;
    border-radius:24px; }}
  .qr-box img {{ width:100%; height:100%; object-fit:contain; display:block; }}
</style>
</head>
<body>
  <div class="masthead"><div class="brand">{_esc(brand)}</div></div>
  <div class="rule-thick"></div>
  <div class="rule-thin"></div>
  <div class="title-wrap">
    <div class="deco-quote serif">”</div>
    <div class="title serif">{_esc(title_l1)}{f'<br><span class="l2">{_esc(title_l2)}</span>' if title_l2 else ''}</div>
    <div class="subtitle">{_esc(card.subtitle)}</div>
  </div>
  <div class="chips">{chips_html}</div>
  <div class="mod">
    <div class="mod-head"><span class="sq"></span><span class="zh">背景概述</span><span class="en">BACKGROUND</span><span class="line"></span></div>
    <div class="facts-avatar">
      <div class="avatar-box">
        <img src="{_esc(avatar_file)}" alt="当事人头像">
        <div class="note">{_esc(person_brief)}</div>
      </div>
      <div class="facts" style="--k-w:{k_w}px">
{facts_html}
      </div>
    </div>
    <div class="scenes">
{scenes_html}
    </div>
{question_block}
  </div>
{relation_block}
  <div class="mod">
    <div class="mod-head"><span class="sq"></span><span class="zh">分析过程</span><span class="en">ANALYSIS</span><span class="line"></span></div>
    <div class="ana-list">
{analysis_html}
    </div>
  </div>
  <div class="mod">
    <div class="mod-head"><span class="sq"></span><span class="zh">解决方案</span><span class="en">ACTION</span><span class="line"></span></div>
    <div class="sol-panel">
      <div class="sol-list">
{solutions_html}
      </div>
    </div>
  </div>
  <div class="mod">
    <div class="mod-head"><span class="sq"></span><span class="zh">金句</span><span class="en">QUOTES</span><span class="line"></span></div>
{quotes_html}
  </div>
  <div class="footer-row">
    <div class="foot-left">{_esc(footer_l1)}<br>{_esc(footer_l2)}</div>
    <div class="cta">{_esc(cta)}</div>
    <div class="qr-box"><img src="{_esc(qr_file)}" alt="入群二维码"></div>
  </div>
  <!-- 渲染兜底：画布高度按节点实际渲染高度自适应，杜绝节点溢出画布压到下方模块 -->
  <script>
  (function () {{
    var canvases = document.querySelectorAll('.dg-canvas');
    for (var i = 0; i < canvases.length; i++) {{
      var canvas = canvases[i];
      var maxBottom = 0;
      var nodes = canvas.querySelectorAll('.dg-node');
      for (var j = 0; j < nodes.length; j++) {{
        maxBottom = Math.max(maxBottom, nodes[j].offsetTop + nodes[j].offsetHeight);
      }}
      if (maxBottom + 30 > canvas.offsetHeight) {{ canvas.style.height = (maxBottom + 30) + 'px'; }}
    }}
  }})();
  </script>
  <div id="endmark" style="height:8px;background:rgb(255,0,255);margin-top:48px;"></div>
</body>
</html>
"""


def _build_diagram_html(diagram: dict[str, Any], avatar_file: str) -> tuple[str, int]:
    canvas_h = int(diagram.get("canvas_h") or 0)
    if not canvas_h:
        return "", 0
    image_file = diagram.get("image_file")
    if image_file:
        # 生图模式（离线验证链路）：关系图整幅由图片模型生成，直接以 <img> 铺进面板
        return (f'<img src="{_esc(image_file)}" alt="人物关系图" '
                f'style="width:100%;height:auto;display:block;border-radius:18px;">'), canvas_h
    canvas_w = DIAGRAM_CANVAS_W  # 完全落在面板边框+内边距内侧，贴边不压框
    font_scale = float(diagram.get("font_scale") or 1.0)
    lines = []
    for index, edge in enumerate(diagram.get("edges", [])):
        # 线语义（V1 规则）：压制=粗实线、反弹/无形=灰虚线、间接=虚线圆点
        marker = "dot" if edge.get("marker", "arr") == "dot" else "arr"
        seg = (f'stroke="{edge.get("stroke", "#1A1A1A")}" '
               f'stroke-width="{edge.get("width", 4)}"'
               + (f' stroke-dasharray="{edge["dash"]}"' if edge.get("dash") else "")
               + f' marker-end="url(#{marker})"')
        attrs = (f'data-edge="{index}" data-from="{_esc(edge.get("source", ""))}" '
                 f'data-to="{_esc(edge.get("target", ""))}" '
                 f'data-style="{edge.get("style", "solid")}"')
        if "qx" in edge:
            lines.append(
                f'<path d="M {edge["x1"]},{edge["y1"]} Q {edge["qx"]},{edge["qy"]} '
                f'{edge["x2"]},{edge["y2"]}" fill="none" {attrs} {seg}/>'
            )
        else:
            lines.append(
                f'<line x1="{edge["x1"]}" y1="{edge["y1"]}" x2="{edge["x2"]}" y2="{edge["y2"]}" {attrs} {seg}/>'
            )
    svg = (
        f'<svg width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" '
        f'style="position:absolute;left:0;top:0;"><defs>'
        '<marker id="arr" markerWidth="14" markerHeight="14" refX="12" refY="7" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L14,7 L0,14 Z" fill="#1A1A1A"/></marker>'
        '<marker id="dot" markerWidth="12" markerHeight="12" refX="6" refY="6" '
        'markerUnits="userSpaceOnUse">'
        '<circle cx="6" cy="6" r="5" fill="#1A1A1A"/></marker></defs>'
        + "".join(lines) + "</svg>"
    )
    nodes_html = []
    for name, node in diagram.get("nodes", {}).items():
        if node.get("kind") == "person":
            nodes_html.append(
                f'<div class="dg-node person" data-node="{_esc(name)}" data-kind="person" '
                f'style="left:{node["cx"] - 230}px;top:{node["cy"] - 170}px;">'
                f'<div class="dg-avatar"><img src="{_esc(avatar_file)}" alt="当事人头像"></div>'
                f'<div class="dg-pname">{_esc(name)}</div>'
                f'<div class="dg-psub">{_esc(node.get("sub", ""))}</div></div>'
            )
            continue
        style = (f'left:{node["cx"] - node.get("w", 340) // 2}px;'
                 f'top:{node["cy"] - node.get("h", 180) // 2}px;'
                 f'width:{node.get("w", 340)}px;min-height:{node.get("h", 180)}px;'
                 f'border-width:{node.get("border", 3)}px;')
        cls = f'dg-node {node.get("kind", "org")}' + (" hl" if node.get("highlight") else "")
        why = f'<div class="dg-why">{_esc(node["why"])}</div>' if node.get("why") else ""
        nodes_html.append(
            f'<div class="{cls}" data-node="{_esc(name)}" '
            f'data-kind="{node.get("kind", "org")}" style="{style}">'
            f'<div class="dg-name">{_esc(name)}</div>{why}</div>'
        )
    verbs = "".join(
        f'<div class="dg-verb" style="left:{edge["lx"]}px;top:{edge["ly"]}px;">{_esc(edge["verb"])}</div>'
        for edge in diagram.get("edges", [])
    )
    html = (f'<div class="dg-canvas" style="width:{canvas_w}px;height:{canvas_h}px;'
            f'--dg-fs:{font_scale};">'
            + svg + "".join(nodes_html) + verbs + "</div>")
    return html, canvas_h


# ---------------------------------------------------------------------------
# 四、渲染：Edge 无头截图（哨兵定位内容高度，精确裁剪）
# ---------------------------------------------------------------------------

def find_edge_binary(custom_path: str = "") -> str:
    candidates = ([custom_path] if custom_path else []) + list(_EDGE_CANDIDATES)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("未找到 Edge/Chrome，请在设置中配置 TS_HTML_CARD_EDGE_PATH")


def render_html_to_png(html_path: Path, png_path: Path, *, scale: int = 2,
                       edge_path: str = "") -> tuple[int, int]:
    """对已有 HTML 截图（不修改 HTML）。返回 (宽, 高) 像素。手动改完 card.html 后用这个重出图。"""
    from PIL import Image

    browser = find_edge_binary(edge_path)
    html_path = Path(html_path).resolve()
    url = html_path.as_uri()
    probe_h = 10000

    def _shoot(window_h: int, dsf: int, target: Path) -> Image.Image:
        target = target.resolve()  # Edge 对相对路径的落盘位置不可靠，必须绝对路径
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        # ignore_cleanup_errors：Edge 后台进程可能短暂占用配置目录，清理失败不应阻断出图
        with tempfile.TemporaryDirectory(prefix="html-card-edge-", ignore_cleanup_errors=True) as profile:
            cmd = [
                browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--no-first-run", "--no-default-browser-check",
                f"--user-data-dir={profile}",
                f"--screenshot={target}", f"--window-size={CARD_WIDTH},{window_h}",
                f"--force-device-scale-factor={dsf}", "--virtual-time-budget=5000", url,
            ]
            subprocess.run(cmd, capture_output=True, timeout=180)
            deadline = time.time() + 60
            last_size = -1
            stable = 0
            while time.time() < deadline:
                if target.exists():
                    size = target.stat().st_size
                    if size > 0 and size == last_size:
                        stable += 1
                        if stable >= 2:
                            break
                    else:
                        stable, last_size = 0, size
                time.sleep(0.5)
            if not target.exists():
                raise RuntimeError(f"Edge 截图失败：{target}")
            return Image.open(target)

    # 1) 超高预截图找哨兵行，确定内容高度
    probe_target = png_path.parent / "_probe.png"
    while True:
        probe = _shoot(probe_h, 1, probe_target)
        content_h = _find_sentinel_row(probe)
        if content_h > 0:
            break
        if probe_h >= 16000:
            raise RuntimeError("卡片内容高度超出 16000px，请检查排版")
        probe_h += 3000

    # 2) 按内容高度精确出图，按本图自身的哨兵行裁剪（规避 2x 子像素取整偏差）
    image = _shoot(content_h + 80, scale, png_path)
    row = _find_sentinel_row(image)
    if row > 0:
        image.crop((0, 0, image.width, row)).save(png_path)
    probe_target.unlink(missing_ok=True)
    final = Image.open(png_path)
    return final.size


def _find_sentinel_row(image) -> int:
    pixels = image.load()
    width = image.width
    for y in range(image.height):
        for x in range(0, width, 24):
            r, g, b = pixels[x, y][:3]
            if abs(r - SENTINEL_COLOR[0]) < 40 and g < 40 and abs(b - SENTINEL_COLOR[2]) < 40:
                return y
    return -1


# ---------------------------------------------------------------------------
# 四.5、关系图生图引擎（html_card_relation_engine=image 时启用；失败自动回退 SVG）
# ---------------------------------------------------------------------------

# V6 文案提示词的固定化名名单（当事人=张三，其余按出场序）。关系图节点不允许出现
# 人名（含化名），渲染前统一换成身份标签；SVG 与生图两条引擎共用这套替换。
_PSEUDONYM_PRIMARY = "张三"
_PSEUDONYM_OTHERS = ("李四", "王二麻子", "赵五", "钱六", "孙七", "周八", "吴九", "郑十",
                     "刘十一", "陈十二", "杨十三", "黄十四", "徐十五", "胡十六", "朱十七")
_ALL_PSEUDONYMS = (_PSEUDONYM_PRIMARY,) + _PSEUDONYM_OTHERS

# 化名→身份推断用的称谓关键词：在化名出现处附近窗口里数命中，取频次最高、更具体的词
_ROLE_HINT_KEYWORDS = (
    "直属领导", "部门总监", "同级同事", "大领导", "大老板", "小组长",
    "领导", "上级", "上司", "老板", "总监", "经理", "主管", "主任", "科长", "部长",
    "处长", "局长", "院长", "校长", "行长", "组长", "队长", "前辈", "师傅", "师父",
    "徒弟", "下属", "下级", "同事", "同级", "HR", "人事", "财务", "采购", "行政",
    "法务", "客服", "销售", "客户", "甲方", "乙方", "供应商", "合作方",
    "医生", "护士", "老师", "学生", "律师", "猎头", "中介", "合伙人", "股东",
)


def _relation_context_text(card: CaseCard) -> str:
    """拼接卡片全文（副标题/背景事实/场景/金句/整体结构），供化名的身份推断。"""
    parts: list[str] = [card.subtitle, card.question, card.relation_summary]
    parts.extend(f"{label}：{content}" for label, content in card.facts)
    parts.extend(card.scenes)
    parts.extend(f"{quote} {sign}" for quote, sign in card.quotes)
    parts.extend(rel.why or "" for rel in card.relations)
    return "\n".join(part for part in parts if part)


def _rank_role_labels(name: str, context: str) -> list[str]:
    """在化名出现处 ±14 字窗口内统计身份称谓，按（频次, 词长）降序返回候选。"""
    counts: dict[str, int] = {}
    for match in re.finditer(re.escape(name), context):
        window = context[max(0, match.start() - 14): match.end() + 14]
        for keyword in _ROLE_HINT_KEYWORDS:
            if keyword in window:
                counts[keyword] = counts.get(keyword, 0) + 1
    return [keyword for keyword, _ in
            sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))]


def _normalize_relation_names(card: CaseCard) -> list[RelationEdge]:
    """把关系图节点里的化名换成身份标签（SVG 与生图共用）。

    张三→当事人；其余化名按卡片上下文推断身份称谓（是同事写同事、是领导写领导），
    取频次最高且不与已有节点撞名的候选；完全没有线索时用「相关人」，
    候选全部撞名时加 A/B 后缀（如 同事A）。
    """
    relations = card.relations
    endpoints = ({rel.source.strip() for rel in relations}
                 | {rel.target.strip() for rel in relations})
    if not endpoints & set(_ALL_PSEUDONYMS):
        return relations

    context = _relation_context_text(card)
    mapping: dict[str, str] = {_PSEUDONYM_PRIMARY: "当事人"}
    used = (endpoints - set(_ALL_PSEUDONYMS)) | {"当事人"}

    def convert(name: str) -> str:
        key = name.strip()
        if key in mapping:
            return mapping[key]
        if key not in _PSEUDONYM_OTHERS:
            return name
        candidates = _rank_role_labels(key, context) or ["相关人"]
        label = next((c for c in candidates if c not in used), None)
        if label is None:
            base = candidates[0]
            suffix = "A"
            while f"{base}{suffix}" in used:
                suffix = chr(ord(suffix) + 1)
            label = f"{base}{suffix}"
        mapping[key] = label
        used.add(label)
        return label

    return [RelationEdge(convert(rel.source), rel.verb, convert(rel.target), rel.why)
            for rel in relations]


_RELATION_MODE_DESC = {
    "orbit": "多方群像：当事人是画面正中央的最大圆形节点，其余角色的小圆节点环绕四周，"
             "连线在当事人与各角色之间展开",
    "confront": "双方对峙：当事人与对手方两个大圆节点一左一右对峙，压制方的连线从两个节点"
                "上方跨越并指向被压方，反弹连线从两个节点下方反向打出",
    "tree": "组织层级树：圆形节点按职级自上而下分层排列（权力越大越靠上、描边越粗），"
            "当事人节点用橙色标签条高亮",
}


def _relation_edge_style_text(rel: RelationEdge, ghosts: set[str], center: str) -> str:
    """与渲染器 _edge_visual 同语义的生图文字描述。"""
    if rel.source in ghosts or rel.target in ghosts:
        return "灰色虚线箭头（无形约束）"
    if rel.target == center and rel.source != center:
        return "黑色粗实线箭头（强势方施压）"
    if rel.source == center and rel.target != center:
        if _is_rebound_verb(rel.verb):
            return "灰色虚线箭头（当事人反弹/觉醒）"
        return "黑色细实线箭头（当事人行动）"
    return "黑色细虚线（间接/结构关系）"


def compose_relation_prompt(card: CaseCard, template_text: str = "") -> tuple[str, str]:
    """从案例卡关系数据组装关系图生图提示词（白底报纸风，逐字照抄节点名与动词）。

    template_text 传入选定的提示词模板正文（须含 ${画型}/${节点清单}/${连线清单}
    三个占位符）；缺占位符或未传时回退内置默认模板，保证出卡不中断。
    返回 (prompt, mode)，mode 与 layout_diagram 的拓扑选型一致。
    """
    from ..default_prompt_templates import RELATION_IMAGE_PROMPT_TEMPLATE

    relations = _normalize_relation_names(card)
    layout = layout_diagram(relations, topology=card.topology)
    mode = layout["mode"]
    center = layout["center"]
    ghosts = {name for name in layout["nodes"] if _is_ghost(name)}

    node_lines = []
    # 主节点头像按卡片主人公性别画（IP角色：男/女）；未知时退回中性
    gender_text = (card.gender or "").strip()
    avatar_gender = ("女性" if "女" in gender_text
                     else "男性" if "男" in gender_text else "性别不明的中性")
    for name in layout["nodes"]:
        if name == center:
            note = (f"（主节点：画图中最大的圆形节点，内画一位{avatar_gender}职场人物的单色头像插画"
                    "（发型、轮廓按该性别画，简笔画气质，不刻画五官表情），"
                    "圆外衬一圈同心虚线圆，节点正下方配小标签条写这个身份标签）")
        elif name in ghosts:
            note = "（无形角色/制度/概念：虚线描边的圆形节点，内画与含义呼应的单色细线图标）"
        else:
            note = "（小圆节点：内画与这个身份呼应的单色细线图标，身份标签写在节点正下方）"
        node_lines.append(f"- {name}{note}")

    edge_lines = []
    for rel in relations:
        style = _relation_edge_style_text(rel, ghosts, center)
        line = f"- {rel.source} —({rel.verb})→ {rel.target}：{style}，箭头指向{rel.target}"
        if rel.why:
            line += f"；说明小字：「{rel.why}」"
        edge_lines.append(line)

    template = template_text or RELATION_IMAGE_PROMPT_TEMPLATE
    placeholders = ("${画型}", "${节点清单}", "${连线清单}")
    if not all(placeholder in template for placeholder in placeholders):
        if template_text:
            logger.warning("关系图提示词模板缺少占位符，回退内置默认模板")
        template = RELATION_IMAGE_PROMPT_TEMPLATE
    prompt = (template
              .replace("${画型}", _RELATION_MODE_DESC[mode])
              .replace("${节点清单}", "\n".join(node_lines))
              .replace("${连线清单}", "\n".join(edge_lines)))
    return prompt, mode


def _relation_image_passes_gate(target: Path, threshold: int = 200) -> bool:
    """白底闸门：沿四边两圈密集采样，≥80% 样本为浅色（RGB 各分量 ≥ threshold）视为白底。

    按比例而非全量判定，是为了容忍模板要求的贴边工程细线外框与 L 形角标；
    深色科技风背景会让绝大多数样本变暗，仍会被整体拦截。
    """
    from PIL import Image

    im = Image.open(target).convert("RGB")
    w, h = im.size
    points: list[tuple[int, int]] = []
    for inset in (10, 26):
        step_x = max(24, w // 60)
        step_y = max(24, h // 60)
        for x in range(inset, w - inset, step_x):
            points += [(x, inset), (x, h - inset - 1)]
        for y in range(inset, h - inset, step_y):
            points += [(inset, y), (w - inset - 1, y)]
    if not points:
        return True
    passed = sum(1 for p in points if min(im.getpixel(p)) >= threshold)
    return passed / len(points) >= 0.8


def _validate_relation_image(content: bytes, target: Path) -> tuple[int, int]:
    """校验生图结果（可解码、尺寸达标、非空白、白底）并统一存成 PNG；不达标抛异常。"""
    from PIL import Image, ImageStat

    im = Image.open(io.BytesIO(content))
    im.load()
    if im.width < 512 or im.height < 512:
        raise ValueError(f"生图尺寸异常: {im.width}x{im.height}")
    if ImageStat.Stat(im.convert("L")).stddev[0] < 5:
        raise ValueError("生图疑似空白图")
    im.convert("RGB").save(target, format="PNG")
    if not _relation_image_passes_gate(target):
        target.unlink(missing_ok=True)
        raise ValueError("生图背景不是白底（疑似深色科技风）")
    return im.width, im.height


def _generate_relation_diagram_override(card: CaseCard, assets_dir: Path, models: Any,
                                        size: str,
                                        prompt_template: str = "") -> tuple[dict[str, Any], str]:
    """按模型链生图并校验，返回 (diagram_override, 实际出图的模型名)。

    models 传单个模型或有序模型列表（任务绑定的图片模型链）：
    每个模型最多尝试 2 次（请求失败/校验不过都算失败），全部模型耗尽才抛异常，
    由调用方回退 SVG 确定性渲染——与主图的链式兜底语义一致。
    """
    from ..integrations import image_generation

    model_list = list(models) if isinstance(models, (list, tuple)) else [models]
    model_list = [m for m in model_list if m is not None]
    if not model_list:
        raise RuntimeError("关系图生图未提供可用模型")

    prompt, _mode = compose_relation_prompt(card, template_text=prompt_template)
    target = Path(assets_dir) / "relation.png"
    last_error: Optional[BaseException] = None
    for model in model_list:
        label = getattr(model, "name", None) or getattr(model, "provider", "") or "模型"
        for attempt in (1, 2):
            try:
                generated = asyncio.run(image_generation.generate_image(model, prompt=prompt, size=size))
                width, height = _validate_relation_image(generated.content, target)
                override = {"image_file": "assets/relation.png",
                            "canvas_h": int(DIAGRAM_CANVAS_W * height / width),
                            "nodes": {}, "edges": []}
                return override, label
            except Exception as exc:  # noqa: BLE001 请求失败/校验不过都换下一次
                last_error = exc
                logger.warning("关系图生图未通过（{} 第{}次）：{}", label, attempt, exc)
    raise RuntimeError(f"关系图生图在 {len(model_list)} 个模型上均未成功：{last_error}")


# ---------------------------------------------------------------------------
# 五、成卡编排：解析 -> 建目录 -> 生成 HTML/数据/二维码/头像 -> 截图
# ---------------------------------------------------------------------------

def pick_avatar(gender: str, avatar_dir: Path, *, index: int = 1) -> Optional[Path]:
    """从头像素材目录选头像：女=F+编号、男=M+编号（image/ 文件夹，用户自行更新）。

    index 用于多卡批内轮换，避免同一天几张卡重复同一头像。
    """
    avatar_dir = Path(avatar_dir)
    prefix = "F" if "女" in (gender or "") else "M"
    candidates = [p for p in sorted(avatar_dir.glob(f"{prefix}[0-9]*.*"))
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if not candidates:
        candidates = [p for p in sorted(avatar_dir.glob("*.*"))
                      if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if not candidates:
        return None
    return candidates[(index - 1) % len(candidates)]


def build_qr_png(url: str, target: Path, *, box_size: int = 16) -> None:
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#1A1A1A", back_color="white")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)


def render_case_card(card: CaseCard, out_dir: Path, *, join_url: str = "",
                     avatar_dir: Optional[Path] = None, edge_path: str = "",
                     scale: int = 2, card_index: int = 1,
                     relation_model: Any = None,
                     relation_models: Optional[list[Any]] = None,
                     relation_size: str = "1536x1024",
                     relation_prompt_template: str = "") -> RenderedCard:
    """把一张案例卡渲染成 out_dir/card.png，同时持久化 card.html 与 card_data.json。

    relation_models 传有序图片模型链（推荐，任务绑定的模型序列）、「人物关系」模块
    按链逐家尝试绘制（每家 2 次），全部失败自动回退 SVG，出卡不中断；
    relation_model 为单模型兼容入口，两者都传时以 relation_models 为准。
    relation_prompt_template 为选定的关系图生图提示词模板正文（空则用内置默认）。
    """
    settings = get_settings()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = out_dir / "assets"
    assets.mkdir(exist_ok=True)

    model_chain = [m for m in (relation_models or []) if m is not None]
    if not model_chain and relation_model is not None:
        model_chain = [relation_model]

    avatar_dir = Path(avatar_dir or (Path.cwd() / "image"))
    # 关系图节点统一换成身份标签（张三→当事人、其余化名按上下文推断身份），SVG 与生图共用
    card.relations = _normalize_relation_names(card)
    avatar_src = pick_avatar(card.gender, avatar_dir, index=card_index)
    avatar_name = "avatar" + avatar_src.suffix if avatar_src else None
    if avatar_src:
        shutil.copyfile(avatar_src, assets / avatar_name)
    qr_name = "qr.png"
    build_qr_png(join_url or getattr(settings, "html_card_join_url", "") or "https://md.xinjianhub.cn/#join-us",
                 assets / qr_name)

    diagram_override: Optional[dict[str, Any]] = None
    relation_winner = ""
    if model_chain:
        try:
            diagram_override, relation_winner = _generate_relation_diagram_override(
                card, assets, model_chain, relation_size,
                prompt_template=relation_prompt_template)
        except Exception as exc:  # noqa: BLE001 生图失败回退 SVG，绝不阻断出卡
            logger.warning("关系图生图失败（模型链 {} 家全败），本卡回退 SVG 渲染：{}",
                           len(model_chain), exc)

    html = build_card_html(
        card,
        avatar_file=f"assets/{avatar_name}" if avatar_name else "",
        qr_file=f"assets/{qr_name}",
        diagram_override=diagram_override,
    )
    html_path = out_dir / "card.html"
    html_path.write_text(html, encoding="utf-8")
    data_path = out_dir / "card_data.json"
    data_path.write_text(
        json.dumps({**card.to_dict(), "avatar_index": card_index}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    png_path = out_dir / "card.png"
    width, height = render_html_to_png(html_path, png_path, scale=scale, edge_path=edge_path)
    logger.info("HTML 案例卡已渲染 index={} dir={} size={}x{}", card_index, out_dir, width, height)
    return RenderedCard(html_path=html_path, png_path=png_path, data_path=data_path,
                        width=width, height=height, relation_model=relation_winner)


async def render_case_cards(
    blocks: list[str],
    *,
    execution_id: Optional[int] = None,
    task_name: str = "",
    relation_model: Any = None,
    relation_models: Optional[list[Any]] = None,
    relation_size: str = "1536x1024",
    relation_prompt_template: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """delivery 集成入口：把内容块渲染成完整长卡，返回与生图模型链路兼容的结构。

    relation_models 传有序图片模型链时，每张卡的人物关系图按链逐家尝试（失败换下一家，
    全败单卡回退 SVG）；relation_model 为单模型兼容入口。
    relation_prompt_template 为选定的关系图生图提示词模板正文（空则用内置默认）。
    """
    from ..integrations import image_generation

    settings = get_settings()
    cards = parse_case_blocks(blocks)
    if not cards:
        raise RuntimeError("本地 HTML 引擎未能从内容块解析出任何案例卡")

    root = Path(settings.html_card_output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", (task_name or "card")).strip("-")[:24] or "card"
    suffix = f"-exec{execution_id}" if execution_id else ""
    run_dir = root / f"{stamp}-{slug}{suffix}"

    pairs = [[index] for index in range(1, len(blocks) + 1)]   # 单卡模式：一块=一卡
    generated_items: list[dict[str, Any]] = []
    final_images: list[dict[str, Any]] = []
    cards_meta: list[dict[str, Any]] = []

    for index, card in enumerate(cards, start=1):
        group = pairs[index - 1] if index - 1 < len(pairs) else [index]
        card_dir = run_dir / f"{index:02d}"
        rendered = await asyncio.to_thread(
            render_case_card, card, card_dir, scale=int(settings.html_card_render_scale),
            relation_model=relation_model, relation_models=relation_models,
            relation_size=relation_size,
            relation_prompt_template=relation_prompt_template,
        )
        relation_requested = bool(relation_models or relation_model is not None)
        relation_engine = (
            "image" if (card_dir / "assets" / "relation.png").exists()
            else ("svg-fallback" if relation_requested else "svg"))
        content = rendered.png_path.read_bytes()
        image = image_generation.GeneratedImage(content=content)
        entry = {"block_index": min(group), "image": image, "model": None, "attempts": []}
        generated_items.append(entry)
        final_images.append({
            "parts": list(group),
            "image": image,
            "models": [None],
            "attempts": [[]],
        })
        cards_meta.append({
            "index": index,
            "title": card.title,
            "html_path": str(rendered.html_path),
            "png_path": str(rendered.png_path),
            "size": f"{rendered.width}x{rendered.height}",
            "relation_engine": relation_engine,
            "relation_model": rendered.relation_model or None,
        })

    meta = {
        "engine": "local_html",
        "relation_engine": "image" if (relation_models or relation_model is not None) else "svg",
        "output_dir": str(run_dir),
        "cards": cards_meta,
        "note": "关系图或版式需人工修正时：直接改 card.html，再运行 "
                "python scripts/render_html_card.py render <card.html 所在目录>",
    }
    return generated_items, final_images, meta


async def render_case_cards_as_files(
    case_cards: list[CaseCard],
    *,
    task_name: str = "",
    execution_id: Optional[int] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """话题卡片链路用：把解析好的案例卡渲染成持久化 PNG 文件。

    返回 ([{path,width,height,size_bytes,engine,layout,title,html_path}], meta)。
    产物落在 settings.html_card_output_dir/<时间戳-任务名>/<序号>/，供推送与人工修正复用。
    """
    settings = get_settings()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", (task_name or "card")).strip("-")[:24] or "card"
    suffix = f"-exec{execution_id}" if execution_id else ""
    run_dir = Path(settings.html_card_output_dir) / f"{stamp}-{slug}{suffix}"

    rendered: list[dict[str, Any]] = []
    cards_meta: list[dict[str, Any]] = []
    for index, card in enumerate(case_cards, start=1):
        item = await asyncio.to_thread(
            render_case_card, card, run_dir / f"{index:02d}", card_index=index)
        rendered.append({
            "path": item.png_path,
            "width": item.width,
            "height": item.height,
            "size_bytes": item.png_path.stat().st_size,
            "engine": "html",
            "layout": "single",
            "title": card.title,
            "html_path": item.html_path,
        })
        cards_meta.append({
            "index": index,
            "title": card.title,
            "html_path": str(item.html_path),
            "png_path": str(item.png_path),
            "size": f"{item.width}x{item.height}",
        })
        logger.info("HTML 案例卡已渲染（话题卡片链路）index={} dir={}", index, run_dir / f"{index:02d}")
    meta = {
        "engine": "local_html",
        "output_dir": str(run_dir),
        "cards": cards_meta,
        "note": "关系图或版式需人工修正时：直接改 card.html，再运行 "
                "python scripts/render_html_card.py render <card.html 所在目录>",
    }
    return rendered, meta
