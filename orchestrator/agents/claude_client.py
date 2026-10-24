"""Thin wrapper around the Anthropic SDK for validated, structured output.

Structured output is obtained by forcing a tool call whose input schema is a
Pydantic model's JSON schema. The returned input is validated with Pydantic and
optional semantic validators; on failure the errors are fed back to Claude for a
bounded number of retries.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from orchestrator.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
SemanticValidator = Callable[[T], list[str]]


class StructuredOutputError(RuntimeError):
    """Claude could not produce valid structured output within the attempt budget."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


@dataclass
class Usage:
    """Accumulated token usage across attempts."""

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


@dataclass
class StructuredResult(Generic[T]):
    """A validated model instance plus call metadata."""

    data: T
    usage: Usage = field(default_factory=Usage)
    attempts: int = 1
    model: str = ""


def _format_validation_errors(exc: ValidationError) -> list[str]:
    """Flatten Pydantic errors to short 'path: message' strings."""
    return [
        f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors()
    ]


class ClaudeClient:
    """Calls Claude and returns schema-validated results."""

    def __init__(self, settings: Settings, client: anthropic.Anthropic | Any | None = None) -> None:
        """Create a client.

        Args:
            settings: Application settings (API key, model, token limit).
            client: Optional pre-built Anthropic client (used for testing).
        """
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens
        self._client = client or anthropic.Anthropic(
            api_key=settings.claude_api_key.get_secret_value()
        )

    def structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[T],
        tool_name: str,
        tool_description: str,
        validators: Sequence[SemanticValidator[T]] = (),
        max_attempts: int = 2,
        max_tokens: int | None = None,
    ) -> StructuredResult[T]:
        """Get a validated ``output_model`` instance from Claude.

        Args:
            system: System prompt.
            user: User message.
            output_model: Pydantic model describing the required output.
            tool_name: Name of the forced tool.
            tool_description: What the tool represents (shown to Claude).
            validators: Extra checks returning a list of error strings (empty = ok).
            max_attempts: Total tries including retries with error feedback.
            max_tokens: Override the default output token budget for this call.

        Raises:
            StructuredOutputError: If no valid output within ``max_attempts``.
            anthropic.APIError: For API/auth/network failures (not retried here).
        """
        tool = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": output_model.model_json_schema(),
        }
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        usage = Usage()
        errors: list[str] = []

        for attempt in range(1, max_attempts + 1):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                system=system,
                messages=messages,
                tools=[tool],
                # Newer models reject forced tool_choice ("tool"/"any"), so use "auto"
                # and rely on the prompt + the retry below if Claude answers in prose.
                tool_choice={"type": "auto"},
            )
            usage.add(response.usage.input_tokens, response.usage.output_tokens)

            if response.stop_reason == "max_tokens":
                raise StructuredOutputError(
                    "Claude's output was truncated (max_tokens); raise CLAUDE_MAX_TOKENS"
                )

            block = next((b for b in response.content if getattr(b, "type", "") == "tool_use"), None)
            if block is None:
                errors = [f"You must respond by calling the `{tool_name}` tool, not with text."]
                logger.warning("Attempt %d/%d: no tool call in response", attempt, max_attempts)
                text = "".join(
                    getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
                )
                messages.append({"role": "assistant", "content": text or "(no tool call)"})
                messages.append({"role": "user", "content": errors[0]})
                continue

            parsed: T | None = None
            try:
                parsed = output_model.model_validate(block.input)
                errors = []
                for validator in validators:
                    errors.extend(validator(parsed))
            except ValidationError as exc:
                errors = _format_validation_errors(exc)

            if not errors and parsed is not None:
                return StructuredResult(
                    data=parsed, usage=usage, attempts=attempt, model=response.model
                )

            logger.warning("Attempt %d/%d failed validation: %s", attempt, max_attempts, errors)
            # Feed the errors back so the next attempt can correct them.
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": block.id, "name": tool_name, "input": block.input}
                    ],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": "Your output was invalid. Fix these problems and call the tool again:\n"
                            + "\n".join(f"- {e}" for e in errors),
                        }
                    ],
                }
            )

        raise StructuredOutputError(
            f"No valid output after {max_attempts} attempts", errors=errors
        )
