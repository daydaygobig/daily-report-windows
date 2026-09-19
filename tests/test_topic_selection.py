"""单话题执行筛选与话题摘要：案例卡序号/关键词筛选、执行 meta 话题列表。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.scheduler.parsing import (
    _filter_cards_by_topic,
    _filter_case_cards_by_topic,
)
from app.services.execution_service import _topic_card_meta


def _case_cards(*titles: str):
    return [SimpleNamespace(title=title) for title in titles]


class TestFilterCaseCardsByTopic:
    def test_numeric_index_selects_one_card(self):
        cards = _case_cards("跨部门协作的边界感", "复盘不是追责", "向上管理")

        assert _filter_case_cards_by_topic(cards, "3") == [cards[2]]
        assert _filter_case_cards_by_topic(cards, " 2 ") == [cards[1]]

    def test_numeric_index_out_of_range_returns_empty(self):
        cards = _case_cards("跨部门协作的边界感", "复盘不是追责")

        assert _filter_case_cards_by_topic(cards, "3") == []
        assert _filter_case_cards_by_topic(cards, "0") == []

    def test_keyword_matches_title_substring_case_insensitive(self):
        cards = _case_cards("跨部门协作的边界感", "复盘不是追责")

        assert _filter_case_cards_by_topic(cards, "边界感") == [cards[0]]
        assert _filter_case_cards_by_topic(cards, "复盘") == [cards[1]]
        assert _filter_case_cards_by_topic(cards, "跨部门") == [cards[0]]

    def test_keyword_without_match_returns_empty(self):
        cards = _case_cards("跨部门协作的边界感")

        assert _filter_case_cards_by_topic(cards, "不存在的关键词") == []

    def test_title_missing_or_empty_is_safe(self):
        cards = [SimpleNamespace(title=""), SimpleNamespace(title=None), SimpleNamespace()]

        assert _filter_case_cards_by_topic(cards, "1") == [cards[0]]
        assert _filter_case_cards_by_topic(cards, "任意") == []


class TestTopicCardMeta:
    def test_case_block_execution_lists_case_card_titles(self):
        meta = {
            "type": "topic_card",
            "format": "case_blocks",
            "case_cards": [
                {"title": "跨部门协作的边界感", "keywords": ["协作", "边界"]},
                {"title": "复盘不是追责", "keywords": []},
            ],
        }
        execution = SimpleNamespace(raw_response=json.dumps(meta, ensure_ascii=False))

        summary = _topic_card_meta(execution)

        assert summary is not None
        assert summary["话题数量"] == 2
        assert [item["标题"] for item in summary["话题列表"]] == [
            "跨部门协作的边界感",
            "复盘不是追责",
        ]
        assert summary["话题列表"][0]["短标签"] == ["协作", "边界"]

    def test_json_card_execution_unchanged(self):
        meta = {
            "type": "topic_card",
            "cards": [
                {"title": "工作总背锅？你的SOP该升级了", "topic_type": "work_methods"},
            ],
        }
        execution = SimpleNamespace(raw_response=json.dumps(meta, ensure_ascii=False))

        summary = _topic_card_meta(execution)

        assert summary is not None
        assert summary["话题数量"] == 1
        assert summary["话题列表"][0]["标题"] == "工作总背锅？你的SOP该升级了"

    def test_non_topic_card_execution_returns_none(self):
        execution = SimpleNamespace(raw_response=json.dumps({"type": "report"}))

        assert _topic_card_meta(execution) is None


class TestFilterCardsByTopicParity:
    def test_json_cards_still_support_index_and_keyword(self):
        cards = [{"title": "话题甲"}, {"title": "话题乙"}]

        assert _filter_cards_by_topic(cards, "2") == [{"title": "话题乙"}]
        assert _filter_cards_by_topic(cards, "甲") == [{"title": "话题甲"}]
