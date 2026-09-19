"""Shared rules for image-card text blocks."""

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageStat

from ..config import get_settings

settings = get_settings()

BLOCK_START = "<!-- CONTENT_BLOCK_START -->"
BLOCK_END = "<!-- CONTENT_BLOCK_END -->"
BLOCK_START_PARAM = "${block_start}"
BLOCK_END_PARAM = "${block_end}"
LEGACY_CARD_MARKERS = ("【拼卡·上】", "【拼卡·下】")   # 已下线的上下拼卡语法，出现即报错提示换模板
NO_IMAGE_CONTENT = "<!-- NO_IMAGE_CONTENT -->"
NO_IMAGE_CONTENT_NOTICE = "本时段无职场话题讨论"
NO_IMAGE_CONTENT_ALIASES = {
    NO_IMAGE_CONTENT,
    NO_IMAGE_CONTENT_NOTICE,
    "【本时段无职场话题讨论】",
}
NO_IMAGE_CONTENT_INSTRUCTION = f"""如果本次聊天记录中没有任何符合当前任务要求、值得生成图片的内容，只输出一行：
{NO_IMAGE_CONTENT}
该标记表示本次整体无需生图，不得把它放进单个内容块，也不得同时输出其他正文或内容块标记。"""

DEFAULT_IMAGE_SPLIT_PROMPT = """请将最终结果拆分成一个或多个独立内容块，每个内容块对应一张图片。

每个内容块必须严格按照以下格式输出：

${block_start}
请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。
${block_end}

不要把两个独立内容合并到同一个内容块；不要在开始和结束标识之外输出其他正文。"""

IMAGE_SIZE_MAP = {
    "1k": {
        "auto": "1024x1024",
        "1:1": "1024x1024",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
        "9:16": "864x1536",
    },
    "2k": {
        "auto": "2048x2048",
        "1:1": "2048x2048",
        "3:2": "2048x1360",
        "2:3": "1360x2048",
        "9:16": "1152x2048",
    },
    "4k": {
        "auto": "2880x2880",
        "1:1": "2880x2880",
        "3:2": "3520x2336",
        "2:3": "2336x3520",
        "9:16": "2160x3840",
    },
}


