"""M4 Compose: turn a generated Terraform instance into live Azure resources.

Deterministic (no LLM). Safety rules:
  * state lives in the shared remote backend, never on local disk;
  * we always apply the *saved plan* we just inspected, never a fresh one;
  * a plan that deletes anything is refused unless explicitly allowed;
  * everything is logged to <instance>/logs/terraform.log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.config import INSTANCES_DIR, Settings
from orchestrator.schemas.demo import PlanSummary
from orchestrator.tools import terraform_runner as default_runner

PLAN_FILE = "tfplan"
# Azure error fragments that mean "not allowed / not available in this region".
_CAPACITY_MARKERS = (
    "restricted from provisioning",
    "LocationNotAvailableForResourceType",
    "SkuNotAvailable",
    "ParameterOutOfRange",
    "RegionIsOfferRestricted",
)
LOG_RELATIVE = Path("logs") / "terraform.log"


class ComposeError(RuntimeError):
    """A Terraform step failed or a safety rule refused to continue."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.detail = message


class ComposeConfigError(ComposeError):
    """Required Azure/state settings are missing."""


def summarize_plan(plan_json: dict[str, Any]) -> PlanSummary:
    """Count creates/updates/deletes in `terraform show -json` output.

    A replacement (["delete","create"]) counts as both a delete and a create, which
    is what makes the deletion guard trip on it.
    """
    add = change = destroy = 0
    resources: list[str] = []
    for rc in plan_json.get("resource_changes", []):
        actions = set(rc.get("change", {}).get("actions", []))
        if actions <= {"no-op", "read"}:
            continue
        add += "create" in actions
        change += "update" in actions
        destroy += "delete" in actions
        resources.append(rc["address"])
    return PlanSummary(add=add, change=change, destroy=destroy, resources=resources)


class ComposerAgent:
    """Runs init/plan/apply/destroy for one instance directory."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: Any = default_runner,
        instances_dir: Path = INSTANCES_DIR,
    ) -> None:
        self._settings = settings
        self._tf = runner  # injectable for tests
        self._instances_dir = instances_dir

    # -- public steps ------------------------------------------------------

    def plan(self, instance_dir: str) -> PlanSummary:
        """init + plan. Safe: makes no changes to Azure resources."""
        workdir = self._workdir(instance_dir)
        self._prepare(workdir)
        log = workdir / LOG_RELATIVE
        self._check("plan", self._tf.plan(workdir, PLAN_FILE, log_path=log))
        try:
            return summarize_plan(self._tf.show_plan_json(workdir, PLAN_FILE))
        except (RuntimeError, json.JSONDecodeError) as exc:
            raise ComposeError("plan", f"could not read the saved plan: {exc}") from exc

    def deploy(self, instance_dir: str, *, allow_destroy: bool = False) -> tuple[PlanSummary, dict[str, Any]]:
        """init + plan + apply the saved plan; returns (plan summary, outputs).

        Raises:
            ComposeError: On any Terraform failure, or if the plan deletes resources
                and ``allow_destroy`` is false (nothing is applied in that case).
        """
        summary = self.plan(instance_dir)
        if summary.has_deletions and not allow_destroy:
            raise ComposeError(
                "plan",
                f"refusing to apply: plan would delete {summary.destroy} resource(s): "
                f"{', '.join(summary.resources)}",
            )
        workdir = self._workdir(instance_dir)
        self._check("apply", self._tf.apply_plan(workdir, PLAN_FILE, log_path=workdir / LOG_RELATIVE))
        return summary, self.outputs(instance_dir)

    def outputs(self, instance_dir: str) -> dict[str, Any]:
        """Non-sensitive root outputs of the deployed instance."""
        try:
            return self._tf.output_json(self._workdir(instance_dir))
        except (RuntimeError, json.JSONDecodeError) as exc:
            raise ComposeError("output", str(exc)) from exc

    def destroy(self, instance_dir: str) -> None:
        """Tear down every resource in the instance's state."""
        workdir = self._workdir(instance_dir)
        self._prepare(workdir)
        self._check("destroy", self._tf.destroy(workdir, log_path=workdir / LOG_RELATIVE))

    def read_log(self, instance_dir: str, tail: int = 200) -> str:
        """Last ``tail`` lines of the instance's terraform log ('' if none yet)."""
        path = self._workdir(instance_dir) / LOG_RELATIVE
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-tail:])

    # -- internals ---------------------------------------------------------

    def _workdir(self, instance_dir: str) -> Path:
        """Resolve an instance folder name, refusing anything outside instances/."""
        root = self._instances_dir.resolve()
        # Must be a bare folder name: no separators, no "..", nothing absolute.
        if not instance_dir or Path(instance_dir).name != instance_dir or instance_dir in {".", ".."}:
            raise ComposeError("prepare", f"unknown instance directory '{instance_dir}'")
        path = (root / instance_dir).resolve()
        if path.parent != root or not path.is_dir():
            raise ComposeError("prepare", f"unknown instance directory '{instance_dir}'")
        return path

    def _prepare(self, workdir: Path) -> None:
        """Write tfvars and init against the shared remote state."""
        s = self._settings
        missing = [
            name
            for name, value in (
                ("AZURE_SUBSCRIPTION_ID", s.azure_subscription_id),
                ("TFSTATE_STORAGE_ACCOUNT", s.tfstate_storage_account),
            )
            if not value
        ]
        if missing:
            raise ComposeConfigError(
                "prepare", f"missing settings: {', '.join(missing)} (run scripts/sync-env-from-bootstrap.ps1)"
            )
        (workdir / "terraform.tfvars.json").write_text(
            json.dumps({"subscription_id": s.azure_subscription_id}, indent=2) + "\n", encoding="utf-8"
        )
        backend = {
            "resource_group_name": s.tfstate_resource_group,
            "storage_account_name": s.tfstate_storage_account,
            "container_name": s.tfstate_container,
        }
        self._check("init", self._tf.init_backend(workdir, backend, log_path=workdir / LOG_RELATIVE))

    @staticmethod
    def _check(stage: str, result: Any) -> None:
        if not result.ok:
            tail = "\n".join(result.output.splitlines()[-25:])
            message = f"terraform {stage} failed:\n{tail}"
            if any(marker in result.output for marker in _CAPACITY_MARKERS):
                message += (
                    "\n\nHint: Azure refused this service/SKU in this region for your subscription. "
                    "Pick another region (set DEMO_LOCATION or say 'in <region>' in the intent), "
                    "destroy this demo, and regenerate."
                )
            raise ComposeError(stage, message)
