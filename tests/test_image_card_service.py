import json
from types import SimpleNamespace

import pytest

from app.scheduler import service as scheduler_module
from app.scheduler.service import SchedulerService
from app.services import image_card_service
from app.services.execution_service import _image_card_meta



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

