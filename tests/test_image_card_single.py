"""单卡模式：内容块解析、拼卡语法拦截、话题筛选与执行图片落盘。"""

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


def _wrapped(*blocks: str) -> str:
    return "\n\n".join(
        f"{image_card_service.BLOCK_START}\n{block}\n{image_card_service.BLOCK_END}"
        for block in blocks
    )


# ---------------- 内容块解析 ----------------


def test_parse_content_blocks_splits_single_cards():
    content = _wrapped("# 完整卡一\n背景概述：……", "# 完整卡二\n背景概述：……")
    blocks = image_card_service.parse_content_blocks(content, split_enabled=True)
    assert len(blocks) == 2
    assert blocks[0].startswith("# 完整卡一")


def test_parse_content_blocks_whole_response_when_split_disabled():
    blocks = image_card_service.parse_content_blocks("整份内容只有一张卡", split_enabled=False)
    assert blocks == ["整份内容只有一张卡"]


def test_parse_content_blocks_rejects_legacy_split_markers():
    """上下拼卡语法已下线：旧模板仍输出标记时在生图前拦截并提示换单卡模板。"""
    content = _wrapped("【拼卡·上】\n话题1上", "【拼卡·下】\n话题1下")
    with pytest.raises(ValueError, match="单卡版"):
        image_card_service.parse_content_blocks(content, split_enabled=True)


# ---------------- 单话题筛选（一块=一话题=一张卡） ----------------


def _job():
    return SimpleNamespace(image_aspect_ratio="auto")


def test_select_image_blocks_by_index_or_keyword():
    blocks = ["话题1 关键词甲", "话题2 关键词乙", "话题3 关键词丙"]
    assert _select_image_blocks(blocks, "2", job=_job()) == ["话题2 关键词乙"]
    assert _select_image_blocks(blocks, "关键词丙", job=_job()) == ["话题3 关键词丙"]
    assert _select_image_blocks(blocks, "9", job=_job()) == []
    assert _select_image_blocks(blocks, "不存在", job=_job()) == []


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
        1, cards=[_png((0, 0, 255))], source_text="块内容"
    )
    assert first["files"] == 2
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


# ---------------- AI 纯生图链路：单卡出图与备份端到端 ----------------


def _png(color: tuple) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (720, 2160), color).save(buf, format="PNG")
    return buf.getvalue()


def _ai_job():
    return SimpleNamespace(
        max_image_count=12,
        image_split_enabled=True,
        image_aspect_ratio="2:3",
        image_resolution="auto",
        image_prompt="生成一张案例卡图",
        image_prompt_template_id=None,
        max_retry=0,
        retry_interval_sec=1,
    )


@pytest.mark.asyncio
async def test_ai_handler_generates_one_card_per_block(monkeypatch, tmp_path):
    service = SchedulerService()
    monkeypatch.setattr(scheduler_common.settings, "qr_code_enabled", False)
    monkeypatch.setattr(scheduler_common.settings, "image_card_backup_dir", str(tmp_path / "bk"))
    # 本测试走纯生图路径：显式关闭本地 HTML 引擎，避免受 .env 环境影响
    monkeypatch.setattr(scheduler_common.settings, "html_card_engine_enabled", False)
    blocks = ["话题1上内容甲", "话题2上内容乙", "话题3上内容丙"]
    raw_response = _wrapped(*blocks)
    generated_by_body = {
        "话题1上内容甲": (255, 0, 0),
        "话题2上内容乙": (0, 255, 0),
        "话题3上内容丙": (0, 0, 255),
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

    assert calls["generate"] == 3                    # 一个内容块 = 一次生图
    meta = json.loads(execution.raw_response)
    assert "stitch" not in meta                       # 拼接功能已下线
    assert [item["parts"] for item in meta["deliveries"]] == [[1], [2], [3]]
    assert len(calls["sent"]) == 3                    # 每张卡独立推送

    backup_dir = Path(meta["local_backup"]["dir"])
    # 3 张卡图 + 1 份内容块原文
    assert meta["local_backup"]["files"] == 4
    assert sorted(p.name for p in backup_dir.iterdir()) == [
        "blocks_source.txt",
        "card_01.png",
        "card_02.png",
        "card_03.png",
    ]
    assert backup_dir.joinpath("blocks_source.txt").read_text(encoding="utf-8") == raw_response


@pytest.mark.asyncio
async def test_ai_handler_rejects_legacy_markers_before_generation(monkeypatch, tmp_path):
    service = SchedulerService()
    monkeypatch.setattr(scheduler_common.settings, "qr_code_enabled", False)
    monkeypatch.setattr(scheduler_common.settings, "image_card_backup_dir", str(tmp_path / "bk"))
    monkeypatch.setattr(scheduler_common.settings, "html_card_engine_enabled", False)

    async def fail_generate(*args, **kwargs):
        raise AssertionError("拼卡语法拦截失败时不应发起生图请求")

    monkeypatch.setattr(delivery_module.image_generation, "generate_image", fail_generate)
    monkeypatch.setattr(
        service,
        "_resolve_image_model_sequence",
        lambda db, task: [SimpleNamespace(model=SimpleNamespace(id=4, provider="mock-image"), max_attempts=1)],
    )
    webhook = SimpleNamespace(id=1, name="通知群", feishu_app_id="app-id", feishu_app_secret_cipher="cipher")
    monkeypatch.setattr(service, "_load_push_webhooks", lambda db, task: [webhook])
    monkeypatch.setattr(delivery_module, "decrypt_value", lambda value: "secret")

    raw_response = _wrapped("【拼卡·上】\n话题1上", "【拼卡·下】\n话题1下")
    execution = SimpleNamespace(id=78, raw_response=None, summary_md=None)

    with pytest.raises(ValueError, match="单卡版"):
        await service._handle_image_card_result(
            db=SimpleNamespace(),
            task=SimpleNamespace(id=1, name="t", push_webhook_ids="[1]"),
            job=_ai_job(),
            execution=execution,
            raw_response=raw_response,
        )
