"""Shared rules for image-card text blocks."""

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageStat

from ..config import get_settings
from ..integrations.image_generation import ImageGenerationError

settings = get_settings()

BLOCK_START = "<!-- CONTENT_BLOCK_START -->"
BLOCK_END = "<!-- CONTENT_BLOCK_END -->"
CARD_TOP_MARKER = "【拼卡·上】"
CARD_BOTTOM_MARKER = "【拼卡·下】"
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


def card_renderer_directory() -> Path:
    """本地案例卡渲染器（card_renderer）目录；可用设置覆盖。"""

    configured = (getattr(settings, "card_renderer_dir", "") or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "card_renderer"


def resolve_local_card_pairs(blocks: list[str]) -> list[tuple[int, int]]:
    """本地渲染的配对唯一入口（返回 1 起始的 (上卡序号, 下卡序号)，严格成对）。

    带拼卡标记时按标记配对（错序/漏块/重复块在此报出具体块序号）；
    无标记的历史内容按位置相邻两两配对，奇数块无法配对直接报错。
    AI 生图链路的宽松配对（允许奇数尾块单独成组）仍走 resolve_card_pairs，
    两者语义不同，不要混用。
    """

    if not blocks:
        raise ValueError("没有可渲染的内容块")
    if has_card_markers(blocks):
        return pair_card_blocks(blocks)
    if len(blocks) % 2 != 0:
        raise ValueError(
            f"本地渲染要求内容块成对（上卡+下卡），实际 {len(blocks)} 个；请检查内容块标记是否完整"
        )
    return [(start, start + 1) for start in range(1, len(blocks) + 1, 2)]


def render_case_cards_locally(
    block_pairs: list[tuple[str, str]],
    *,
    font_theme: str = "A",
    qr_url: str | None = None,
) -> dict:
    """调用本地 Playwright 渲染器把上下卡内容块渲染成 1:6 长图（已内嵌二维码）。

    block_pairs 为 (上卡块原文, 下卡块原文) 序列——配对必须由调用方先经
    resolve_local_card_pairs 完成（pair_card_blocks 是配对唯一真源），本函数
    与渲染脚本都不再做拆块/配对，块首拼卡标记可省略。
    返回 {"cards": [长图 bytes...], "halves": [(上卡 bytes, 下卡 bytes)...],
    "warnings": [渲染器 stdout 中的告警行...]}，均按卡序排列；
    halves 用于执行后落盘备份，便于事后排查拼接问题。
    """

    renderer_dir = card_renderer_directory()
    script = renderer_dir / "render_card.py"
    if not script.exists():
        raise ImageGenerationError(f"本地案例卡渲染脚本不存在：{script}")
    payload = {"cards": [{"top": top, "bottom": bottom} for top, bottom in block_pairs]}
    with tempfile.TemporaryDirectory(prefix="case-card-local-") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / "cards.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        output_dir = tmp_dir / "out"
        cmd = [
            sys.executable,
            str(script),
            str(input_path),
            "--input-json",
            "--font",
            font_theme,
            "--outdir",
            str(output_dir),
        ]
        if qr_url:
            cmd += ["--qr", qr_url]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=str(renderer_dir),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            raise ImageGenerationError(f"本地案例卡渲染失败：{detail}")
        cards = sorted(
            output_dir.glob("card_*.png"),
            key=lambda p: int(re.search(r"card_(\d+)\.png", p.name).group(1)),
        )
        if not cards:
            raise ImageGenerationError(f"本地案例卡渲染未产出图片：{(result.stdout or '').strip()[-300:]}")
        half_dir = output_dir / "half"
        halves = []
        for index in range(1, len(cards) + 1):
            top = half_dir / f"card{index}_top.png"
            bottom = half_dir / f"card{index}_bottom.png"
            halves.append(
                (
                    top.read_bytes() if top.exists() else b"",
                    bottom.read_bytes() if bottom.exists() else b"",
                )
            )
        return {
            "cards": [p.read_bytes() for p in cards],
            "halves": halves,
            "warnings": _collect_renderer_warnings(result.stdout),
        }


def _collect_renderer_warnings(stdout: str | None) -> list[str]:
    """提取渲染脚本 stdout 中的校验/溢出告警行。

    渲染成功（returncode=0）时 stdout 会被调用方丢弃，内容溢出（整卡缩放）
    与字段校验问题在生产环境将完全不可见，因此这里显式收集回传给调用方。
    """

    warnings: list[str] = []
    for line in (stdout or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[warn]"):
            warnings.append(stripped)
        elif stripped.startswith("[card ") and ("校验" in stripped or "溢出" in stripped):
            warnings.append(stripped)
    return warnings


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


def block_card_kind(block: str | None) -> str | None:
    """内容块第一个非空行的拼卡标记类型：top / bottom / None。"""

    for line in (block or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(CARD_TOP_MARKER):
            return "top"
        if stripped.startswith(CARD_BOTTOM_MARKER):
            return "bottom"
        return None
    return None


def has_card_markers(blocks: list[str]) -> bool:
    """任一内容块带拼卡标记即为 True（用于判断是否走上下拼卡配对规则）。"""

    return any(block_card_kind(block) for block in blocks)


def _block_preview(block: str | None) -> str:
    return (block or "").strip().replace("\n", " ")[:30]


def pair_card_blocks(blocks: list[str]) -> list[tuple[int, int]]:
    """按【拼卡·上】/【拼卡·下】标记把内容块配对成（上卡序号, 下卡序号），序号 1 起始。

    序列必须全部块带标记且严格「上、下」交替，否则抛 ValueError——这类错序
    （漏块/重复块/乱序）如果放任，会被按位置相邻配对的拼接逻辑拼成跨话题的卡，
    正是"一张卡出现两个话题/内容重复"的根源，必须在生图花费之前拦下。
    """

    pairs: list[tuple[int, int]] = []
    pending_top: int | None = None
    for index, block in enumerate(blocks, start=1):
        kind = block_card_kind(block)
        if kind == "top":
            if pending_top is not None:
                raise ValueError(
                    f"第 {pending_top} 个内容块（【拼卡·上】）之后没有紧跟下卡，内容块顺序错乱：{_block_preview(blocks[pending_top - 1])}"
                )
            pending_top = index
        elif kind == "bottom":
            if pending_top is None:
                raise ValueError(
                    f"第 {index} 个内容块是【拼卡·下】，但前面没有待配对的【拼卡·上】：{_block_preview(block)}"
                )
            pairs.append((pending_top, index))
            pending_top = None
        else:
            raise ValueError(
                f"第 {index} 个内容块第一行缺少【拼卡·上】/【拼卡·下】标记：{_block_preview(block)}"
            )
    if pending_top is not None:
        raise ValueError(
            f"第 {pending_top} 个内容块（【拼卡·上】）没有配对的下卡，内容块总数必须为偶数：{_block_preview(blocks[pending_top - 1])}"
        )
    return pairs


def resolve_card_pairs(blocks: list[str], *, split_enabled: bool) -> list[list[int]]:
    """返回拼接配对（内容块序号分组，1 起始；组内 1~2 个序号）。

    分块启用且内容块带拼卡标记时按标记配对（错序直接抛错）；
    否则退回旧行为：按位置相邻两两配对，奇数尾块单独成组（历史模板兼容）。
    """

    if not split_enabled:
        return [[1]]
    if has_card_markers(blocks):
        return [list(pair) for pair in pair_card_blocks(blocks)]
    return [
        [start, start + 1] if start + 1 <= len(blocks) else [start]
        for start in range(1, len(blocks) + 1, 2)
    ]


def backup_execution_images(
    execution_id: int | None,
    *,
    halves: list[bytes] | None = None,
    cards: list[bytes] | None = None,
    source_text: str | None = None,
) -> dict:
    """把一次执行的半卡图/拼接图/内容块原文落盘，便于事后排查拼接错位与生图越界。

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
    for index, content in enumerate(halves or [], start=1):
        if not content:
            continue
        (target / f"half_{index:02d}.png").write_bytes(content)
        saved += 1
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
        if has_card_markers(blocks):
            # 上下拼卡内容：标记必须「上、下」严格交替成对，错序/漏块/重复块
            # 在此快速失败（生成阶段会触发文本模型重试，且发生在任何生图花费之前）
            pair_card_blocks(blocks)
    if max_count is not None and len(blocks) > max_count:
        raise ValueError(
            f"本次识别到 {len(blocks)} 个图片内容，超过作业上限 {max_count} 张"
        )
    return blocks
