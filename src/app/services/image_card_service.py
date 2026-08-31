"""Shared rules for image-card text blocks."""

import re

BLOCK_START = "<!-- CONTENT_BLOCK_START -->"
BLOCK_END = "<!-- CONTENT_BLOCK_END -->"
BLOCK_START_PARAM = "${block_start}"
BLOCK_END_PARAM = "${block_end}"

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
    if max_count is not None and len(blocks) > max_count:
        raise ValueError(
            f"本次识别到 {len(blocks)} 个图片内容，超过作业上限 {max_count} 张"
        )
    return blocks
