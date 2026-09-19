"""关系图生图引擎（方案A）：提示词组装、白底闸门、重试与 SVG 回退（不调真实生图接口）。"""

import io
from types import SimpleNamespace

from PIL import Image, ImageDraw

from app.services import html_case_card_service as svc


def _png_bytes(color, size=(1024, 768), with_mark: bool = False, mark=(26, 26, 23)) -> bytes:
    im = Image.new("RGB", size, color)
    if with_mark:
        ImageDraw.Draw(im).rectangle([100, 100, 300, 300], fill=mark)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _sample_card() -> svc.CaseCard:
    return svc.CaseCard.from_dict({
        "title": "帮领导代打卡，是义气还是把柄？",
        "gender": "男",
        "relations": [
            {"source": "主任", "verb": "隐形拿捏", "target": "当事人", "why": "把柄在他手里"},
            {"source": "当事人", "verb": "摊牌拒绝", "target": "主任", "why": "不再代打卡"},
        ],
    })


def test_compose_relation_prompt_pins_white_bg_and_copies_texts():
    prompt, mode = svc.compose_relation_prompt(_sample_card())
    assert mode == "confront"                    # 两方故事自动对峙画型
    assert "#FFFFFF" in prompt                   # 背景色号钉死（对抗深色科技风）
    assert "主任" in prompt and "当事人" in prompt
    assert "隐形拿捏" in prompt and "摊牌拒绝" in prompt
    assert "双方对峙" in prompt                   # 画型描述
    assert "灰色虚线" in prompt                   # 摊牌拒绝=反弹动词 → 灰虚线描述


def test_compose_relation_prompt_v2_engineering_style_and_why_notes():
    prompt, _ = svc.compose_relation_prompt(_sample_card())
    # 工程制图风 V2 特征：圆形节点+头像插画+图标+端点圆点+箭头裸字动词
    assert "圆形" in prompt and "头像插画" in prompt and "细线图标" in prompt
    assert "端点小圆点" in prompt and "L 形工程角标" in prompt
    # why 说明小字随连线进提示词（逐字照抄）
    assert "说明小字：「把柄在他手里」" in prompt
    assert "说明小字：「不再代打卡」" in prompt
    # 禁人名硬约束
    assert "禁止出现任何人名" in prompt


def test_compose_relation_prompt_maps_pseudonyms_to_role_labels():
    card = svc.CaseCard.from_dict({
        "scenes": ["李四是科室主任，管着排班和考勤。"],
        "relations": [
            {"source": "张三", "verb": "隐形拿捏", "target": "李四", "why": "把柄在手"},
            {"source": "李四", "verb": "摊牌拒绝", "target": "张三", "why": "不再背锅"},
        ],
    })
    prompt, _ = svc.compose_relation_prompt(card)
    assert "张三" not in prompt and "李四" not in prompt
    assert "当事人" in prompt and "主任" in prompt   # 身份从卡片上下文推断
    assert "角色甲" not in prompt                     # 不允许占位式名称
    assert "${" not in prompt                    # 占位符已全部填充


def test_validate_relation_image_rejects_dark_background(tmp_path):
    try:
        svc._validate_relation_image(
            _png_bytes((20, 20, 20), with_mark=True, mark=(250, 250, 250)),
            tmp_path / "dark.png")
    except ValueError as exc:
        assert "白底" in str(exc)
    else:
        raise AssertionError("深底图应当被白底闸门拒绝")
    assert not (tmp_path / "dark.png").exists()  # 不合格图不落盘


def test_validate_relation_image_accepts_marked_white(tmp_path):
    width, height = svc._validate_relation_image(
        _png_bytes((252, 252, 252), with_mark=True), tmp_path / "ok.png")
    assert (width, height) == (1024, 768)
    assert (tmp_path / "ok.png").exists()
    assert svc._relation_image_passes_gate(tmp_path / "ok.png")


def test_relation_image_gate_tolerates_border_decoration(tmp_path):
    """贴边的工程细线外框+L形角标不应误杀白底图（按比例判定）。"""
    path = tmp_path / "framed.png"
    path.write_bytes(_png_bytes((253, 253, 253), with_mark=True))
    from PIL import Image, ImageDraw
    im = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(im)
    for inset in (11, 12, 13):                       # 贴边外框粗线
        draw.rectangle([inset, inset, 1023 - inset, 767 - inset], outline=(26, 26, 26))
    draw.rectangle([11, 11, 90, 14], fill=(26, 26, 26))   # L 角标
    draw.rectangle([11, 11, 14, 90], fill=(26, 26, 26))
    im.save(path, format="PNG")
    assert svc._relation_image_passes_gate(path)


