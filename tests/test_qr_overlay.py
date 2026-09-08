import io

import pytest
from PIL import Image

from app.utils import qr_overlay


def _png_bytes(size=(1024, 4096)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (240, 230, 210)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_apply_qr_overlay_returns_png_with_same_dimensions():
    result = qr_overlay.apply_qr_overlay(
        _png_bytes(),
        url="https://md.xinjianhub.cn/",
        caption="喜欢您来",
    )

    assert result.mime_type == "image/png"
    overlaid = Image.open(io.BytesIO(result.content))
    assert overlaid.size == (1024, 4096)


def test_apply_qr_overlay_rejects_image_too_small():
    with pytest.raises(ValueError):
        qr_overlay.apply_qr_overlay(
            _png_bytes(size=(64, 64)),
            url="https://md.xinjianhub.cn/",
            caption="喜欢您来",
        )


def test_apply_qr_overlay_without_caption_has_smaller_panel():
    with_caption = qr_overlay.apply_qr_overlay(
        _png_bytes(), url="https://md.xinjianhub.cn/", caption="喜欢您来"
    )
    without_caption = qr_overlay.apply_qr_overlay(
        _png_bytes(), url="https://md.xinjianhub.cn/", caption=""
    )

    assert len(without_caption.content) > 0
    assert len(with_caption.content) > 0
