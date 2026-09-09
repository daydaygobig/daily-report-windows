import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.integrations.image_generation import ImageGenerationError
from app.scheduler import service as scheduler_module
from app.scheduler.service import SchedulerService
from app.services import image_card_service
from app.services.execution_service import _image_card_meta

TOP = image_card_service.CARD_TOP_MARKER
BOTTOM = image_card_service.CARD_BOTTOM_MARKER


def test_split_blocks_from_fixed_markers():
    content = f"""
{image_card_service.BLOCK_START}
# 话题一
第一张图
{image_card_service.BLOCK_END}
{image_card_service.BLOCK_START}
# 话题二
第二张图
{image_card_service.BLOCK_END}
"""

    blocks = image_card_service.parse_content_blocks(
        content,
        split_enabled=True,
        max_count=2,
    )

    assert blocks == ["# 话题一\n第一张图", "# 话题二\n第二张图"]


def test_whole_markdown_is_one_image_when_split_disabled():
    content = "# 汇总\n完整内容"

    assert image_card_service.parse_content_blocks(
        content,
        split_enabled=False,
    ) == [content]


@pytest.mark.parametrize("split_enabled", [False, True])
@pytest.mark.parametrize(
    "content",
    [
        image_card_service.NO_IMAGE_CONTENT,
        image_card_service.NO_IMAGE_CONTENT_NOTICE,
        "【本时段无职场话题讨论】",
    ],
)
def test_no_image_content_marker_skips_the_whole_image_run(split_enabled, content):
    assert image_card_service.parse_content_blocks(
        content,
        split_enabled=split_enabled,
    ) == []


def test_no_image_content_marker_cannot_be_used_inside_a_content_block():
    content = (
        f"{image_card_service.BLOCK_START}\n"
        f"{image_card_service.NO_IMAGE_CONTENT}\n"
        f"{image_card_service.BLOCK_END}"
    )

    with pytest.raises(ValueError, match="完整返回内容单独输出"):
        image_card_service.parse_content_blocks(content, split_enabled=True)


def test_image_execution_meta_reports_no_content_as_skipped():
    execution = SimpleNamespace(
        raw_response=json.dumps(
            {
                "type": "image_card",
                "block_count": 0,
                "skipped": "no_image_content",
                "skip_reason": "文本模型判定本次没有符合条件的生图内容",
                "deliveries": [],
            },
            ensure_ascii=False,
        )
    )

    meta = _image_card_meta(execution)

    assert meta["生成状态"] == "已跳过"
    assert meta["推送状态"] == "未执行"
    assert meta["跳过原因"] == "文本模型判定本次没有符合条件的生图内容"


def test_split_prompt_requires_both_parameters():
    with pytest.raises(ValueError, match="block_start"):
        image_card_service.normalize_split_prompt(True, "只包含 ${block_start}")


# ---------------- 本地渲染器调用 ----------------


def _fake_renderer_dir(tmp_path: Path) -> Path:
    renderer_dir = tmp_path / "card_renderer"
    renderer_dir.mkdir()
    (renderer_dir / "render_card.py").write_text("# fake", encoding="utf-8")
    return renderer_dir


