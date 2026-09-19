"""html_case_card_service 单元测试：V5 文案块解析 + 关系图自动布局（不含 Edge 渲染）。"""

from app.services import html_case_card_service as svc


def _sample_blocks() -> list[str]:
    top = """【拼卡·上】
IP角色：女
连60万赔偿都不要，这辞职是逃命还是犯病？
存款260万垫底，为什么还是撑不住？
关键词：超额责任心、裸辞、2N赔偿

背景概述：
当事人｜33岁，银行软件开发10年，税后年薪35万
身心｜去年7月确诊中度抑郁焦虑，腰椎间盘突出急性发作
筹码｜无固定期限合同，被辞退可拿约60万（2N）

重点项目刚投产，她身心耗尽，周五前就要交辞职信。
60万赔偿摆在面前，她连争取的力气都没有。

周五辞职信就要交了，这封信你拦不拦？

人物关系：
超额责任心 ——(隐形压制)→ 当事人：请假恐惧，摆烂有负罪感
当事人 ——(主动弃权)→ 60万赔偿：连被裁拿2N的力气都不想花
整体结构：这不是钱的问题，是结构问题"""
    bottom = """【拼卡·下】
分析过程：
1、「先逃命再说」：先把人捞出来，这是多数人的第一反应
2、「这么想就输了」：状态越差，越不该做重大决定

解决方案：
1、「先去复查」：周五前先挂精神科复查
2、「休完假期」：年假病假一次休完

金句：
天不会塌，收起你该死的超额责任心。
—— @李四"""
    return [
        f"<!-- CONTENT_BLOCK_START -->\n{top}\n<!-- CONTENT_BLOCK_END -->",
        f"<!-- CONTENT_BLOCK_START -->\n{bottom}\n<!-- CONTENT_BLOCK_END -->",
    ]


def test_parse_case_blocks_merges_top_and_bottom():
    cards = svc.parse_case_blocks(_sample_blocks())
    assert len(cards) == 1
    card = cards[0]
    assert card.gender == "女"
    assert card.title == "连60万赔偿都不要，这辞职是逃命还是犯病？"
    assert card.subtitle == "存款260万垫底，为什么还是撑不住？"
    assert card.keywords == ["超额责任心", "裸辞", "2N赔偿"]
    assert [k for k, _ in card.facts] == ["当事人", "身心", "筹码"]
    assert len(card.scenes) == 2
    assert card.question == "周五辞职信就要交了，这封信你拦不拦？"
    assert len(card.relations) == 2
    assert card.relation_summary == "整体结构：这不是钱的问题，是结构问题"
    assert card.analysis == [
        ("先逃命再说", "先把人捞出来，这是多数人的第一反应"),
        ("这么想就输了", "状态越差，越不该做重大决定"),
    ]
    assert card.solutions[0] == ("先去复查", "周五前先挂精神科复查")
    assert card.quotes == [("天不会塌，收起你该死的超额责任心。", "@李四")]


def test_parse_reverse_relation_arrow():
    card = svc.CaseCard()
    edge = svc._parse_relation_line("主任 ←——(互相拿捏)—— 医务科：一个想瞒、一个想查")
    assert edge is not None
    assert edge.source == "医务科" and edge.target == "主任" and edge.verb == "互相拿捏"


def test_layout_diagram_centers_person_and_draws_edges():
    cards = svc.parse_case_blocks(_sample_blocks())
    layout = svc.layout_diagram(cards[0].relations)
    nodes = layout["nodes"]
    assert nodes["当事人"]["kind"] == "person"
    assert nodes["超额责任心"]["kind"] == "ghost"   # 责任心命中无形角色关键词
    assert nodes["60万赔偿"]["kind"] == "ghost"      # 赔偿命中无形角色关键词
    assert len(layout["edges"]) == 2
    for edge in layout["edges"]:
        assert edge["style"] == "solid"              # 与当事人相连的边一律实线
        length = ((edge["x2"] - edge["x1"]) ** 2 + (edge["y2"] - edge["y1"]) ** 2) ** 0.5
        assert length >= 60, "连线过短，箭头与标签施展不开"


