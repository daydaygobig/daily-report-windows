from types import SimpleNamespace

import pytest

from app.scheduler.service import SchedulerService
from app.services import image_card_service


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

    with pytest.raises(ValueError, match="没有找到图片内容"):
        service._validate_ai_output(
            task=task,
            job=job,
            summary="# 未分块内容",
            html_required=False,
        )
