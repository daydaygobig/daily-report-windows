"""Utilities for computing prompt usage statistics."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional dependency
    tiktoken = None


def compute_prompt_usage(task_prompt: str, system_instruction: str, chatlog_text: str) -> Dict[str, Dict[str, int]]:
    sections = {
        "system": system_instruction or "",
        "task": task_prompt or "",
        "chatlog": chatlog_text or "",
    }
    chars = {key: len(value) for key, value in sections.items()}
    tokens = {key: _count_tokens(value) for key, value in sections.items()}
    chars["total"] = sum(chars.values())
    tokens["total"] = sum(tokens.values())
    return {"chars": chars, "tokens": tokens}


def count_tokens(text: str) -> int:
    """Public helper for counting tokens, reused outside this module."""
    return _count_tokens(text)


def _count_tokens(text: str) -> int:
    if not text:
        return 0
    if tiktoken:
        try:
            encoding = _get_encoding()
            return len(encoding.encode(text))
        except Exception:  # pragma: no cover - fallback
            pass
    # Fallback: approximate by splitting on whitespace and counting characters
    ascii_words = sum(1 for part in text.split() if part.isascii())
    non_ascii = sum(1 for ch in text if not ch.isspace() and not ch.isascii())
    return ascii_words + non_ascii


@lru_cache(maxsize=1)
def _get_encoding():
    if not tiktoken:
        raise RuntimeError("tiktoken not installed")
    return tiktoken.get_encoding("cl100k_base")
