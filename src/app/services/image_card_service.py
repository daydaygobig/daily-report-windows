"""Shared rules for image-card text blocks."""

import re
from io import BytesIO

from PIL import Image, ImageStat

BLOCK_START = "<!-- CONTENT_BLOCK_START -->"
BLOCK_END = "<!-- CONTENT_BLOCK_END -->"
BLOCK_START_PARAM = "${block_start}"
BLOCK_END_PARAM = "${block_end}"
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
        "1:3": "720x2160",
    },
    "2k": {
        "auto": "2048x2048",
        "1:1": "2048x2048",
        "3:2": "2048x1360",
        "2:3": "1360x2048",
        "9:16": "1152x2048",
        "1:3": "1080x3240",
    },
    "4k": {
        "auto": "2880x2880",
        "1:1": "2880x2880",
        "3:2": "3520x2336",
        "2:3": "2336x3520",
        "9:16": "2160x3840",
        "1:3": "1440x4320",
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


def stitch_images_vertically(images: list[bytes]) -> bytes:
    """把多张图片按顺序上下拼接成一张长图（像素级对齐，无接缝）。

    以最窄一张的宽度为基准，其余等比缩放到同一宽度后依次堆叠；
    用于 1:3 上下拼卡模式：相邻两张（同一话题的上卡+下卡）合成 1:6 长图。
    拼接前会裁掉相邻边缘的纯色空白行（上卡裁底、下卡裁顶），只保留
    24px 缓冲，避免生图模型在接缝一侧堆积大片留白。
    """
    if not images:
        raise ValueError("没有可拼接的图片")
    frames = []
    for raw in images:
        with Image.open(BytesIO(raw)) as im:
            frames.append(im.convert("RGB"))
    trimmed: list[Image.Image] = []
    count = len(frames)
    for index, im in enumerate(frames):
        if count > 1:
            im = _trim_blank_edge(im, trim_top=index > 0, trim_bottom=index < count - 1)
        trimmed.append(im)
    width = min(im.width for im in trimmed)
    resized = []
    for im in trimmed:
        if im.width != width:
            im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
        resized.append(im)
    total_height = sum(im.height for im in resized)
    canvas = Image.new("RGB", (width, total_height), (255, 255, 255))
    offset = 0
    for im in resized:
        canvas.paste(im, (0, offset))
        offset += im.height
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


# 单行 RGB 极差不超过该阈值视为纯色行（容忍压缩噪声）
BLANK_ROW_SPREAD = 16
# 纯色行与背景参考色的距离超过该阈值即为内容行
BG_COLOR_TOLERANCE = 24
# 裁剪后在内容边缘保留的纯色缓冲高度
TRIM_BUFFER_PX = 24
# 裁剪后允许的最小图高，低于此值视为整卡空白，放弃裁剪
MIN_TRIMMED_HEIGHT = 200


def _bg_reference(im: Image.Image) -> tuple[int, int, int]:
    """取四角像素均值作为背景参考色（卡片四角通常为留白）。"""
    width, height = im.size
    corners = (
        im.getpixel((0, 0)),
        im.getpixel((width - 1, 0)),
        im.getpixel((0, height - 1)),
        im.getpixel((width - 1, height - 1)),
    )
    return tuple(sum(c[i] for c in corners) // 4 for i in range(3))  # type: ignore[return-value]


def _is_blank_row(im: Image.Image, y: int, bg: tuple[int, int, int]) -> bool:
    """行内极差小（纯色）且颜色贴近背景参考色，才判定为可裁的空白行。"""
    row = im.crop((0, y, im.width, y + 1))
    if max(hi - lo for lo, hi in row.getextrema()) > BLANK_ROW_SPREAD:
        return False
    means = ImageStat.Stat(row).mean
    return all(abs(means[i] - bg[i]) <= BG_COLOR_TOLERANCE for i in range(3))


def _trim_blank_edge(im: Image.Image, *, trim_top: bool, trim_bottom: bool) -> Image.Image:
    """裁掉图片顶部/底部的连续纯色空白行，在内容边缘保留 24px 缓冲。"""
    height = im.height
    bg = _bg_reference(im)
    top = 0
    bottom = height
    if trim_bottom:
        last_content = None
        for y in range(height - 1, -1, -1):
            if not _is_blank_row(im, y, bg):
                last_content = y
                break
        if last_content is None:
            return im
        bottom = min(height, last_content + 1 + TRIM_BUFFER_PX)
    if trim_top:
        first_content = None
        for y in range(0, bottom):
            if not _is_blank_row(im, y, bg):
                first_content = y
                break
        if first_content is not None:
            top = max(top, first_content - TRIM_BUFFER_PX)
    if bottom - top < MIN_TRIMMED_HEIGHT:
        return im
    if top == 0 and bottom == height:
        return im
    return im.crop((0, top, im.width, bottom))


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
    if max_count is not None and len(blocks) > max_count:
        raise ValueError(
            f"本次识别到 {len(blocks)} 个图片内容，超过作业上限 {max_count} 张"
        )
    return blocks
