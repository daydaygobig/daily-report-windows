"""上下拼卡内容块配对：标记校验、按标记配对、话题筛选与执行图片落盘。"""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.scheduler import common as scheduler_common
from app.scheduler import delivery as delivery_module
from app.scheduler.parsing import _select_image_blocks
from app.scheduler.service import SchedulerService
from app.services import image_card_service
from app.integrations.image_generation import GeneratedImage

TOP = image_card_service.CARD_TOP_MARKER
BOTTOM = image_card_service.CARD_BOTTOM_MARKER


def _block(kind: str, body: str) -> str:
    marker = TOP if kind == "top" else BOTTOM
    return f"{marker}\n{body}"


def _wrapped(*blocks: str) -> str:
    return "\n\n".join(
        f"{image_card_service.BLOCK_START}\n{block}\n{image_card_service.BLOCK_END}"
        for block in blocks
    )


# ---------------- 标记识别与配对 ----------------


def test_block_card_kind_reads_first_nonempty_line():
    assert image_card_service.block_card_kind(f"{TOP}\n标题") == "top"
    assert image_card_service.block_card_kind(f"\n\n{BOTTOM}\n分析") == "bottom"
    assert image_card_service.block_card_kind("没有标记的内容") is None
    assert image_card_service.block_card_kind("") is None


def test_pair_card_blocks_pairs_in_order():
    blocks = [_block("top", "话题1上"), _block("bottom", "话题1下"), _block("top", "话题2上"), _block("bottom", "话题2下")]
    assert image_card_service.pair_card_blocks(blocks) == [(1, 2), (3, 4)]


def test_pair_card_blocks_rejects_missing_bottom():
    blocks = [_block("top", "话题1上"), _block("bottom", "话题1下"), _block("top", "话题2上")]
    with pytest.raises(ValueError, match="没有配对的下卡"):
        image_card_service.pair_card_blocks(blocks)


def test_pair_card_blocks_rejects_bottom_without_top():
    blocks = [_block("bottom", "话题1下"), _block("top", "话题1上"), _block("bottom", "话题1下")]
    with pytest.raises(ValueError, match="没有待配对的"):
        image_card_service.pair_card_blocks(blocks)


def test_pair_card_blocks_rejects_unmarked_block_among_marked():
    blocks = [_block("top", "上"), _block("bottom", "下"), "无标记块"]
    with pytest.raises(ValueError, match="缺少【拼卡·上】/【拼卡·下】标记"):
        image_card_service.pair_card_blocks(blocks)


# ---------------- parse_content_blocks 序列校验 ----------------


def test_parse_content_blocks_accepts_valid_marked_sequence():
    content = _wrapped(_block("top", "话题1上"), _block("bottom", "话题1下"))
    blocks = image_card_service.parse_content_blocks(content, split_enabled=True)
    assert blocks == [_block("top", "话题1上"), _block("bottom", "话题1下")]


def test_parse_content_blocks_rejects_swapped_block_order():
    # 上卡出现在下卡之后：按位置相邻配对会拼出跨话题的卡，必须在生图前拦截
    content = _wrapped(_block("bottom", "话题1下"), _block("top", "话题1上"))
    with pytest.raises(ValueError, match="没有待配对的"):
        image_card_service.parse_content_blocks(content, split_enabled=True)


def test_parse_content_blocks_rejects_odd_marked_blocks():
    content = _wrapped(_block("top", "上"), _block("bottom", "下"), _block("top", "落单的上"))
    with pytest.raises(ValueError, match="没有配对的下卡"):
        image_card_service.parse_content_blocks(content, split_enabled=True)


def test_parse_content_blocks_ignores_sequence_without_markers():
    content = _wrapped("# 完整卡一", "# 完整卡二")
    assert len(image_card_service.parse_content_blocks(content, split_enabled=True)) == 2


# ---------------- 拼接分组 ----------------


def test_resolve_card_pairs_uses_markers_when_present():
    blocks = [_block("top", "1上"), _block("bottom", "1下"), _block("top", "2上"), _block("bottom", "2下")]
    assert image_card_service.resolve_card_pairs(blocks, split_enabled=True) == [[1, 2], [3, 4]]