def test_generate_relation_diagram_override_retries_once_then_raises(monkeypatch, tmp_path):
    from app.integrations import image_generation

    calls = {"n": 0}

    async def fake_generate(model, *, prompt, size, **kwargs):
        calls["n"] += 1
        return SimpleNamespace(content=_png_bytes((20, 20, 20), with_mark=True, mark=(250, 250, 250)))

    monkeypatch.setattr(image_generation, "generate_image", fake_generate)
    try:
        svc._generate_relation_diagram_override(_sample_card(), tmp_path, object(), "1536x1024")
    except RuntimeError as exc:
        assert "1 个模型" in str(exc) and "均未成功" in str(exc)
    else:
        raise AssertionError("深底生图两次都应失败并抛错")
    assert calls["n"] == 2                       # 单模型失败重试一次
    assert not (tmp_path / "relation.png").exists()


def test_generate_relation_diagram_override_success(monkeypatch, tmp_path):
    from app.integrations import image_generation

    async def fake_generate(model, *, prompt, size, **kwargs):
        return SimpleNamespace(content=_png_bytes((255, 255, 255), with_mark=True))

    monkeypatch.setattr(image_generation, "generate_image", fake_generate)
    override, winner = svc._generate_relation_diagram_override(
        _sample_card(), tmp_path, SimpleNamespace(provider="fake-image-model"), "1536x1024")
    assert override["image_file"] == "assets/relation.png"
    assert override["canvas_h"] > 0
    assert winner == "fake-image-model"
    assert (tmp_path / "relation.png").exists()


def test_generate_relation_diagram_override_falls_through_model_chain(monkeypatch, tmp_path):
    """模型链兜底：首家全败（请求异常）自动换下一家，并报告实际出图的模型。"""
    from app.integrations import image_generation

    calls = {"n": 0, "providers": []}

    async def fake_generate(model, *, prompt, size, **kwargs):
        calls["n"] += 1
        calls["providers"].append(model.provider)
        if model.provider == "dead-provider":
            raise RuntimeError("502 upstream")
        return SimpleNamespace(content=_png_bytes((255, 255, 255), with_mark=True))

    monkeypatch.setattr(image_generation, "generate_image", fake_generate)
    dead = SimpleNamespace(provider="dead-provider")
    alive = SimpleNamespace(provider="alive-provider")
    override, winner = svc._generate_relation_diagram_override(
        _sample_card(), tmp_path, [dead, alive], "1536x1024")
    assert winner == "alive-provider"
    assert calls["n"] == 3                          # 首家两次失败，第二家一次成功
    assert calls["providers"] == ["dead-provider", "dead-provider", "alive-provider"]
    assert override["image_file"] == "assets/relation.png"


def test_render_case_card_falls_back_to_svg(monkeypatch, tmp_path):
    """生图失败时回退 SVG 关系图，出卡不中断。"""
    def broken(card, assets_dir, models, size, prompt_template=""):
        raise RuntimeError("生图服务不可用")

    monkeypatch.setattr(svc, "_generate_relation_diagram_override", broken)

    def fake_render(html_path, png_path, *, scale=2, edge_path=""):
        png_path.write_bytes(_png_bytes((247, 243, 236), size=(2160, 100)))
        return 2160, 100

    monkeypatch.setattr(svc, "render_html_to_png", fake_render)
    rendered = svc.render_case_card(_sample_card(), tmp_path, relation_model=object())
    html = rendered.html_path.read_text(encoding="utf-8")
    assert 'class="dg-canvas"' in html           # 回退到 SVG 关系图
    assert "relation.png" not in html
    assert not (tmp_path / "assets" / "relation.png").exists()


def test_compose_relation_prompt_uses_custom_template():
    """传入的模板优先：占位符被填充、自定义内容保留、无残留占位符。"""
    template = (
        "自定义开头 ${画型}\n"
        "节点：\n${节点清单}\n"
        "连线：\n${连线清单}\n"
        "自定义结尾"
    )
    prompt, mode = svc.compose_relation_prompt(_sample_card(), template_text=template)
    assert mode == "confront"
    assert "自定义开头" in prompt and "自定义结尾" in prompt
    assert "双方对峙" in prompt                     # 画型占位符已填充
    assert "- 主任" in prompt and "隐形拿捏" in prompt
    assert "${画型}" not in prompt and "${节点清单}" not in prompt and "${连线清单}" not in prompt


def test_compose_relation_prompt_falls_back_when_placeholder_missing():
    """模板缺占位符时整份回退内置默认，不拼出坏提示词。"""
    prompt, _ = svc.compose_relation_prompt(_sample_card(), template_text="没有占位符的坏模板")
    assert "印刷在纯白" in prompt                   # 内置默认特征
    assert "没有占位符的坏模板" not in prompt


def test_relation_prompt_template_seeded_in_defaults():
    """内置提示词库包含关系图生图模板，且占位符齐全（播种用）。"""
    from app.default_prompt_templates import DEFAULT_PROMPT_TEMPLATES, RELATION_IMAGE_PROMPT_TEMPLATE
    names = [t["name"] for t in DEFAULT_PROMPT_TEMPLATES]
    assert any("关系图生图提示词" in name for name in names)
    for placeholder in ("${画型}", "${节点清单}", "${连线清单}"):
        assert placeholder in RELATION_IMAGE_PROMPT_TEMPLATE
