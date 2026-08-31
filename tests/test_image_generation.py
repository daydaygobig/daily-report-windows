import base64
import json
from types import SimpleNamespace

import pytest
import respx
from httpx import Response

from app.integrations import image_generation


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "https://api.openai.com/v1/images/generations"),
        ("https://api.example.com", "https://api.example.com/v1/images/generations"),
        ("https://api.example.com/v1", "https://api.example.com/v1/images/generations"),
        (
            "https://api.example.com/v1/images/generations/",
            "https://api.example.com/v1/images/generations",
        ),
        (
            "https://api.example.com/v1/images/generations/v1/images/generations",
            "https://api.example.com/v1/images/generations",
        ),
        (
            "https://api.example.com/custom/images/generations",
            "https://api.example.com/custom/images/generations",
        ),
    ],
)
def test_normalize_image_base_url(value, expected):
    assert image_generation.normalize_image_base_url(value) == expected


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_decodes_b64(monkeypatch):
    endpoint = "https://example.com/v1/images/generations"
    image_bytes = b"small-png"
    route = respx.post(endpoint).mock(
        return_value=Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image_bytes).decode()}]},
        )
    )
    monkeypatch.setattr(image_generation, "decrypt_value", lambda _: "secret")
    model = SimpleNamespace(
        provider="gpt-image-2",
        base_url=endpoint,
        api_key_cipher="encrypted",
        extra=None,
    )

    result = await image_generation.generate_image(
        model,
        prompt="test",
        size="1024x1024",
        quality="low",
        extra_payload={
            "payload": {
                "model": "wrong-model",
                "prompt": "wrong-prompt",
                "n": 8,
                "size": "4096x4096",
                "output_format": "webp",
                "provider_option": True,
            }
        },
    )

    assert result.content == image_bytes
    assert route.called
    request_json = json.loads(route.calls.last.request.content.decode())
    assert request_json["model"] == "gpt-image-2"
    assert request_json["prompt"] == "test"
    assert request_json["n"] == 1
    assert request_json["size"] == "1024x1024"
    assert request_json["quality"] == "low"
    assert request_json["output_format"] == "png"
    assert request_json["provider_option"] is True


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_rejects_url_only_response(monkeypatch):
    endpoint = "https://example.com/v1/images/generations"
    respx.post(endpoint).mock(return_value=Response(200, json={"data": [{"url": "https://example.com/image.png"}]}))
    monkeypatch.setattr(image_generation, "decrypt_value", lambda _: "secret")
    model = SimpleNamespace(
        provider="gpt-image-2",
        base_url=endpoint,
        api_key_cipher="encrypted",
        extra=None,
    )

    with pytest.raises(image_generation.ImageGenerationError, match="只返回了图片 URL"):
        await image_generation.generate_image(model, prompt="test")