def test_resolve_card_pairs_falls_back_to_positional_with_odd_tail():
    blocks = ["卡一", "卡二", "卡三"]
    assert image_card_service.resolve_card_pairs(blocks, split_enabled=True) == [[1, 2], [3]]


def test_resolve_card_pairs_single_block_when_split_disabled():
    assert image_card_service.resolve_card_pairs(["整篇内容"], split_enabled=False) == [[1]]


# ---------------- 单话题筛选 ----------------


def _job(aspect_ratio: str = "1:3"):
    return SimpleNamespace(image_aspect_ratio=aspect_ratio)


def test_select_image_blocks_returns_whole_marker_pair():
    blocks = [
        _block("top", "话题1 关键词甲"),
        _block("bottom", "话题1下"),
        _block("top", "话题2 关键词乙"),
        _block("bottom", "话题2下"),
    ]
    # 序号 "2" 命中话题1的下卡，返回话题1整组；"3"/关键词命中话题2，返回话题2整组
    assert _select_image_blocks(blocks, "2", job=_job()) == blocks[:2]
    assert _select_image_blocks(blocks, "3", job=_job()) == blocks[2:]
    assert _select_image_blocks(blocks, "关键词乙", job=_job()) == blocks[2:]
    assert _select_image_blocks(blocks, "关键词甲", job=_job()) == blocks[:2]


def test_select_image_blocks_unmarked_keeps_positional_groups():
    blocks = ["甲", "乙", "丙", "丁"]
    assert _select_image_blocks(blocks, "2", job=_job()) == ["甲", "乙"]


def test_select_image_blocks_without_stitch_selects_single_block():
    blocks = ["甲", "乙"]
    assert _select_image_blocks(blocks, "2", job=_job(aspect_ratio="auto")) == ["乙"]


# ---------------- 执行图片落盘备份 ----------------


def test_backup_execution_images_writes_and_prunes(monkeypatch, tmp_path):
    backup_root = tmp_path / "image_cards"
    monkeypatch.setattr(image_card_service.settings, "image_card_backup_dir", str(backup_root))
    monkeypatch.setattr(image_card_service.settings, "image_card_backup_keep_last", 2)

    def _png(color: tuple) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color).save(buf, format="PNG")
        return buf.getvalue()

    first = image_card_service.backup_execution_images(
        1, halves=[_png((255, 0, 0))], cards=[_png((0, 0, 255))], source_text="块内容"
    )
    assert first["files"] == 3
    image_card_service.backup_execution_images(2, cards=[_png((0, 255, 0))])
    # keep_last=2：写入 exec_3 后最旧的 exec_1 被清理
    image_card_service.backup_execution_images(3, cards=[_png((0, 0, 0))])
    assert sorted(p.name for p in backup_root.iterdir()) == ["exec_2", "exec_3"]
    image_card_service.backup_execution_images(4, cards=[_png((9, 9, 9))])
    remaining = sorted(p.name for p in backup_root.iterdir())
    assert remaining == ["exec_3", "exec_4"]
    assert (backup_root / "exec_4" / "card_01.png").exists()


def test_backup_disabled_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(image_card_service.settings, "image_card_backup_enabled", False)
    assert image_card_service.backup_execution_images(9, cards=[b"x"]) == {}
    assert not (tmp_path / "image_cards").exists()


# ---------------- 本地渲染器 parse_input 严格配对 ----------------


RENDER_CARD_PATH = Path(__file__).resolve().parents[1] / "card_renderer" / "render_card.py"