def test_render_case_cards_locally_returns_renderer_warnings(monkeypatch, tmp_path):
    renderer_dir = _fake_renderer_dir(tmp_path)
    monkeypatch.setattr(image_card_service, "card_renderer_directory", lambda: renderer_dir)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["payload"] = json.loads(Path(cmd[2]).read_text(encoding="utf-8"))
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        half = outdir / "half"
        half.mkdir(parents=True)
        (half / "card1_top.png").write_bytes(b"t")
        (half / "card1_bottom.png").write_bytes(b"b")
        (outdir / "card_1.png").write_bytes(b"c")
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    "[card 1] 校验: 事实字段应为3行，实际2行",
                    "[card 1] 上卡内容溢出模块: module-card",
                    "[card 1] 完成 -> card_1.png",
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(image_card_service.subprocess, "run", fake_run)

    result = image_card_service.render_case_cards_locally(
        [("【拼卡·上】\n上卡内容", "【拼卡·下】\n下卡内容")]
    )

    # 服务端完成配对后以 JSON 契约传给渲染脚本，不再重包装文本协议
    assert "--input-json" in seen["cmd"]
    assert seen["payload"] == {
        "cards": [{"top": "【拼卡·上】\n上卡内容", "bottom": "【拼卡·下】\n下卡内容"}]
    }
    assert result["cards"] == [b"c"]
    assert result["halves"] == [(b"t", b"b")]
    assert result["warnings"] == [
        "[card 1] 校验: 事实字段应为3行，实际2行",
        "[card 1] 上卡内容溢出模块: module-card",
    ]


def test_render_case_cards_locally_failure_raises_image_generation_error(monkeypatch, tmp_path):
    """渲染失败必须抛 ImageGenerationError 且带上子进程错误详情，而不是 NameError。"""
    renderer_dir = _fake_renderer_dir(tmp_path)
    monkeypatch.setattr(image_card_service, "card_renderer_directory", lambda: renderer_dir)
    monkeypatch.setattr(
        image_card_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="chromium 崩溃"),
    )

    with pytest.raises(ImageGenerationError, match="chromium 崩溃"):
        image_card_service.render_case_cards_locally([("上卡", "下卡")])


def test_render_case_cards_locally_missing_script_raises_image_generation_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        image_card_service,
        "card_renderer_directory",
        lambda: tmp_path / "missing",
    )

    with pytest.raises(ImageGenerationError, match="渲染脚本不存在"):
        image_card_service.render_case_cards_locally([("上卡", "下卡")])


# ---------------- 本地渲染配对唯一入口 ----------------


def test_resolve_local_card_pairs_uses_markers_when_present():
    blocks = [
        f"{TOP}\n话题1上",
        f"{BOTTOM}\n话题1下",
        f"{TOP}\n话题2上",
        f"{BOTTOM}\n话题2下",
    ]
    assert image_card_service.resolve_local_card_pairs(blocks) == [(1, 2), (3, 4)]


def test_resolve_local_card_pairs_unmarked_falls_back_to_positional():
    assert image_card_service.resolve_local_card_pairs(["卡一上", "卡一下", "卡二上", "卡二下"]) == [
        (1, 2),
        (3, 4),
    ]


def test_resolve_local_card_pairs_rejects_odd_unmarked_blocks():
    with pytest.raises(ValueError, match="实际 3 个"):
        image_card_service.resolve_local_card_pairs(["上", "下", "落单"])


def test_resolve_local_card_pairs_rejects_empty_blocks():
    with pytest.raises(ValueError, match="没有可渲染的内容块"):
        image_card_service.resolve_local_card_pairs([])


def test_split_prompt_rewrites_legacy_image_prompt_wording():
    prompt = (
        "请把最终结果拆分成一个或多个独立内容块：一个完整职场案例对应一个内容块，也对应一张图片。\n"
        "${block_start}\n这里放一个案例的完整生图提示词\n${block_end}\n"
        "不要把两个案例放进同一个内容块"
    )

    normalized = image_card_service.normalize_split_prompt(True, prompt)

    assert "请根据输入内容生成该内容块的完整正文" in normalized
    assert "每个内容块对应一张图片" in normalized
    assert "这里放" not in normalized
    assert "完整生图提示词" not in normalized
    assert "职场" not in normalized
    assert "案例" not in normalized


def test_image_count_limit_fails_before_image_requests():
    content = "\n".join(
        f"{image_card_service.BLOCK_START}\n{i}\n{image_card_service.BLOCK_END}"
        for i in range(3)
    )

    with pytest.raises(ValueError, match="超过作业上限 2 张"):
        image_card_service.parse_content_blocks(
            content,
            split_enabled=True,
            max_count=2,
        )


