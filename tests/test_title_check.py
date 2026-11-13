"""title_check：日报标题-正文一致性校验的单元测试。"""

from app.scheduler.title_check import (
    check_report_titles,
    extract_topic_cards,
    replace_card_title,
)


def _doc(cards):
    body = "".join(
        f"<h4 class=\"text-xl\">{title}</h4><div class=\"content-preview collapsed\">{text}</div>"
        for title, text in cards
    )
    return (
        "<!DOCTYPE html><html><head><style>/* 话题标题样式 */</style>"
        "<script>var a='话题';</script></head><body>"
        f"<section>{body}</section>"
        "<footer>漫道日报</footer></body></html>"
    )


def test_提取话题卡片_忽略脚本样式与标签():
    html = _doc([("越级汇报犯忌", "正文越级汇报权力结构"), ("双线汇报被孤立", "正文双线汇报破冰")])
    cards = extract_topic_cards(html)
    assert [c.title for c in cards] == ["越级汇报犯忌", "双线汇报被孤立"]
    # 正文中的 script/style 内容与 html 注释不参与纯文本
    assert "var" not in cards[0].body_text
    assert "样式" not in cards[0].body_text


def test_正常标题全部通过():
    html = _doc([
        ("搞定跨国汇报靠预判", "跨国汇报预判术今天上午和美国的大领导汇报讨论项目预判对方问题"),
        ("别迷信投人成事靠关系网", "投人本质是投社会关系找她就能帮我做冰箱贴背后的关系网"),
        ("AI把成本打平后值钱的是懂人心", "AI时代的商业本质成本打平之后真正稀缺的是懂人心组织与战略"),
    ])
    results = check_report_titles(html)
    assert all(r.passed for r in results)
    assert all(r.reason == "" for r in results)


def test_串扰标题被识别():
    # 话题2标题引用了话题3正文的「四步法」概念，自身正文毫无出处
    html = _doc([
        ("越级汇报犯忌先看透领导斗法", "越级汇报权力结构猜忌链向上管理大老板点名直属领导"),
        ("升职四步法关键在第三步", "复盘悖论主人翁心态职场窗口期整理全了再问永远开不了口"),
        ("双线汇报被孤立先破冰", "双线汇报升迁四步法第三步找到说了算的人送礼破冰站队"),
    ])
    results = check_report_titles(html)
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert failed[0].card.index == 2
    assert failed[0].reason == "crossed"
    assert failed[0].other_card_index == 3


def test_单卡片跳过校验():
    html = _doc([("唯一话题", "正文内容")])
    results = check_report_titles(html)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].reason == "insufficient_cards"


def test_无卡片时返回空():
    assert check_report_titles("<p>没有话题的页面</p>") == []
    assert check_report_titles("") == []


def test_替换标题保留h4属性并转义():
    html = _doc([("旧标题", "正文"), ("另一个", "正文二")])
    updated = replace_card_title(html, 1, "新标题<测试>")
    assert updated is not None
    assert '<h4 class="text-xl">新标题&lt;测试&gt;</h4>' in updated
    assert "旧标题" not in updated
    assert replace_card_title(html, 5, "越界") is None