def normalize_split_prompt(enabled: bool, prompt: str | None) -> str | None:
    """Validate and normalize the editable split instruction."""

    if not enabled:
        return (prompt or DEFAULT_IMAGE_SPLIT_PROMPT).strip()
    value = (prompt or DEFAULT_IMAGE_SPLIT_PROMPT).strip()
    replacements = (
        ("请把最终结果拆分成一个或多个独立内容块：一个完整职场案例对应一个内容块，也对应一张图片。",
         "请将最终结果拆分成一个或多个独立内容块，每个内容块对应一张图片。"),
        ("这里放一个案例的完整生图提示词", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"),
        ("这里放一个案例的完整 Markdown 内容", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"),
        ("这里输出一个案例的完整 Markdown 内容", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"),
        ("请根据聊天记录生成该话题的完整正文，不要原样输出本行说明。",
         "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"),
        ("不要把两个案例放进同一个内容块", "不要把两个独立内容合并到同一个内容块"),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    missing = [
        token
        for token in (BLOCK_START_PARAM, BLOCK_END_PARAM)
        if token not in value
    ]
    if missing:
        raise ValueError("拆图规则必须同时包含 ${block_start} 和 ${block_end}")
    return value


def expand_split_prompt(prompt: str | None) -> str:
    value = normalize_split_prompt(True, prompt) or DEFAULT_IMAGE_SPLIT_PROMPT
    return value.replace(BLOCK_START_PARAM, BLOCK_START).replace(
        BLOCK_END_PARAM,
        BLOCK_END,
    )


def resolve_image_size(aspect_ratio: str | None, resolution: str | None) -> str:
    ratio = aspect_ratio or "auto"
    level = resolution or "auto"
    if level == "auto" and ratio == "auto":
        return "auto"
    effective_level = "1k" if level == "auto" else level
    sizes = IMAGE_SIZE_MAP.get(effective_level)
    if not sizes or ratio not in sizes:
        raise ValueError("图片比例或分辨率配置不受支持")
    return sizes[ratio]


def backup_execution_images(
    execution_id: int | None,
    *,
    cards: list[bytes] | None = None,
    source_text: str | None = None,
) -> dict:
    """把一次执行的卡片图与内容块原文落盘，便于事后排查生图越界与文案问题。

    目录：settings.image_card_backup_dir/exec_<执行ID>（无 ID 时用时间戳）；
    只保留最近 settings.image_card_backup_keep_last 次执行（<=0 表示全部保留）。
    备份属于辅助能力，调用方需自行捕获异常，不得影响主流程。
    """

    if not settings.image_card_backup_enabled:
        return {}
    root = Path(settings.image_card_backup_dir)
    name = (
        f"exec_{execution_id}"
        if execution_id
        else f"exec_unnamed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    saved = 0
    for index, content in enumerate(cards or [], start=1):
        if not content:
            continue
        (target / f"card_{index:02d}.png").write_bytes(content)
        saved += 1
    if source_text:
        (target / "blocks_source.txt").write_text(source_text, encoding="utf-8")
        saved += 1
    _prune_image_card_backups(root)
    return {"dir": str(target), "files": saved}


def _prune_image_card_backups(root: Path) -> None:
    keep = int(getattr(settings, "image_card_backup_keep_last", 0) or 0)
    if keep <= 0 or not root.exists():
        return
    dirs = [d for d in root.iterdir() if d.is_dir() and d.name.startswith("exec_")]
    # mtime 粒度可能同刻度（连续快速写入），用目录名（exec_<自增ID>）做平局裁决，
    # 否则同刻度时会误删较新的执行备份
    dirs.sort(key=lambda d: (d.stat().st_mtime, d.name), reverse=True)
    for stale in dirs[keep:]:
        try:
            for f in stale.iterdir():
                if f.is_file():
                    f.unlink()
            stale.rmdir()
        except OSError:
            pass  # 清理失败不影响主流程，下次执行再试


def compose_image_prompt(template: str | None, block: str | None) -> str:
    """Combine the saved image prompt template with one Markdown content block."""

    prompt_template = (template or "").strip()
    content_block = (block or "").strip()
    if not prompt_template:
        raise ValueError("图片提示词模板内容为空")
    if not content_block:
        raise ValueError("图片内容块为空")
    return (
        f"{prompt_template}\n\n"
        "以下是本次需要生成图片的 Markdown 内容，请忠实呈现：\n\n"
        f"{content_block}"
    )


def parse_content_blocks(
    content: str,
    *,
    split_enabled: bool,
    max_count: int | None = None,
) -> list[str]:
    """Return one image prompt per marked Markdown block, or the whole document."""

    text = (content or "").strip()
    if not text:
        raise ValueError("模型返回内容为空")
    if text in NO_IMAGE_CONTENT_ALIASES:
        return []
    if NO_IMAGE_CONTENT in text:
        raise ValueError("无需生图标记必须作为本次完整返回内容单独输出")
    if not split_enabled:
        blocks = [text]
    else:
        start_count = text.count(BLOCK_START)
        end_count = text.count(BLOCK_END)
        if start_count == 0 or end_count == 0:
            raise ValueError("模型返回中没有找到图片内容的开始和结束标识")
        if start_count != end_count:
            raise ValueError("图片内容的开始和结束标识数量不一致")
        pattern = re.compile(
            f"{re.escape(BLOCK_START)}\\s*(.*?)\\s*{re.escape(BLOCK_END)}",
            re.DOTALL,
        )
        blocks = [match.strip() for match in pattern.findall(text) if match.strip()]
        if len(blocks) != start_count:
            raise ValueError("图片内容标识存在嵌套、空块或顺序错误")
        if any(marker in block for block in blocks for marker in LEGACY_CARD_MARKERS):
            # 上下拼卡语法已下线：旧文案模板仍输出标记时快速失败（发生在任何生图花费之前），
            # 生成阶段会触发文本模型重试，错误信息指引更换单卡文案模板
            raise ValueError(
                "文案仍在输出【拼卡·上/下】标记——上下拼卡模式已下线，"
                "请把任务的提示词模板换为单卡版（如「日报话题案例卡（纯日报内容）」）"
            )
    if max_count is not None and len(blocks) > max_count:
        raise ValueError(
            f"本次识别到 {len(blocks)} 个图片内容，超过作业上限 {max_count} 张"
        )
    return blocks