def _load_render_card():
    spec = importlib.util.spec_from_file_location("render_card_under_test", RENDER_CARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_top(title: str) -> str:
    return "\n".join(
        [
            "IP角色：男",
            title,
            "副标题追问？",
            "关键词：甲、乙、丙",
            "",
            "背景概述：",
            "事实｜一",
            "事实｜二",
            "事实｜三",
            "",
            "场景一",
            "场景二",
            "场景三",
            "",
            "你怎么办？",
            "",
            "人物关系：",
            "同事 —(施压)→ 当事人：把杂活转嫁",
            "整体结构：转嫁结构",
        ]
    )


def _valid_bottom() -> str:
    return "\n".join(
        [
            "分析过程：",
            "1、『先答应』：内容",
            "",
            "解决方案：",
            "1、『当场拒绝』：做法",
            "",
            "金句：",
            "金句内容",
            "—— @张三",
        ]
    )


def test_render_card_parse_input_pairs_by_sequence():
    render_card = _load_render_card()
    text = _wrapped(
        _block("top", _valid_top("标题一")),
        _block("bottom", _valid_bottom()),
        _block("top", _valid_top("标题二")),
        _block("bottom", _valid_bottom()),
    )
    cards = render_card.parse_input(text)
    assert [card["top"]["title"] for card in cards] == ["标题一", "标题二"]


def test_render_card_parse_input_rejects_consecutive_tops():
    render_card = _load_render_card()
    text = _wrapped(
        _block("top", _valid_top("标题一")),
        _block("top", _valid_top("标题二")),
        _block("bottom", _valid_bottom()),
        _block("bottom", _valid_bottom()),
    )
    with pytest.raises(ValueError, match="没有紧跟配对的"):
        render_card.parse_input(text)


def test_render_card_parse_input_rejects_unmarked_block():
    render_card = _load_render_card()
    text = _wrapped("没有标记的内容", _block("bottom", _valid_bottom()))
    with pytest.raises(ValueError, match="【拼卡·上】或【拼卡·下】"):
        render_card.parse_input(text)


def test_render_card_parse_input_rejects_lone_top():
    render_card = _load_render_card()
    text = _wrapped(_block("top", _valid_top("标题一")))
    with pytest.raises(ValueError, match="没有紧跟配对的"):
        render_card.parse_input(text)


def test_render_card_parse_input_accepts_marker_with_trailing_text():
    """标记行带余文（服务端 startswith 规则放行的场景），渲染器同样接受且余文并入正文。"""
    render_card = _load_render_card()
    top_lines = _valid_top("标题一").splitlines()
    # 标记行自带「：IP角色：男」，去掉正文里重复的首行
    text = _wrapped(
        "\n".join([f"{TOP}：IP角色：男", *top_lines[1:]]),
        _block("bottom", _valid_bottom()),
    )
    cards = render_card.parse_input(text)
    assert cards[0]["top"]["title"] == "标题一"
    assert cards[0]["gender"] == "male"


def test_render_card_parse_input_tolerates_leading_blank_lines():
    """内容块标记行前有空行时，标记行不得漏进正文（旧实现 b[1:] 的隐患）。"""
    render_card = _load_render_card()
    text = _wrapped(
        "\n".join(["", _block("top", _valid_top("标题一"))]),
        _block("bottom", _valid_bottom()),
    )
    cards = render_card.parse_input(text)
    assert cards[0]["top"]["title"] == "标题一"


# ---------------- 渲染器 JSON 输入（服务端已配对） ----------------


def _cards_json_payload(top_text: str, bottom_text: str) -> str:
    return json.dumps({"cards": [{"top": top_text, "bottom": bottom_text}]}, ensure_ascii=False)


def test_render_card_parse_cards_json_accepts_marked_blocks():
    render_card = _load_render_card()
    payload = _cards_json_payload(_block("top", _valid_top("标题一")), _block("bottom", _valid_bottom()))
    cards = render_card.parse_cards_json(payload)
    assert cards[0]["top"]["title"] == "标题一"
    assert cards[0]["gender"] == "male"
    assert cards[0]["bottom"]["solution"][0]["tag"] == "当场拒绝"


def test_render_card_parse_cards_json_accepts_unmarked_blocks():
    """无标记的历史内容按位置配对后同样可渲染（旧文本协议下是死路）。"""
    render_card = _load_render_card()
    payload = _cards_json_payload(_valid_top("标题一"), _valid_bottom())
    cards = render_card.parse_cards_json(payload)
    assert cards[0]["top"]["title"] == "标题一"


def test_render_card_parse_cards_json_merges_marker_trailing_text():
    render_card = _load_render_card()
    top_lines = _valid_top("标题一").splitlines()
    payload = _cards_json_payload(
        "\n".join([f"{TOP}：IP角色：男", *top_lines[1:]]),
        _block("bottom", _valid_bottom()),
    )
    cards = render_card.parse_cards_json(payload)
    assert cards[0]["top"]["title"] == "标题一"


def test_render_card_parse_cards_json_rejects_mismatched_marker():
    """上卡位却带【拼卡·下】标记：上游配对出错的信号，必须当场报错。"""
    render_card = _load_render_card()
    payload = _cards_json_payload(_block("bottom", _valid_bottom()), _valid_bottom())
    with pytest.raises(ValueError, match="标记与所在半卡不符"):
        render_card.parse_cards_json(payload)


def test_render_card_parse_cards_json_rejects_bad_payload():
    render_card = _load_render_card()
    with pytest.raises(ValueError, match="JSON 输入解析失败"):
        render_card.parse_cards_json("不是 JSON")
    with pytest.raises(ValueError, match="缺少非空 cards 数组"):
        render_card.parse_cards_json(json.dumps({"cards": []}))
    with pytest.raises(ValueError, match="缺少 top/bottom 文本字段"):
        render_card.parse_cards_json(json.dumps({"cards": [{"top": "只有上卡"}]}))


# ---------------- 本地渲染链路：配对契约与告警回传 ----------------


@pytest.mark.asyncio
async def test_local_handler_records_render_warnings_in_meta(monkeypatch, tmp_path):
    """本地渲染的溢出/校验告警必须进入 execution.raw_response，不能随 stdout 丢弃。"""
    service = SchedulerService()
    monkeypatch.setattr(delivery_module.image_card_service.settings, "image_card_backup_enabled", False)
    seen = {}

    def fake_render(block_pairs, *, font_theme="A", qr_url=None):
        seen["block_pairs"] = block_pairs
        return {
            "cards": [b"long-image"],
            "halves": [(b"top", b"bottom")],
            "warnings": ["[card 1] 上卡内容溢出模块: module-card"],
        }

    monkeypatch.setattr(delivery_module.image_card_service, "render_case_cards_locally", fake_render)

    async def fake_deliver_image_bytes(**kwargs):
        return "img-key-1"

    monkeypatch.setattr(service, "_deliver_image_bytes", fake_deliver_image_bytes)
    webhook = SimpleNamespace(id=1, name="通知群", feishu_app_id="app-id", feishu_app_secret_cipher="cipher")
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])
    monkeypatch.setattr(delivery_module, "decrypt_value", lambda value: "secret")

    execution = SimpleNamespace(id=88, raw_response=None, summary_md=None)
    blocks = [
        _block("top", "话题1上内容甲"),
        _block("bottom", "话题1下内容乙"),
    ]

    await service._handle_image_card_result(
        db=SimpleNamespace(),
        task=SimpleNamespace(id=1, name="案例卡任务", push_webhook_ids="[1]"),
        job=SimpleNamespace(
            card_renderer="local",
            max_image_count=6,
            image_split_enabled=True,
            card_font_theme="A",
            max_retry=0,
            retry_interval_sec=1,
        ),
        execution=execution,
        raw_response=_wrapped(*blocks),
    )

    # 渲染器收到的是服务端配好的 (上卡块, 下卡块) 对，不再重包装文本协议
    assert seen["block_pairs"] == [(blocks[0], blocks[1])]
    meta = json.loads(execution.raw_response)
    assert meta["renderer"] == "local"
    assert meta["render_warnings"] == ["[card 1] 上卡内容溢出模块: module-card"]
    assert meta["deliveries"][0]["webhooks"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_local_handler_pairs_unmarked_blocks_positionally(monkeypatch):
    """无标记历史内容走本地渲染：按位置配对成块对（旧链路会死在渲染器的标记校验上）。"""
    service = SchedulerService()
    monkeypatch.setattr(delivery_module.image_card_service.settings, "image_card_backup_enabled", False)
    seen = {}

    def fake_render(block_pairs, *, font_theme="A", qr_url=None):
        seen["block_pairs"] = block_pairs
        return {"cards": [b"img"], "halves": [(b"t", b"b")], "warnings": []}

    monkeypatch.setattr(delivery_module.image_card_service, "render_case_cards_locally", fake_render)

    async def fake_deliver_image_bytes(**kwargs):
        return "img-key-1"

    monkeypatch.setattr(service, "_deliver_image_bytes", fake_deliver_image_bytes)
    webhook = SimpleNamespace(id=1, name="通知群", feishu_app_id="app-id", feishu_app_secret_cipher="cipher")
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])
    monkeypatch.setattr(delivery_module, "decrypt_value", lambda value: "secret")

    execution = SimpleNamespace(id=89, raw_response=None, summary_md=None)
    await service._handle_image_card_result(
        db=SimpleNamespace(),
        task=SimpleNamespace(id=1, name="案例卡任务", push_webhook_ids="[1]"),
        job=SimpleNamespace(
            card_renderer="local",
            max_image_count=6,
            image_split_enabled=True,
            card_font_theme="A",
            max_retry=0,
            retry_interval_sec=1,
        ),
        execution=execution,
        raw_response=_wrapped("无标记上卡内容", "无标记下卡内容"),
    )

    assert seen["block_pairs"] == [("无标记上卡内容", "无标记下卡内容")]
    assert json.loads(execution.raw_response)["deliveries"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_local_handler_skips_no_image_content_with_notice(monkeypatch):
    """本地渲染模式下模型返回无内容标记：推送提示语并记录跳过，而不是渲染器晦涩报错。"""
    service = SchedulerService()
    sent = []

    async def fake_push_feishu(**kwargs):
        sent.append(kwargs["summary"])
        return True

    monkeypatch.setattr(service, "_push_feishu", fake_push_feishu)
    webhook = SimpleNamespace(id=1, name="通知群", feishu_app_id="app-id", feishu_app_secret_cipher="cipher")
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])

    execution = SimpleNamespace(id=90, raw_response=None, summary_md=None)
    await service._handle_image_card_result(
        db=SimpleNamespace(),
        task=SimpleNamespace(id=1, name="案例卡任务", push_webhook_ids="[1]"),
        job=SimpleNamespace(id=2, card_renderer="local", max_image_count=6, image_split_enabled=True),
        execution=execution,
        raw_response=image_card_service.NO_IMAGE_CONTENT,
    )

    meta = json.loads(execution.raw_response)
    assert meta["renderer"] == "local"
    assert meta["skipped"] == "no_image_content"
    assert execution.summary_md == image_card_service.NO_IMAGE_CONTENT_NOTICE
    assert sent == [image_card_service.NO_IMAGE_CONTENT_NOTICE]