def test_split_title_prefers_comma_break():
    l1, l2 = svc._split_title("连60万赔偿都不要，这辞职是逃命还是犯病？")
    assert l1 == "连60万赔偿都不要，"
    assert l2 == "这辞职是逃命还是犯病？"
    short_l1, short_l2 = svc._split_title("裸辞后悔了")
    assert short_l1 == "裸辞后悔了" and short_l2 == ""


def test_case_card_roundtrip():
    cards = svc.parse_case_blocks(_sample_blocks())
    data = cards[0].to_dict()
    restored = svc.CaseCard.from_dict(data)
    assert restored.to_dict() == data


def _single_card_block() -> str:
    """V6 单卡完整内容块（无拼卡标记）。"""
    return """<!-- CONTENT_BLOCK_START -->
IP角色：女
存款260万却连60万赔偿都不要
副标题为什么还是撑不住？
关键词：超额责任心、裸辞、2N赔偿

背景概述：
当事人｜33岁，银行软件开发10年
身心｜确诊中度抑郁焦虑
筹码｜无固定期限合同，被裁可拿60万

重点项目投产，她身心耗尽。
周五前就要交辞职信。

换成你，这封信你交不交？

人物关系：
超额责任心 ——(隐形压制)→ 当事人：请假恐惧，摆烂有负罪感
整体结构：这不是钱的问题，是结构问题

分析过程：
1、「先逃命再说」：先把人捞出来，多数人的第一反应
2、「这么想就输了」：状态越差，越不该做重大决定

解决方案：
1、「先去复查」：周五前先挂精神科复查
2、「休完假期」：年假病假一次休完

金句：
天不会塌，收起你该死的超额责任心。
—— @李四
<!-- CONTENT_BLOCK_END -->"""


def test_parse_single_card_block_without_markers():
    """V6 单卡格式：一个内容块=一张完整卡（含分析/方案/金句）。"""
    blocks = [
        "<!-- CONTENT_BLOCK_START -->\n" + _single_card_block().split("<!-- CONTENT_BLOCK_START -->")[1]
    ]
    blocks = [_single_card_block()]
    cards = svc.parse_case_blocks(blocks)
    assert len(cards) == 1
    card = cards[0]
    assert card.gender == "女"
    assert card.title == "存款260万却连60万赔偿都不要"
    assert len(card.facts) == 3 and len(card.scenes) == 2
    assert len(card.relations) == 1 and card.relation_summary
    assert len(card.analysis) == 2 and len(card.solutions) == 2 and len(card.quotes) == 1


def test_topic_card_validation_accepts_content_blocks():
    """话题卡片任务的输出校验：内容块格式不再要求 JSON。"""
    from types import SimpleNamespace

    from app.scheduler.prompts import PromptFlowMixin

    task = SimpleNamespace(task_type="topic_card", topic_style_config=None)
    job = SimpleNamespace()
    flow = PromptFlowMixin()
    flow._validate_ai_output(task=task, job=job, summary=_single_card_block(), html_required=False)

    bad = "<!-- CONTENT_BLOCK_START -->\n随便一段没有槽位的文字\n<!-- CONTENT_BLOCK_END -->"
    try:
        flow._validate_ai_output(task=task, job=job, summary=bad, html_required=False)
    except ValueError as exc:
        assert "案例卡" in str(exc)
    else:
        raise AssertionError("空槽内容块应当校验失败")


def test_layout_curve_mixes_arch_and_straight():
    """curve 模式智能混合：与当事人相连的辐射线用弧线，卫星之间的连线用直线。"""
    cards = svc.parse_case_blocks(_sample_blocks())
    cards[0].relations.append(
        svc.RelationEdge("无固定期限合同", "反向锁死", "公司", "想让谁走，得先掏出2N赔偿"))
    layout = svc.layout_diagram(cards[0].relations, arrow_style="curve")
    curved = [e for e in layout["edges"] if "qx" in e]
    straight = [e for e in layout["edges"] if "qx" not in e]
    # 两条当事人辐射线为弧线
    assert {e["verb"] for e in curved} == {"隐形压制", "主动弃权"}
    # 卫星之间的连线为直线（虚线+圆点）
    assert len(straight) == 1 and straight[0]["verb"] == "反向锁死"

    layout_solid = svc.layout_diagram(cards[0].relations, arrow_style="solid")
    assert all("qx" not in e for e in layout_solid["edges"])


