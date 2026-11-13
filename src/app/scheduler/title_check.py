"""日报标题-正文一致性校验（纯规则，不调用 LLM）。

深度话题卡片的标题由模型一次性生成整篇 HTML 时写出，长上下文下偶发
「串扰」：把相邻话题的金句/概念写进本卡标题（如 2026-11-04 日报话题 2
的标题引用了话题 3 的「升职四步法」，而本卡正文完全没有该内容）。

判定用 bigram 覆盖率做相对比较：若标题与其他卡片正文的匹配度显著高于
与自己正文的匹配度，判为串扰。阈值基于 2026-11-02/03/04 三期真实日报
校准——正常标题 own 0.18~0.57 且显著高于 other_max（最接近的一例
own=0.48 vs other=0.51，差 -0.03 不触发）；已知串扰标题 own=0.23 而
other_max=0.54，差 +0.31。

仅处理 HTML 日报（h4 卡片，与 buildToc 目录同源）；无 h4 或卡片数不足
2 张时跳过校验，返回全部通过。
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

_H4_RE = re.compile(r"<h4[^>]*>(.*?)</h4>", re.IGNORECASE | re.DOTALL)
_NOISE_RE = re.compile(
    r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->",
    re.IGNORECASE | re.DOTALL,
)

# 判定阈值（校准依据见模块 docstring）
CROSSED_MARGIN = 0.10
LOW_OWN = 0.15
LOW_OWN_OTHER = 0.25


@dataclass
class TopicCard:
    index: int  # 1 起始，按 h4 文档顺序
    title: str
    body_text: str


@dataclass
class TitleCheckResult:
    card: TopicCard
    own_score: float
    other_max_score: float
    other_card_index: Optional[int]  # 1 起始；无其他卡片时为 None
    passed: bool
    reason: str = ""


def extract_topic_cards(summary: str) -> List[TopicCard]:
    """按 h4 文档顺序切出话题卡片（标题 + 到下一个 h4 为止的正文纯文本）。"""
    if not summary:
        return []
    matches = list(_H4_RE.finditer(summary))
    cards: List[TopicCard] = []
    for pos, match in enumerate(matches):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(summary)
        body = _to_plain_text(summary[match.end():end])
        cards.append(TopicCard(index=pos + 1, title=title, body_text=body))
    return [c for c in cards if c.title]


def check_report_titles(summary: str) -> List[TitleCheckResult]:
    """逐卡校验标题归属；不足 2 张卡时无法做相对比较，全部视为通过。"""
    cards = extract_topic_cards(summary)
    if len(cards) < 2:
        return [
            TitleCheckResult(card=c, own_score=1.0, other_max_score=0.0,
                             other_card_index=None, passed=True,
                             reason="insufficient_cards")
            for c in cards
        ]
    results: List[TitleCheckResult] = []
    for card in cards:
        own, _ = _coverage(card.title, card.body_text)
        other_max, other_index = 0.0, None
        for other in cards:
            if other.index == card.index:
                continue
            score, _ = _coverage(card.title, other.body_text)
            if score > other_max:
                other_max, other_index = score, other.index
        passed, reason = True, ""
        if other_max >= own + CROSSED_MARGIN:
            passed, reason = False, "crossed"
        elif own < LOW_OWN and other_max >= LOW_OWN_OTHER:
            passed, reason = False, "low_own"
        results.append(TitleCheckResult(
            card=card, own_score=round(own, 4), other_max_score=round(other_max, 4),
            other_card_index=other_index, passed=passed, reason=reason,
        ))
    return results


def replace_card_title(summary: str, card_index: int, new_title: str) -> Optional[str]:
    """把第 card_index 张卡的 h4 标题替换为 new_title（保留原 h4 属性）；找不到时返回 None。"""
    matches = list(_H4_RE.finditer(summary))
    if not 1 <= card_index <= len(matches):
        return None
    match = matches[card_index - 1]
    whole = match.group(0)
    open_end = whole.index(">") + 1  # 开标签 `<h4 ...>` 结束处
    new_whole = whole[:open_end] + html_lib.escape(new_title) + "</h4>"
    return summary[:match.start()] + new_whole + summary[match.end():]


def _coverage(title: str, body: str) -> Tuple[float, List[Tuple[str, int, int]]]:
    """标题各内容片段在正文中的 bigram 覆盖率（0~1）及逐片段命中详情。"""
    normalized_body = _normalize(body)
    runs = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}|\d+(?:\.\d+)?%?", _normalize(title))
    detail: List[Tuple[str, int, int]] = []
    scores: List[float] = []
    for run in runs:
        grams = [run[i:i + 2] for i in range(len(run) - 1)] or [run]
        hit = sum(1 for g in grams if g in normalized_body)
        detail.append((run, hit, len(grams)))
        scores.append(hit / len(grams))
    overall = sum(scores) / len(scores) if scores else 1.0
    return overall, detail


def _to_plain_text(fragment: str) -> str:
    text = _NOISE_RE.sub("", fragment)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _normalize(text: str) -> str:
    text = html_lib.unescape(unicodedata.normalize("NFKC", text))
    return re.sub(r"\s+", "", text)
