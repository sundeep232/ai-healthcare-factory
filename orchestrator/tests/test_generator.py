"""GeneratorAgent tests with a fake Claude (terraform validation off, temp output dir)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.agents.claude_client import ClaudeClient, StructuredOutputError
from orchestrator.agents.generator import GeneratorAgent
from orchestrator.tests.helpers import FakeAnthropic, make_settings, tool_response
from orchestrator.tests.test_terraform_files import golden, load_blueprint
from orchestrator.tools.terraform_files import instance_id


def make_agent(tmp_path: Path, responses: list) -> tuple[GeneratorAgent, FakeAnthropic]:
    fake = FakeAnthropic(responses)
    client = ClaudeClient(make_settings(), client=fake)
    agent = GeneratorAgent(client, validate_with_terraform=False, instances_dir=tmp_path)
    return agent, fake


def good_payload() -> dict[str, str]:
    main, outputs = golden()
    return {"main_tf": main, "outputs_tf": outputs}


def test_generate_writes_instance(tmp_path: Path) -> None:
    agent, fake = make_agent(tmp_path, [tool_response(good_payload(), tool_name="submit_terraform")])
    bp = load_blueprint()

    result = agent.generate(bp)

    assert result.attempts == 1
    assert result.directory == tmp_path / instance_id(bp)
    names = {p.name for p in result.directory.iterdir()}
    assert names == {
        "main.tf", "outputs.tf", "versions.tf", "providers.tf",
        "backend.tf", "variables.tf", "base.tf", "blueprint.json",
    }  # fmt: skip
    saved = json.loads((result.directory / "blueprint.json").read_text(encoding="utf-8"))
    assert saved["blueprint_id"] == bp.blueprint_id
    # The prompt carries real module interfaces and the blueprint, but not the raw requirements.
    call = fake.calls[0]
    assert 'variable "key_vault_id"' in call["system"]
    assert "claims-dash-api" in call["messages"][0]["content"]
    assert call["max_tokens"] == 8000


def test_rule_violation_is_fed_back_and_retried(tmp_path: Path) -> None:
    main, outputs = golden()
    bad = {"main_tf": main + '\nresource "azurerm_resource_group" "x" {\n}\n', "outputs_tf": outputs}
    agent, fake = make_agent(
        tmp_path,
        [
            tool_response(bad, tool_name="submit_terraform"),
            tool_response(good_payload(), tool_name="submit_terraform"),
        ],
    )

    result = agent.generate(load_blueprint())

    assert result.attempts == 2
    feedback = fake.calls[1]["messages"][-1]["content"][0]["content"]
    assert "only contain `module` blocks" in feedback


def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    bad = {"main_tf": "# nothing here", "outputs_tf": ""}
    agent, _ = make_agent(tmp_path, [tool_response(bad, tool_name="submit_terraform")] * 3)

    with pytest.raises(StructuredOutputError):
        agent.generate(load_blueprint())
    assert list(tmp_path.iterdir()) == []  # nothing half-written on failure
