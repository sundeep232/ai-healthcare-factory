"""Test doubles for the Anthropic SDK (no network, no API key needed)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from orchestrator.config import Settings


def make_settings() -> Settings:
    """Settings that never read the real .env."""
    return Settings(claude_api_key="sk-ant-test", _env_file=None)  # type: ignore[call-arg]


def tool_response(
    payload: dict[str, Any],
    *,
    tool_name: str = "tool",
    stop_reason: str = "tool_use",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> SimpleNamespace:
    """Build an object shaped like an Anthropic Message containing one tool_use block."""
    block = SimpleNamespace(type="tool_use", id="toolu_test", name=tool_name, input=payload)
    return SimpleNamespace(
        content=[block],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model="fake-model",
    )


class FakeAnthropic:
    """Returns queued responses in order and records every create() call."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeAnthropic ran out of queued responses")
        return self._responses.pop(0)
