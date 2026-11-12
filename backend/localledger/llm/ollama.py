"""Ollama provider. Only loopback URLs are accepted so prompts never leave the machine."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx

from localledger.llm.base import (
    ChatResponse,
    LLMModelNotFound,
    LLMResponseError,
    LLMUnavailable,
    ModelInfo,
    ToolCall,
)

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def validate_local_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOOPBACK:
        raise ValueError("Ollama URL must point to this machine (127.0.0.1 or localhost).")
    return url.rstrip("/")


class OllamaProvider:
    def __init__(self, base_url: str, *, timeout: float = 300.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = validate_local_url(base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout,
                                    transport=transport, trust_env=False)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise LLMUnavailable("The local model timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable("Ollama is not reachable. Is it running?") from exc

    def health(self) -> dict[str, Any]:
        response = self._request("GET", "/api/version", timeout=3.0)
        if response.status_code != 200:
            raise LLMUnavailable("Ollama responded unexpectedly.")
        return {"version": response.json().get("version")}

    def list_models(self) -> list[ModelInfo]:
        response = self._request("GET", "/api/tags", timeout=5.0)
        if response.status_code != 200:
            raise LLMUnavailable("Could not list Ollama models.")
        return [
            ModelInfo(name=m.get("name", ""), size_bytes=m.get("size"),
                      parameter_size=(m.get("details") or {}).get("parameter_size"))
            for m in response.json().get("models", [])
        ]

    def chat(self, model: str, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]] | None = None) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
        }
        if tools:
            payload["tools"] = tools
        response = self._request("POST", "/api/chat", json=payload)
        if response.status_code == 404:
            raise LLMModelNotFound(f"Model {model!r} is not installed in Ollama.")
        if response.status_code != 200:
            detail = ""
            with contextlib.suppress(ValueError):
                detail = str(response.json().get("error", ""))[:200]
            raise LLMResponseError(f"Ollama returned HTTP {response.status_code}. {detail}")
        try:
            body = response.json()
            message = body["message"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseError("Ollama returned an unreadable response.") from exc
        calls = []
        for call in message.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            calls.append(ToolCall(name=str(fn.get("name", "")), arguments=fn.get("arguments")))
        duration = body.get("total_duration")
        return ChatResponse(
            content=message.get("content") or "",
            tool_calls=calls,
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
            duration_ms=duration / 1e6 if isinstance(duration, int | float) else None,
        )

    def pull(self, model: str) -> Iterator[dict[str, Any]]:
        """Stream download progress. Only ever called after explicit user action."""
        try:
            with self._client.stream("POST", "/api/pull", json={"model": model, "stream": True},
                                     timeout=None) as response:
                if response.status_code != 200:
                    raise LLMResponseError(f"Ollama pull failed (HTTP {response.status_code}).")
                for line in response.iter_lines():
                    if line.strip():
                        yield json.loads(line)
        except httpx.HTTPError as exc:
            raise LLMUnavailable("Ollama is not reachable. Is it running?") from exc