@pytest.mark.parametrize(
    ("aspect_ratio", "resolution", "expected"),
    [
        ("auto", "auto", "auto"),
        ("1:1", "2k", "2048x2048"),
        ("1:1", "4k", "2880x2880"),
        ("3:2", "4k", "3520x2336"),
        ("2:3", "4k", "2336x3520"),
        ("9:16", "4k", "2160x3840"),
    ],
)
def test_resolve_image_size(aspect_ratio, resolution, expected):
    assert image_card_service.resolve_image_size(aspect_ratio, resolution) == expected


def test_compose_image_prompt_combines_template_and_markdown_block():
    result = image_card_service.compose_image_prompt(
        "使用克制的手绘信息卡片风格。",
        "# 职场案例\n\n这是本次案例内容。",
    )

    assert result.startswith("使用克制的手绘信息卡片风格。")
    assert "# 职场案例" in result
    assert "这是本次案例内容。" in result


def test_compose_image_prompt_rejects_empty_template():
    with pytest.raises(ValueError, match="图片提示词模板内容为空"):
        image_card_service.compose_image_prompt("", "# 内容")


def test_scheduler_uses_job_split_rule_for_text_intermediate():
    service = SchedulerService()
    task = SimpleNamespace(
        task_type="image_card",
        system_prompt_custom_enabled=False,
        image_split_enabled=False,
    )
    job = SimpleNamespace(
        image_split_enabled=True,
        image_split_prompt=image_card_service.DEFAULT_IMAGE_SPLIT_PROMPT,
    )

    instruction = service._build_system_instruction(
        task,
        job,
        ["测试群"],
        {"time_str": "2026-08-31 00:00 ~ 23:59"},
        None,
    )

    assert image_card_service.BLOCK_START in instruction
    assert image_card_service.BLOCK_END in instruction
    assert image_card_service.NO_IMAGE_CONTENT in instruction


def test_scheduler_always_adds_no_image_rule_when_split_is_disabled():
    service = SchedulerService()
    task = SimpleNamespace(task_type="image_card", system_prompt_custom_enabled=False)
    job = SimpleNamespace(image_split_enabled=False)

    instruction = service._build_system_instruction(
        task,
        job,
        ["测试群"],
        {"time_str": "2026-08-31 00:00 ~ 23:59"},
        None,
    )

    assert image_card_service.NO_IMAGE_CONTENT in instruction
    assert "不得把它放进单个内容块" in instruction


def test_scheduler_validates_blocks_using_job_settings():
    service = SchedulerService()
    task = SimpleNamespace(task_type="image_card")
    job = SimpleNamespace(image_split_enabled=True, max_image_count=2)
    summary = (
        f"{image_card_service.BLOCK_START}\n# 内容一\n{image_card_service.BLOCK_END}"
    )

    service._validate_ai_output(
        task=task,
        job=job,
        summary=summary,
        html_required=False,
    )
    service._validate_ai_output(
        task=task,
        job=job,
        summary=image_card_service.NO_IMAGE_CONTENT,
        html_required=False,
    )

    with pytest.raises(ValueError, match="没有找到图片内容"):
        service._validate_ai_output(
            task=task,
            job=job,
            summary="# 未分块内容",
            html_required=False,
        )