# ---------------- AI 生图链路：配对与备份端到端 ----------------


def _png(color: tuple) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (720, 2160), color).save(buf, format="PNG")
    return buf.getvalue()


def _ai_job():
    return SimpleNamespace(
        card_renderer="ai",
        max_image_count=12,
        image_split_enabled=True,
        image_aspect_ratio="1:3",
        image_resolution="auto",
        image_prompt="生成一张案例卡图",
        image_prompt_template_id=None,
        max_retry=0,
        retry_interval_sec=1,
    )


@pytest.mark.asyncio
async def test_ai_handler_pairs_by_markers_and_backs_up(monkeypatch, tmp_path):
    service = SchedulerService()
    monkeypatch.setattr(scheduler_common.settings, "qr_code_enabled", False)
    monkeypatch.setattr(scheduler_common.settings, "image_card_backup_dir", str(tmp_path / "bk"))
    blocks = [
        _block("top", "话题1上内容甲"),
        _block("bottom", "话题1下内容乙"),
        _block("top", "话题2上内容丙"),
        _block("bottom", "话题2下内容丁"),
    ]
    raw_response = _wrapped(*blocks)
    generated_by_body = {
        "话题1上内容甲": (255, 0, 0),
        "话题1下内容乙": (0, 255, 0),
        "话题2上内容丙": (0, 0, 255),
        "话题2下内容丁": (255, 255, 0),
    }

    async def fake_generate_image(model, *, prompt, size, **kwargs):
        for body, color in generated_by_body.items():
            if body in prompt:
                return GeneratedImage(content=_png(color))
        raise AssertionError(f"提示词中未识别到内容块：{prompt[:80]}")

    calls = {"generate": 0, "sent": []}

    async def fake_generate(*args, **kwargs):
        calls["generate"] += 1
        return await fake_generate_image(*args, **kwargs)

    async def fake_upload_image(**kwargs):
        return f"imgkey-{kwargs['image_bytes'][:4].hex()}"

    async def fake_send_image(webhook, image_key=None, max_retries=1):
        calls["sent"].append(image_key)
        return True

    monkeypatch.setattr(delivery_module.image_generation, "generate_image", fake_generate)
    monkeypatch.setattr(delivery_module.feishu, "upload_image", fake_upload_image)
    monkeypatch.setattr(delivery_module.feishu, "send_image", fake_send_image)
    monkeypatch.setattr(
        service,
        "_resolve_image_model_sequence",
        lambda db, task: [SimpleNamespace(model=SimpleNamespace(id=4, provider="mock-image"), max_attempts=1)],
    )

    webhook = SimpleNamespace(
        id=1,
        name="通知群",
        feishu_app_id="app-id",
        feishu_app_secret_cipher="cipher",
    )
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])
    monkeypatch.setattr(delivery_module, "decrypt_value", lambda value: "secret")

    execution = SimpleNamespace(id=77, raw_response=None, summary_md=None)
    task = SimpleNamespace(id=1, name="案例卡任务", push_webhook_ids="[1]")

    await service._handle_image_card_result(
        db=SimpleNamespace(),
        task=task,
        job=_ai_job(),
        execution=execution,
        raw_response=raw_response,
    )

    assert calls["generate"] == 4
    meta = json.loads(execution.raw_response)
    assert meta["blocks_kinds"] == ["top", "bottom", "top", "bottom"]
    assert meta["stitch"]["pairs"] == [[1, 2], [3, 4]]
    assert [item["parts"] for item in meta["deliveries"]] == [[1, 2], [3, 4]]

    backup_dir = Path(meta["local_backup"]["dir"])
    # 4 张半卡 + 2 张拼接长图 + 1 份内容块原文
    assert meta["local_backup"]["files"] == 7
    assert sorted(p.name for p in backup_dir.iterdir()) == [
        "blocks_source.txt",
        "card_01.png",
        "card_02.png",
        "half_01.png",
        "half_02.png",
        "half_03.png",
        "half_04.png",
    ]
    assert backup_dir.joinpath("blocks_source.txt").read_text(encoding="utf-8") == raw_response

    # 拼接长图上半是话题1上卡（红）、下半是话题1下卡（绿）——按标记配对而非错位
    with Image.open(io.BytesIO((backup_dir / "card_01.png").read_bytes())) as stitched:
        assert stitched.size == (720, 4320)
        assert stitched.getpixel((10, 10)) == (255, 0, 0)
        assert stitched.getpixel((10, 4310)) == (0, 255, 0)
    with Image.open(io.BytesIO((backup_dir / "card_02.png").read_bytes())) as stitched:
        assert stitched.getpixel((10, 10)) == (0, 0, 255)
        assert stitched.getpixel((10, 4310)) == (255, 255, 0)


