"""ComposerAgent tests with a fake terraform runner (no Azure, no binary)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.agents.composer import (
    ComposeConfigError,
    ComposeError,
    ComposerAgent,
    summarize_plan,
)
from orchestrator.config import Settings
from orchestrator.tools.terraform_runner import CommandResult


class FakeTerraform:
    """Records calls; behaviour is scripted through attributes."""

    def __init__(self, plan_changes: list[list[str]] | None = None) -> None:
        self.calls: list[str] = []
        self.backend: dict[str, str] = {}
        self.fail_at: str | None = None
        self.plan_changes = plan_changes if plan_changes is not None else [["create"]] * 3

    def _result(self, step: str) -> CommandResult:
        self.calls.append(step)
        if self.fail_at == step:
            return CommandResult(False, "line1\nError: boom on " + step)
        return CommandResult(True, "ok")

    def init_backend(self, workdir: Path, backend_config: dict[str, str], log_path: Path | None = None):
        self.backend = backend_config
        return self._result("init")

    def plan(self, workdir: Path, plan_file: str = "tfplan", log_path: Path | None = None):
        return self._result("plan")

    def show_plan_json(self, workdir: Path, plan_file: str = "tfplan") -> dict[str, Any]:
        self.calls.append("show")
        return {
            "resource_changes": [
                {"address": f"module.m{i}.thing", "change": {"actions": a}}
                for i, a in enumerate(self.plan_changes)
            ]
        }

    def apply_plan(self, workdir: Path, plan_file: str = "tfplan", log_path: Path | None = None):
        return self._result("apply")

    def destroy(self, workdir: Path, log_path: Path | None = None):
        return self._result("destroy")

    def output_json(self, workdir: Path) -> dict[str, Any]:
        self.calls.append("output")
        return {"web_url": "https://example.test"}


def settings(**overrides: str) -> Settings:
    values = {
        "azure_subscription_id": "00000000-0000-0000-0000-000000000000",
        "tfstate_storage_account": "stfake",
        **overrides,
    }
    return Settings(claude_api_key="sk-ant-test", _env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def instances(tmp_path: Path) -> Path:
    (tmp_path / "demo-1").mkdir()
    return tmp_path


def make(instances: Path, tf: FakeTerraform, **overrides: str) -> ComposerAgent:
    return ComposerAgent(settings(**overrides), runner=tf, instances_dir=instances)


def test_summarize_plan_counts_replace_as_create_and_delete() -> None:
    summary = summarize_plan(
        {
            "resource_changes": [
                {"address": "a", "change": {"actions": ["create"]}},
                {"address": "b", "change": {"actions": ["update"]}},
                {"address": "c", "change": {"actions": ["delete", "create"]}},
                {"address": "d", "change": {"actions": ["no-op"]}},
                {"address": "e", "change": {"actions": ["read"]}},
            ]
        }
    )
    assert (summary.add, summary.change, summary.destroy) == (2, 1, 1)
    assert summary.resources == ["a", "b", "c"]
    assert summary.has_deletions


def test_deploy_runs_steps_in_order_and_returns_outputs(instances: Path) -> None:
    tf = FakeTerraform()
    summary, outputs = make(instances, tf).deploy("demo-1")

    assert tf.calls == ["init", "plan", "show", "apply", "output"]
    assert summary.add == 3
    assert outputs == {"web_url": "https://example.test"}
    assert tf.backend == {
        "resource_group_name": "rg-factory-shared",
        "storage_account_name": "stfake",
        "container_name": "tfstate",
    }
    tfvars = json.loads((instances / "demo-1" / "terraform.tfvars.json").read_text())
    assert tfvars == {"subscription_id": "00000000-0000-0000-0000-000000000000"}


def test_deploy_refuses_plans_with_deletions(instances: Path) -> None:
    tf = FakeTerraform(plan_changes=[["create"], ["delete"]])
    with pytest.raises(ComposeError, match="refusing to apply") as exc:
        make(instances, tf).deploy("demo-1")
    assert exc.value.stage == "plan"
    assert "apply" not in tf.calls


def test_deploy_can_allow_destroy_explicitly(instances: Path) -> None:
    tf = FakeTerraform(plan_changes=[["delete", "create"]])
    make(instances, tf).deploy("demo-1", allow_destroy=True)
    assert "apply" in tf.calls


@pytest.mark.parametrize("step", ["init", "plan", "apply"])
def test_failures_carry_stage_and_output_tail(instances: Path, step: str) -> None:
    tf = FakeTerraform()
    tf.fail_at = step
    with pytest.raises(ComposeError) as exc:
        make(instances, tf).deploy("demo-1")
    assert exc.value.stage == step
    assert f"Error: boom on {step}" in exc.value.detail


def test_plan_only_never_applies(instances: Path) -> None:
    tf = FakeTerraform()
    make(instances, tf).plan("demo-1")
    assert tf.calls == ["init", "plan", "show"]


def test_destroy(instances: Path) -> None:
    tf = FakeTerraform()
    make(instances, tf).destroy("demo-1")
    assert tf.calls == ["init", "destroy"]


def test_missing_settings_fail_before_touching_terraform(instances: Path) -> None:
    tf = FakeTerraform()
    with pytest.raises(ComposeConfigError, match="TFSTATE_STORAGE_ACCOUNT"):
        make(instances, tf, tfstate_storage_account="").plan("demo-1")
    assert tf.calls == []


@pytest.mark.parametrize("name", ["../etc", "..", "missing", "demo-1/../demo-1", "C:\\Windows"])
def test_instance_dir_cannot_escape_instances_root(instances: Path, name: str) -> None:
    with pytest.raises(ComposeError, match="unknown instance directory"):
        make(instances, FakeTerraform()).plan(name)


def test_read_log(instances: Path) -> None:
    composer = make(instances, FakeTerraform())
    assert composer.read_log("demo-1") == ""
    log = instances / "demo-1" / "logs" / "terraform.log"
    log.parent.mkdir()
    log.write_text("\n".join(f"line {i}" for i in range(10)), encoding="utf-8")
    assert composer.read_log("demo-1", tail=3) == "line 7\nline 8\nline 9"


def test_region_restriction_errors_get_a_hint(instances: Path) -> None:
    class Restricted(FakeTerraform):
        def apply_plan(self, workdir, plan_file="tfplan", log_path=None):
            return CommandResult(False, "Error: ParameterOutOfRange: The value of the 'Version' should be in: []")

    with pytest.raises(ComposeError) as exc:
        make(instances, Restricted()).deploy("demo-1")
    assert "Pick another region" in exc.value.detail


def test_ordinary_errors_get_no_region_hint(instances: Path) -> None:
    tf = FakeTerraform()
    tf.fail_at = "apply"
    with pytest.raises(ComposeError) as exc:
        make(instances, tf).deploy("demo-1")
    assert "Hint" not in exc.value.detail
