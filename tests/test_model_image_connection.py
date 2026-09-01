from app.routers.models import _safe_image_test_extra


def test_image_connection_test_keeps_fixed_low_cost_fields():
    extra = {
        "auth_header": "X-API-Key",
        "headers": {"X-Provider": "compatible"},
        "payload": {
            "model": "other-model",
            "prompt": "expensive prompt",
            "n": 8,
            "size": "4096x4096",
            "quality": "high",
            "output_format": "webp",
            "response_format": "b64_json",
            "provider_option": True,
        },
    }

    result = _safe_image_test_extra(extra)

    assert result["auth_header"] == "X-API-Key"
    assert result["headers"] == {"X-Provider": "compatible"}
    assert result["payload"] == {
        "response_format": "b64_json",
        "provider_option": True,
    }
