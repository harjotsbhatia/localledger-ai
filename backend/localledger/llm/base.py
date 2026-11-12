"""Model-agnostic chat interface. Ollama is the first implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    code = "llm_error"


class LLMUnavailable(LLMError):
    code = "llm_unavailable"


class LLMModelNotFound(LLMError):
    code = "model_not_found"


class LLMResponseError(LLMError):
    code = "llm_bad_response"


@dataclass
class ToolCall:
    name: str
    arguments: Any  # dict when well-formed; anything else is handled as malformed


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: float | None = None


@dataclass
class ModelInfo:
    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None


class LLMProvider(Protocol):
    def health(self) -> dict[str, Any]: ...
    def list_models(self) -> list[ModelInfo]: ...
    def chat(self, model: str, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]] | None = None) -> ChatResponse: ...