@pytest.mark.asyncio
async def test_scheduler_skips_image_dependencies_for_no_image_content(monkeypatch):
    service = SchedulerService()
    model_output = "本时段无职场话题讨论"
    execution = SimpleNamespace(raw_response=None, summary_md=model_output)
    webhook = SimpleNamespace(id=2, name="通知群")
    sent_messages = []

    monkeypatch.setattr(scheduler_module.webhook_repo, "get_by_ids", lambda db, ids: [webhook])

    async def fake_push_feishu(**kwargs):
        sent_messages.append(kwargs)
        return True

    monkeypatch.setattr(service, "_push_feishu", fake_push_feishu)

    await service._handle_image_card_result(
        db=SimpleNamespace(),
        task=SimpleNamespace(id=1, push_webhook_ids="[2]"),
        job=SimpleNamespace(id=2, image_split_enabled=True, max_image_count=6),
        execution=execution,
        raw_response=model_output,
    )

    meta = json.loads(execution.raw_response)
    assert meta["block_count"] == 0
    assert meta["skipped"] == "no_image_content"
    assert meta["model_output"] == model_output
    assert meta["notice"] == image_card_service.NO_IMAGE_CONTENT_NOTICE
    assert meta["notice_pushed"] is True
    assert meta["deliveries"] == []
    assert execution.summary_md == image_card_service.NO_IMAGE_CONTENT_NOTICE
    assert sent_messages[0]["summary"] == image_card_service.NO_IMAGE_CONTENT_NOTICE


def test_resolve_image_size_supports_paired_card_ratio():
    """左右拼卡的 1:3 竖版比例在各级分辨率下都可用。"""
    assert image_card_service.resolve_image_size("1:3", "1k") == "720x2160"
    assert image_card_service.resolve_image_size("1:3", "2k") == "1080x3240"
    assert image_card_service.resolve_image_size("1:3", "4k") == "1440x4320"
    assert image_card_service.resolve_image_size("1:3", "auto") == "720x2160"


def test_stitch_images_vertically_pairs_and_scales():
    """上下拼卡：相邻两张等宽拼接为 1:6 长图；宽度不一致时按最窄宽度等比缩放。"""
    import io

    from PIL import Image

    def _png(width: int, height: int, color: tuple) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (width, height), color).save(buf, format="PNG")
        return buf.getvalue()

    merged = image_card_service.stitch_images_vertically([_png(100, 300, (255, 0, 0)), _png(100, 300, (0, 0, 255))])
    with Image.open(io.BytesIO(merged)) as im:
        assert im.size == (100, 600)
        assert im.getpixel((50, 150)) == (255, 0, 0)
        assert im.getpixel((50, 450)) == (0, 0, 255)

    merged_scaled = image_card_service.stitch_images_vertically(
        [_png(100, 300, (255, 0, 0)), _png(80, 240, (0, 0, 255))]
    )
    with Image.open(io.BytesIO(merged_scaled)) as im:
        assert im.size[0] == 80
        # 100x300 等比缩放到宽 80 后高 240，加上第二张 240，总高 480
        assert im.size[1] == 480

    import pytest

    with pytest.raises(ValueError):
        image_card_service.stitch_images_vertically([])


def test_stitch_trims_blank_edges_at_seam():
    """上下拼卡：上卡裁掉底部空白、下卡裁掉顶部空白，各保留 24px 缓冲。"""
    import io

    from PIL import Image

    def _card(band_top: int, band_bottom: int, color: tuple) -> bytes:
        im = Image.new("RGB", (100, 300), (248, 243, 227))
        for y in range(band_top, band_bottom):
            for x in range(0, 100):
                im.putpixel((x, y), color)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    upper = _card(20, 200, (255, 0, 0))  # 内容在上部，底部 100px 空白
    lower = _card(120, 280, (0, 0, 255))  # 内容在下部，顶部 120px 空白
    merged = image_card_service.stitch_images_vertically([upper, lower])
    with Image.open(io.BytesIO(merged)) as im:
        # 上卡：内容末行 199，保留至 199+1+24=224，高 224
        # 下卡：内容首行 120，从 120-24=96 起保留，高 204；拼后总高 428
        assert im.size == (100, 428)
        assert im.getpixel((50, 50)) == (255, 0, 0)
        assert im.getpixel((50, 300)) == (0, 0, 255)
        # 接缝附近的缓冲区应为主背景色
        assert im.getpixel((50, 215)) == (248, 243, 227)
        assert im.getpixel((50, 235)) == (248, 243, 227)
