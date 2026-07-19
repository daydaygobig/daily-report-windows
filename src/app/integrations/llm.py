"""LLM abstraction layer supporting streaming completions."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, Optional, List

import httpx

from ..config import get_settings
from ..integrations.security import decrypt_value
from ..models.model import Model

settings = get_settings()

MAX_TOKENS_PARAM_KEYS = {"max_tokens", "max_completion_tokens"}


class LLMError(Exception):
    """Raised when LLM invocation fails."""


async def stream_completion(
    model: Model,
    *,
    prompt: str,
    timeout: Optional[int] = None,
    extra_payload: Optional[Dict] = None,
) -> AsyncGenerator[str, None]:
    """Stream completion response from configured LLM provider.

    The function assumes provider accepts OpenAI-compatible streaming endpoint by default,
    but authentication can be customized via model.extra. Gemini API 走单次非流式请求。
    """

    api_key = decrypt_value(model.api_key_cipher)
    base_url = model.base_url or "https://api.openai.com/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model.provider,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    extra_config: Dict[str, Any] = {}

    if isinstance(extra_payload, dict):
        extra_config = extra_payload
    elif extra_payload:
        payload.update(extra_payload)
    elif model.extra:
        try:
            extra_config = json.loads(model.extra)
        except json.JSONDecodeError:
            extra_config = {}

    if not isinstance(extra_config, dict):
        extra_config = {}

    overrides = extra_config.get("payload")
    if isinstance(overrides, dict):
        payload_overrides = overrides
    else:
        payload_overrides = None

    standard = (getattr(model, "request_standard", None) or "openai").lower()
    is_gemini = _is_gemini_endpoint(model, base_url, standard=standard)
    is_anthropic = standard == "anthropic"
    if not is_gemini:
        if not is_anthropic:
            payload.update(_openai_payload_from_model(model, extra_config))
        if isinstance(payload_overrides, dict):
            payload.update(payload_overrides)

    headers = {"Content-Type": "application/json"}
    timeout = timeout or settings.llm_timeout_sec

    async with httpx.AsyncClient(timeout=timeout) as client:
        if is_gemini:
            async for chunk in _stream_completion_gemini(
                client,
                base_url=base_url,
                api_key=api_key,
                prompt=prompt,
                payload_overrides=payload_overrides,
                extra_config=extra_config,
                model=model,
            ):
                yield chunk
            return
        if is_anthropic:
            async for chunk in _stream_completion_anthropic(
                client,
                base_url=base_url,
                api_key=api_key,
                prompt=prompt,
                payload_overrides=payload_overrides,
                extra_config=extra_config,
                model=model,
            ):
                yield chunk
            return

        auth_header = str(extra_config.get("auth_header") or "Authorization")
        if auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header] = api_key

        additional_headers = extra_config.get("headers")
        if isinstance(additional_headers, dict):
            headers.update({str(k): str(v) for k, v in additional_headers.items()})

        async for chunk in _completion_openai_stream(client, base_url=base_url, payload=payload, headers=headers):
            yield chunk


def _is_gemini_endpoint(model: Model, base_url: str, *, standard: str | None = None) -> bool:
    resolved = (standard or getattr(model, "request_standard", None) or "openai").lower()
    if resolved == "gemini":
        return True
    if resolved == "anthropic":
        return False
    url = (base_url or "").lower()
    return "generativelanguage.googleapis.com" in url


async def _stream_completion_gemini(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    prompt: str,
    payload_overrides: Optional[Dict[str, Any]],
    extra_config: Dict[str, Any],
    model: Model,
) -> AsyncGenerator[str, None]:
    request_body: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]
    }
    generation_config = _generation_config_from_model(model)
    if generation_config:
        request_body["generationConfig"] = generation_config
    if isinstance(payload_overrides, dict):
        request_body = _deep_merge_dict(request_body, payload_overrides)

    headers = {"Content-Type": "application/json"}
    additional_headers = extra_config.get("headers")
    if isinstance(additional_headers, dict):
        headers.update({str(k): str(v) for k, v in additional_headers.items()})

    params: Dict[str, Any] = {}
    query_params = extra_config.get("query_params")
    if isinstance(query_params, dict):
        params.update({str(k): v for k, v in query_params.items() if v is not None})

    auth_header = extra_config.get("auth_header")
    if auth_header:
        headers[str(auth_header)] = api_key
    else:
        key_param = str(extra_config.get("api_key_query_param") or "key")
        params.setdefault(key_param, api_key)

    try:
        response = await client.post(base_url, json=request_body, headers=headers, params=params or None)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise LLMError(f"Gemini 响应异常: {exc.response.status_code} {detail}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Gemini 请求失败: {exc}") from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise LLMError("Gemini 返回非 JSON 响应") from exc

    feedback = data.get("promptFeedback") or {}
    block_reason = feedback.get("blockReason")
    if block_reason:
        raise LLMError(f"Gemini 拒绝请求: {block_reason}")

    candidates = data.get("candidates") or []
    content = None
    finish_reason = None
    for candidate in candidates:
        finish_reason = candidate.get("finishReason")
        if finish_reason == "SAFETY":
            raise LLMError("Gemini 由于安全策略拒绝回答")
        if candidate.get("content"):
            content = candidate["content"]
            break

    if not content:
        raise LLMError("Gemini 未返回内容")

    parts = content.get("parts") or []
    texts = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
            if text:
                texts.append(text)
    combined_text = "".join(texts).strip()
    if not combined_text:
        raise LLMError("Gemini 返回内容为空")

    usage_metadata = data.get("usageMetadata") or {}
    usage_payload: Dict[str, Any] = {}
    prompt_tokens = usage_metadata.get("promptTokenCount")
    completion_tokens = usage_metadata.get("candidatesTokenCount")
    if prompt_tokens is not None:
        usage_payload["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        usage_payload["completion_tokens"] = completion_tokens

    chunk: Dict[str, Any] = {
        "choices": [
            {
                "delta": {
                    "content": combined_text,
                },
            }
        ]
    }
    if finish_reason:
        chunk["choices"][0]["finish_reason"] = str(finish_reason).lower()
    if usage_payload:
        chunk["usage"] = usage_payload

    yield json.dumps(chunk, ensure_ascii=False)


async def _completion_openai_stream(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
) -> AsyncGenerator[str, None]:
    async with client.stream("POST", base_url, json=payload, headers=headers) as response:
        if response.status_code >= 400:
            body_bytes = await response.aread()
            try:
                body_text = body_bytes.decode("utf-8")
            except UnicodeDecodeError:
                body_text = str(body_bytes)
            raise LLMError(f"LLM response error: {response.status_code} {body_text}")

        async for line in response.aiter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                yield data


async def _stream_completion_anthropic(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    prompt: str,
    payload_overrides: Optional[Dict[str, Any]],
    extra_config: Dict[str, Any],
    model: Model,
) -> AsyncGenerator[str, None]:
    url = base_url or "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": extra_config.get("anthropic_version") or "2023-06-01",
    }
    default_body: Dict[str, Any] = {
        "model": model.provider,
        "max_tokens": getattr(model, "max_tokens", None) or 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    temperature = getattr(model, "temperature", None)
    top_p = getattr(model, "top_p", None)
    if temperature is not None:
        default_body["temperature"] = temperature
    if top_p is not None:
        default_body["top_p"] = top_p
    thinking_config = _anthropic_thinking_from_model(model, extra_config)
    if thinking_config:
        default_body["thinking"] = thinking_config
    if isinstance(payload_overrides, dict):
        request_body = _deep_merge_dict(default_body, payload_overrides)
    else:
        request_body = default_body
    try:
        response = await client.post(url, json=request_body, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"Anthropic 响应异常: {exc.response.status_code} {exc.response.text.strip()}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Anthropic 请求失败: {exc}") from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise LLMError("Anthropic 返回非 JSON 响应") from exc

    content = data.get("content") or []
    texts: List[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            if part.get("text"):
                texts.append(part["text"])
    combined = "".join(texts).strip()
    usage = data.get("usage") or {}

    first_chunk = {
        "choices": [
            {
                "delta": {
                    "content": combined,
                },
            }
        ]
    }
    yield json.dumps(first_chunk, ensure_ascii=False)
    yield json.dumps(
        {
            "choices": [
                {
                    "finish_reason": data.get("stop_reason") or "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
            },
        },
        ensure_ascii=False,
    )


def _openai_payload_from_model(model: Model, extra_config: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"stream": True}
    max_tokens = getattr(model, "max_tokens", None)
    max_tokens_param = str(extra_config.get("max_tokens_param") or "max_tokens")
    if max_tokens is not None and max_tokens_param in MAX_TOKENS_PARAM_KEYS:
        payload[max_tokens_param] = max_tokens

    temperature = getattr(model, "temperature", None)
    top_p = getattr(model, "top_p", None)
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    reasoning_format = _resolve_reasoning_format(model, extra_config)
    _apply_openai_reasoning(payload, extra_config.get("thinking_level"), reasoning_format)
    return payload


def _resolve_reasoning_format(model: Model, extra_config: Dict[str, Any]) -> str:
    configured = str(extra_config.get("reasoning_format") or "auto").lower()
    if configured in {"openai", "deepseek"}:
        return configured
    marker = f"{getattr(model, 'provider', '')} {getattr(model, 'base_url', '')}".lower()
    if "deepseek" in marker:
        return "deepseek"
    return "openai"


def _apply_openai_reasoning(payload: Dict[str, Any], thinking_level: Any, reasoning_format: str) -> None:
    if thinking_level not in {"low", "medium", "high", "xhigh"}:
        return
    if reasoning_format == "deepseek":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "max" if thinking_level == "xhigh" else "high"
        return
    payload["reasoning_effort"] = thinking_level


def _anthropic_thinking_from_model(model: Model, extra_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    thinking_level = extra_config.get("thinking_level")
    if thinking_level not in {"low", "medium", "high", "xhigh"}:
        return None

    explicit_budget = extra_config.get("thinking_budget_tokens")
    if isinstance(explicit_budget, int) and explicit_budget >= 1024:
        return {"type": "enabled", "budget_tokens": explicit_budget}

    budget_by_level = {
        "low": 1024,
        "medium": 4096,
        "high": 10000,
        "xhigh": 20000,
    }
    budget = budget_by_level[thinking_level]
    max_tokens = getattr(model, "max_tokens", None)
    if max_tokens is not None and max_tokens <= budget:
        budget = max_tokens - 1
    if budget < 1024:
        return None
    return {"type": "enabled", "budget_tokens": budget}


def _generation_config_from_model(model: Model) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    max_tokens = getattr(model, "max_tokens", None)
    temperature = getattr(model, "temperature", None)
    top_p = getattr(model, "top_p", None)
    if max_tokens is not None:
        config["maxOutputTokens"] = max_tokens
    if temperature is not None:
        config["temperature"] = temperature
    if top_p is not None:
        config["topP"] = top_p
    return config


def _deep_merge_dict(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = {k: v for k, v in base.items()}
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result
