"""Agent tests using a fake Anthropic client (offline)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from helpers import FakeAnthropic, make_settings, tool_response
from orchestrator.agents import (
    ClaudeClient,
    InterpreterAgent,
    PlannerAgent,
    StructuredOutputError,
)
from orchestrator.schemas import Requirements
from orchestrator.tools.catalog import CapabilityCatalog

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints"


def example() -> dict[str, Any]:
    return json.loads((BLUEPRINT_DIR / "example-claims-dashboard.json").read_text(encoding="utf-8"))


def draft_payload() -> dict[str, Any]:
    """The Claude-facing part of the example (no identity/requirements)."""
    data = example()
    return {k: data[k] for k in ("instance_slug", "summary", "resources", "data_plan")}


def client_with(responses: list[Any]) -> tuple[ClaudeClient, FakeAnthropic]:
    fake = FakeAnthropic(responses)
    return ClaudeClient(make_settings(), client=fake), fake


class Greeting(BaseModel):
    text: str


class TestClaudeClient:
    def test_returns_validated_model_and_usage(self) -> None:
        client, fake = client_with([tool_response({"text": "hi"}, input_tokens=7, output_tokens=3)])
        result = client.structured(
            system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
        )
        assert result.data.text == "hi"
        assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 3)
        assert result.attempts == 1
        # Forced tool_choice is unsupported on newer models, so "auto" is used.
        assert fake.calls[0]["tool_choice"] == {"type": "auto"}
        assert fake.calls[0]["tools"][0]["name"] == "t"

    def test_prose_answer_is_pushed_back_then_retried(self) -> None:
        prose = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Sure! Here is the answer...")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            model="fake-model",
        )
        client, fake = client_with([prose, tool_response({"text": "ok"})])
        result = client.structured(
            system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
        )
        assert result.data.text == "ok" and result.attempts == 2
        assert "must respond by calling" in fake.calls[1]["messages"][-1]["content"]

    def test_never_calling_tool_raises(self) -> None:
        prose = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="nope")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            model="fake-model",
        )
        client, _ = client_with([prose, prose])
        with pytest.raises(StructuredOutputError) as exc:
            client.structured(
                system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
            )
        assert any("tool" in e for e in exc.value.errors)

    def test_retries_with_feedback_on_schema_error(self) -> None:
        client, fake = client_with([tool_response({"wrong": 1}), tool_response({"text": "ok"})])
        result = client.structured(
            system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
        )
        assert result.attempts == 2
        assert result.usage.input_tokens == 200  # accumulated across attempts
        feedback = fake.calls[1]["messages"][-1]["content"][0]
        assert feedback["is_error"] is True and "text" in feedback["content"]

    def test_retries_on_semantic_validator_error(self) -> None:
        client, _ = client_with([tool_response({"text": "bad"}), tool_response({"text": "good"})])
        result = client.structured(
            system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d",
            validators=[lambda g: ["must be good"] if g.text != "good" else []],
        )
        assert result.data.text == "good" and result.attempts == 2

    def test_raises_after_attempt_budget(self) -> None:
        client, _ = client_with([tool_response({"wrong": 1}), tool_response({"wrong": 2})])
        with pytest.raises(StructuredOutputError) as exc:
            client.structured(
                system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
            )
        assert exc.value.errors

    def test_truncated_output_fails_fast(self) -> None:
        client, fake = client_with([tool_response({"text": "x"}, stop_reason="max_tokens")])
        with pytest.raises(StructuredOutputError, match="truncated"):
            client.structured(
                system="s", user="u", output_model=Greeting, tool_name="t", tool_description="d"
            )
        assert len(fake.calls) == 1  # retrying a truncation would not help


class TestInterpreter:
    def test_interpret_builds_requirements(self) -> None:
        reqs = example()["requirements"]
        client, fake = client_with([tool_response(reqs)])
        result = InterpreterAgent(client).interpret("Show claims analytics to execs")
        assert isinstance(result.data, Requirements)
        assert result.data.data_scale.member_count == 5000
        # Untrusted intent must be delimited as data in the user message.
        assert fake.calls[0]["messages"][0]["content"].startswith("<intent>")

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 4001])
    def test_rejects_bad_intent_without_calling_api(self, bad: str) -> None:
        client, fake = client_with([])
        with pytest.raises(ValueError):
            InterpreterAgent(client).interpret(bad)
        assert fake.calls == []


class TestPlanner:
    def requirements(self) -> Requirements:
        return Requirements.model_validate(example()["requirements"])

    def test_plan_produces_versioned_blueprint(self) -> None:
        client, _ = client_with([tool_response(draft_payload())])
        result = PlannerAgent(client, CapabilityCatalog.load()).plan(self.requirements())
        bp = result.data
        assert bp.version == 1 and bp.parent_version is None
        assert bp.requirements.demo_name == "Claims Analytics Dashboard"
        assert bp.blueprint_id  # assigned by the system, not by Claude

    def test_replan_increments_version(self) -> None:
        client, _ = client_with([tool_response(draft_payload()), tool_response(draft_payload())])
        planner = PlannerAgent(client, CapabilityCatalog.load())
        v1 = planner.plan(self.requirements()).data
        v2 = planner.plan(self.requirements(), parent=v1).data
        assert (v2.version, v2.parent_version) == (2, 1)

    def test_catalog_violation_triggers_retry_then_succeeds(self) -> None:
        bad = copy.deepcopy(draft_payload())
        bad["resources"][2]["type"] = "oracle_exadata"
        client, fake = client_with([tool_response(bad), tool_response(draft_payload())])
        result = PlannerAgent(client, CapabilityCatalog.load()).plan(self.requirements())
        assert result.attempts == 2
        feedback = fake.calls[1]["messages"][-1]["content"][0]["content"]
        assert "oracle_exadata" in feedback

    def test_persistent_violation_raises(self) -> None:
        bad = copy.deepcopy(draft_payload())
        bad["resources"][2]["sku"] = "NOPE"
        client, _ = client_with([tool_response(bad), tool_response(bad)])
        with pytest.raises(StructuredOutputError):
            PlannerAgent(client, CapabilityCatalog.load()).plan(self.requirements())

    def test_catalog_is_embedded_in_system_prompt(self) -> None:
        client, fake = client_with([tool_response(draft_payload())])
        PlannerAgent(client, CapabilityCatalog.load()).plan(self.requirements())
        system = fake.calls[0]["system"]
        assert "postgresql_flexible" in system and "{{CATALOG}}" not in system


def test_interpreter_prompt_uses_configured_default_region() -> None:
    client = ClaudeClient(make_settings(), client=FakeAnthropic([]))
    agent = InterpreterAgent(client, default_region="northeurope")
    assert "region northeurope" in agent._system
    assert "{{" not in agent._system