@pytest.mark.asyncio
async def test_ai_handler_rejects_misordered_blocks_before_generation(monkeypatch, tmp_path):
    service = SchedulerService()
    monkeypatch.setattr(scheduler_common.settings, "qr_code_enabled", False)
    monkeypatch.setattr(scheduler_common.settings, "image_card_backup_dir", str(tmp_path / "bk"))

    async def fail_generate(*args, **kwargs):
        raise AssertionError("配对校验失败时不应发起生图请求")

    monkeypatch.setattr(delivery_module.image_generation, "generate_image", fail_generate)
    monkeypatch.setattr(
        service,
        "_resolve_image_model_sequence",
        lambda db, task: [SimpleNamespace(model=SimpleNamespace(id=4, provider="mock-image"), max_attempts=1)],
    )
    webhook = SimpleNamespace(id=1, name="通知群", feishu_app_id="app-id", feishu_app_secret_cipher="cipher")
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])
    monkeypatch.setattr(delivery_module, "decrypt_value", lambda value: "secret")

    raw_response = _wrapped(_block("top", "话题2上"), _block("top", "话题1上"), _block("bottom", "话题1下"), _block("bottom", "话题2下"))
    execution = SimpleNamespace(id=78, raw_response=None, summary_md=None)

    with pytest.raises(ValueError, match="之后没有紧跟下卡"):
        await service._handle_image_card_result(
            db=SimpleNamespace(),
            task=SimpleNamespace(id=1, name="t", push_webhook_ids="[1]"),
            job=_ai_job(),
            execution=execution,
            raw_response=raw_response,
        )