def test_topology_marker_split():
    """「整体结构」行可选拓扑标记：剥离标记、归一化别名、无标记原样返回。"""
    summary, topology = svc._split_topology_marker("整体结构：〔对峙〕这不是义气问题，是把柄问题")
    assert topology == "对峙"
    assert summary == "整体结构：这不是义气问题，是把柄问题"
    summary, topology = svc._split_topology_marker("整体结构：这不是钱的问题，是结构问题")
    assert topology == "" and summary == "整体结构：这不是钱的问题，是结构问题"
    summary, topology = svc._split_topology_marker("整体结构：【层级树】汇报线决定生死")
    assert topology == "层级" and summary == "整体结构：汇报线决定生死"


def test_parse_topology_marker_into_card():
    blocks = ["""<!-- CONTENT_BLOCK_START -->
帮领导代打卡，是义气还是把柄？
一次顺手，换来的可能是终身拿捏
关键词：代打卡、职场边界

人物关系：
主任 ——(隐形拿捏)→ 当事人：代打卡的把柄在他手里
整体结构：〔对峙〕这不是义气问题，是把柄问题
<!-- CONTENT_BLOCK_END -->"""]
    card = svc.parse_case_blocks(blocks)[0]
    assert card.topology == "对峙"
    assert card.relation_summary == "整体结构：这不是义气问题，是把柄问题"


def test_layout_confrontation_for_two_parties():
    """只有两方时自动切「双方对峙」：左右对峙、压制粗实线上拱、反弹灰虚线下打。"""
    relations = [
        svc.RelationEdge("主任", "隐形拿捏", "当事人", "代打卡的把柄在他手里"),
        svc.RelationEdge("当事人", "摊牌拒绝", "主任", "不再替他打卡"),
    ]
    layout = svc.layout_diagram(relations)
    assert layout["mode"] == "confront"
    nodes = layout["nodes"]
    assert nodes["当事人"]["cx"] < nodes["主任"]["cx"]   # 当事人左、对手右
    pressure = next(e for e in layout["edges"] if e["target"] == "当事人")
    assert pressure["stroke"] == "#1A1A1A" and pressure["width"] == 6 and not pressure["dash"]
    assert pressure["y2"] < nodes["当事人"]["cy"]        # 压制线锚在圆环顶（上拱）
    rebound = next(e for e in layout["edges"] if e["source"] == "当事人")
    assert rebound["stroke"] == "#6B655C" and rebound["dash"]
    assert rebound["y1"] > nodes["当事人"]["cy"]         # 反弹线锚在名字下方（下打）


def test_layout_tree_by_topology_marker():
    """〔层级〕标记切「组织层级树」：权力越大越靠上、描边越粗，当事人高亮、无形角色沉底。"""
    relations = [
        svc.RelationEdge("大老板", "隔空施压", "总监", "裁员名额层层下压"),
        svc.RelationEdge("总监", "转嫁风险", "当事人", "背锅侠选最没背景的"),
        svc.RelationEdge("当事人", "留痕自保", "总监", "邮件抄送全员"),
        svc.RelationEdge("绩效制度", "隐形筛选", "当事人", "强制分布必有垫底"),
    ]
    layout = svc.layout_diagram(relations, topology="层级")
    assert layout["mode"] == "tree"
    nodes = layout["nodes"]
    assert nodes["大老板"]["cy"] < nodes["总监"]["cy"] < nodes["当事人"]["cy"]
    assert nodes["大老板"]["border"] > nodes["总监"]["border"] > nodes["当事人"]["border"]
    assert nodes["当事人"]["highlight"] is True
    assert nodes["绩效制度"]["cy"] > nodes["当事人"]["cy"]   # 无形角色沉底
    ghost_edge = next(e for e in layout["edges"] if e["source"] == "绩效制度")
    assert ghost_edge["stroke"] == "#6B655C" and ghost_edge["dash"]


