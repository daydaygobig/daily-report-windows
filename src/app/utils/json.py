"""JSON serialization helpers."""

import json
from typing import Any


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def loads(data: str | None) -> Any:
    if not data:
        return None
    return json.loads(data)
