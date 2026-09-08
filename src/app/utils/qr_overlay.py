"""在生成的案例卡图片右下角叠加二维码面板（二维码 + 可选小字说明）。"""

from __future__ import annotations

import io
from dataclasses import dataclass

import qrcode
from PIL import Image, ImageDraw, ImageFont

# 小字说明的中文字体候选，按顺序取第一个可用的
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)


@dataclass(frozen=True)
class QrOverlayResult:
    content: bytes
    mime_type: str
    qr_side_px: int
    caption: str


def _load_caption_font(size: int):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _build_qr_image(url: str, target_side: int) -> Image.Image:
    """按目标边长绘制二维码；每个码点取整数像素，保证黑白块边缘清晰可扫。"""

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    module_count = len(matrix)
    module_px = max(2, round(target_side / module_count))
    side = module_px * module_count
    image = Image.new("L", (side, side), 255)
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(matrix):
        for col, dark in enumerate(line):
            if dark:
                draw.rectangle(
                    (
                        col * module_px,
                        row * module_px,
                        (col + 1) * module_px - 1,
                        (row + 1) * module_px - 1,
                    ),
                    fill=0,
                )
    return image


def _build_qr_panel(url: str, caption: str, target_qr_side: int) -> Image.Image:
    qr_image = _build_qr_image(url, target_qr_side)
    pad = max(8, round(qr_image.width * 0.12))
    bottom_pad = max(6, round(pad * 0.6))
    radius = max(6, round(pad * 0.8))

    font = None
    text_box = None
    text_gap = 0
    if caption:
        font = _load_caption_font(max(14, round(qr_image.width * 0.24)))
        text_box = ImageDraw.Draw(qr_image).textbbox((0, 0), caption, font=font)
        text_gap = max(4, round(pad * 0.4))

    panel_w = qr_image.width + pad * 2
    text_h = (text_box[3] - text_box[1]) if text_box else 0
    panel_h = pad + qr_image.height + (text_gap + text_h if text_box else 0) + bottom_pad

    panel = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle(
        (0, 0, panel_w - 1, panel_h - 1),
        radius=radius,
        fill=(255, 255, 255, 255),
        outline=(203, 203, 203, 255),
        width=max(1, pad // 12),
    )
    panel.paste(qr_image.convert("RGBA"), ((panel_w - qr_image.width) // 2, pad))
    if caption and text_box and font:
        text_x = (panel_w - (text_box[2] - text_box[0])) // 2 - text_box[0]
        text_y = pad + qr_image.height + text_gap - text_box[1]
        draw.text((text_x, text_y), caption, font=font, fill=(64, 64, 64, 255))
    return panel


def apply_qr_overlay(
    image_bytes: bytes,
    *,
    url: str,
    caption: str = "",
    size_ratio: float = 0.12,
    edge_ratio: float = 0.025,
) -> QrOverlayResult:
    """把二维码面板贴到图片右下角，返回 PNG 字节；图片太小放不下时抛 ValueError。"""

    if not url or not url.strip():
        raise ValueError("二维码链接为空")
    source = Image.open(io.BytesIO(image_bytes))
    width, height = source.size
    panel = _build_qr_panel(url.strip(), caption, round(width * size_ratio))
    margin = max(8, round(width * edge_ratio))
    if panel.width > width - margin * 2 or panel.height > height - margin * 2:
        raise ValueError(
            f"图片尺寸 {width}x{height} 放不下二维码面板 {panel.width}x{panel.height}"
        )
    canvas = source.convert("RGBA")
    canvas.alpha_composite(
        panel, (width - panel.width - margin, height - panel.height - margin)
    )
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return QrOverlayResult(
        content=buffer.getvalue(),
        mime_type="image/png",
        qr_side_px=round(width * size_ratio),
        caption=caption,
    )