def test_orbit_line_semantics_follow_v1_rules():
    """群像模式线语义：无形角色灰虚线、压向当事人粗实线、反弹动词灰虚线。"""
    relations = [
        svc.RelationEdge("超额责任心", "隐形压制", "当事人", "拒绝就有负罪感"),
        svc.RelationEdge("当事人", "硬刚拒绝", "同事", "当场顶回去"),
        svc.RelationEdge("同事", "递刀子", "当事人", "看戏不嫌事大"),
    ]
    layout = svc.layout_diagram(relations)
    assert layout["mode"] == "orbit"
    by_verb = {e["verb"]: e for e in layout["edges"]}
    assert by_verb["隐形压制"]["stroke"] == "#6B655C" and by_verb["隐形压制"]["dash"]
    assert by_verb["递刀子"]["width"] == 6 and not by_verb["递刀子"]["dash"]
    assert by_verb["硬刚拒绝"]["stroke"] == "#6B655C" and by_verb["硬刚拒绝"]["dash"]


def test_case_card_topology_roundtrip():
    cards = svc.parse_case_blocks(_sample_blocks())
    card = cards[0]
    card.topology = "对峙"
    restored = svc.CaseCard.from_dict(card.to_dict())
    assert restored.topology == "对峙"


def test_layout_shrinks_font_when_nodes_overflow():
    """节点越出画布边界时自动逐档缩小图内字号，直到收进边界。"""
    relations = [
        svc.RelationEdge("手绘三年路线图达人", "隐形压制", "当事人", "每多赚一块钱就要多投入一份成本"),
        svc.RelationEdge("同事", "冷眼旁观", "当事人", "看戏不嫌事大"),
    ]
    layout = svc.layout_diagram(relations)
    assert layout["font_scale"] < 1.0
    for node in layout["nodes"].values():
        half = 230 if node["kind"] == "person" else node["w"] / 2
        assert node["cx"] - half >= 8, "节点左缘越界"
        assert node["cx"] + half <= svc.DIAGRAM_CANVAS_W - 8, "节点右缘越界"


def test_normalize_relation_names_maps_pseudonyms_to_role_labels():
    """关系图节点统一身份标签：张三→当事人，其余化名按卡片上下文推断身份称谓。"""
    card = svc.CaseCard(
        facts=[("张三", "内审P7，遭遇能力极强的同级同事李四")],
        scenes=["李四越权盘活了死局。"],
        relations=[
            svc.RelationEdge("张三", "隐形压制", "主任", "每步都要审批"),
            svc.RelationEdge("李四", "通风报信", "王二麻子", "串通一气"),
        ],
    )
    normalized = svc._normalize_relation_names(card)
    assert [(r.source, r.target) for r in normalized] == [
        ("当事人", "主任"), ("同级同事", "相关人")]   # 李四→同级同事；王二麻子无线索→相关人
    # 原列表不被修改（调用方自行决定是否回写）
    assert card.relations[0].source == "张三"


def test_normalize_relation_names_skips_collision_with_existing_node():
    """推断出的身份与已有节点撞名时，顺延到次优候选（而不是合并成同一节点）。"""
    card = svc.CaseCard(
        scenes=["李四是科室主任，管着排班表。"],
        relations=[
            svc.RelationEdge("李四", "隐形拿捏", "张三", "把柄在手"),
            svc.RelationEdge("同事", "背后蛐蛐", "李四", "看戏不嫌事大"),
        ],
    )
    normalized = svc._normalize_relation_names(card)
    names = sorted({r.source for r in normalized} | {r.target for r in normalized})
    assert "李四" not in names and "张三" not in names
    # 「主任」不与已有「同事」节点撞名，直接可用
    assert "主任" in names and "当事人" in names and "同事" in names


def test_normalize_relation_names_leaves_role_labels_untouched():
    card = svc.CaseCard(relations=[svc.RelationEdge("当事人", "硬刚", "直属领导", "不接甩锅")])
    normalized = svc._normalize_relation_names(card)
    assert (normalized[0].source, normalized[0].target) == ("当事人", "直属领导")
