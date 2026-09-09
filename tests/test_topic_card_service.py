"""topic_card_service 纯函数特征测试：JSON 解析、风格配置、脱敏规则、文本/图片布局。"""

from __future__ import annotations

import json

import pytest

from app.services import topic_card_service as tcs


def _topic_card(**overrides):
    card = {
        "topic_type": "work_methods",
        "tags": ["职场"],
        "time_range": "08:02 - 14:06",
        "title": "工作总背锅？你的SOP该升级了",
        "initiator": "苏云",
        "initiator_label": "发起人",
        "trigger_quote": "客户又投诉了",
        "summary": "群友讨论了如何用 SOP 减少背锅。",
        "points": ["先留痕", "再对齐"],
        "participants": ["苏云", "阿南plus"],
        "highlight_quote": "你的进步只来自于得到了老师的认可。",
        "highlight_speaker": "张三",
    }
    card.update(overrides)
    return {"cards": [card]}


def test_parse_topic_cards_normalizes():
    raw = "```json\n" + json.dumps(_topic_card(), ensure_ascii=False) + "\n```"
    cards = tcs.parse_topic_cards(raw)
    assert len(cards) == 1
    card = cards[0]
    assert card["id"] == "card-01"
    assert card["style_key"] in tcs.VALID_STYLE_KEYS
    assert card["theme"] in tcs.VALID_THEMES
    assert card["section1_title"] == "抛出探讨"
    assert card["highlight_label"] == "高光时刻"


def test_parse_topic_cards_requires_cards_array():
    with pytest.raises(ValueError, match="cards"):
        tcs.parse_topic_cards(json.dumps({"foo": 1}, ensure_ascii=False))


def test_parse_topic_cards_reports_missing_fields():
    bad = {"cards": [{"title": "只有标题"}]}
    with pytest.raises(ValueError, match="缺少字段"):
        tcs.parse_topic_cards(json.dumps(bad, ensure_ascii=False))


def test_case_card_detected_by_field_signature():
    case = {
        "title": "案例标题",
        "trigger_quote": "起因",
        "background": "背景说明",
        "relationship": "人物关系说明",
        "analysis": ["第一条分析"],
        "solution": "解决方案",
        "highlight_quote": "金句",
        "highlight_speaker": "李四",
        "participants": ["李四"],
    }
    raw = json.dumps({"cards": [case]}, ensure_ascii=False)
    cards = tcs.parse_topic_cards(raw)
    assert cards[0]["card_format"] == "case"
    assert cards[0]["highlight_label"] == "金句"
    assert "背景说明" in cards[0]["summary"]


def test_case_card_masks_person_names():
    case = {
        "card_format": "case",
        "title": "案例标题",
        "trigger_quote": "苏云 提出了问题",
        "background": "苏云 和 阿南plus 争执不下",
        "relationship": "苏云 是当事人",
        "analysis": ["阿南plus 认为流程有问题"],
        "solution": "苏云 决定先对齐 SOP",
        "highlight_quote": "张三 总结了经验",
        "highlight_speaker": "张三",
        "initiator": "苏云",
        "participants": ["阿南plus"],
    }
    raw = json.dumps({"cards": [case]}, ensure_ascii=False)
    card = tcs.parse_topic_cards(raw)[0]
    assert "苏云" not in card["background"]
    assert "苏某" in card["background"]
    assert "阿某" in card["analysis"][0]
    assert card["initiator"] == "苏某"


def test_mask_person_name_rules():
    assert tcs._mask_person_name("苏云") == "苏某"
    assert tcs._mask_person_name("欧阳晨") == "欧阳某"
    assert tcs._mask_person_name("Cici_") == "C某"
    assert tcs._mask_person_name("A") == "A"
    assert tcs._mask_person_name("") == ""
    assert tcs._mask_person_name("@阿南") == "阿某"


def test_maybe_mask_keeps_generic_and_alias_names():
    assert tcs._maybe_mask_name("群友A") == "群友A"
    assert tcs._maybe_mask_name("网友12") == "网友12"
    assert tcs._maybe_mask_name("张三") == "张三"
    assert tcs._maybe_mask_name("王二麻子") == "王二麻子"
    assert tcs._maybe_mask_name("赵大宝") == "赵某"


def test_name_masks_replace_longest_first_with_mentions():
    masks = tcs._build_name_masks(["小王", "王小明", "老李"])
    assert masks[0][0] == "王小明"
    text = "@王小明 和 @小王 找 老李 开会"
    masked = tcs._apply_name_masks(text, masks)
    assert "王小明" not in masked.replace("王某", "")
    assert "老李" not in masked


def test_normalize_topic_style_config_defaults_and_roundtrip():
    default = tcs.normalize_topic_style_config(None)
    assert default == tcs.DEFAULT_TOPIC_STYLE_CONFIG
    # 部分覆盖：未指定的类目回落默认配置，且结果始终包含全部四个类目
    custom = {"industry_business": {"style_key": "style_c", "theme": "green"}}
    raw = json.dumps(custom, ensure_ascii=False)
    merged = tcs.normalize_topic_style_config(raw)
    assert merged["industry_business"] == custom["industry_business"]
    assert len(merged) == len(tcs.DEFAULT_TOPIC_STYLE_CONFIG)
    for key, value in tcs.DEFAULT_TOPIC_STYLE_CONFIG.items():
        if key != "industry_business":
            assert merged[key] == value


def test_build_text_messages_layouts():
    raw = json.dumps(_topic_card(), ensure_ascii=False)
    card = tcs.parse_topic_cards(raw)[0]
    cards = [dict(card, id=f"card-{i:02d}") for i in range(1, 5)]
    per_topic = tcs.build_text_messages(cards[:2], layout="per_topic", threshold=3)
    assert len(per_topic) == 2
    merged = tcs.build_text_messages(cards, layout="auto", threshold=3)
    assert len(merged) == 1
    assert "---" in merged[0]
    single_card = tcs.build_text_messages([card], layout="auto", threshold=3)
    assert len(single_card) == 1
    assert "### " in single_card[0]
    assert "讨论时段" in single_card[0]


def test_resolve_image_layout():
    assert tcs.resolve_image_layout("auto", 2, 3) == "single"
    assert tcs.resolve_image_layout("auto", 4, 3) == "collection"
    assert tcs.resolve_image_layout("single", 9, 1) == "single"
    assert tcs.resolve_image_layout("collection", 1, 9) == "collection"
    assert tcs.resolve_image_layout("bogus", 5, 3) == "single"


def test_parse_topic_cards_clips_overlong_fields():
    raw = json.dumps(_topic_card(title="长" * 100, summary="摘" * 500), ensure_ascii=False)
    card = tcs.parse_topic_cards(raw)[0]
    assert len(card["title"]) == 60
    assert len(card["summary"]) == 260
