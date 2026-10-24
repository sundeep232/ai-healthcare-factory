"""Thin, safe wrapper around the Terraform CLI (init/validate/fmt only).

Nothing here talks to Azure: ``init -backend=false`` and ``validate`` are purely
local. ``apply`` belongs to M4 and is deliberately not exposed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.config import TF_PLUGIN_CACHE_DIR

DEFAULT_TIMEOUT_S = 300


class TerraformNotFoundError(RuntimeError):
    """The terraform executable is not on PATH."""


@dataclass(frozen=True)
class CommandResult:
    """Outcome of one CLI invocation."""

    ok: bool
    output: str


def terraform_path() -> str | None:
    """Return the path to the terraform executable, if installed."""
    return shutil.which("terraform")


def _run(
    args: list[str],
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_S,
    log_path: Path | None = None,
) -> CommandResult:
    """Run terraform. With ``log_path`` the output is appended to that file (for the API)."""
    exe = terraform_path()
    if exe is None:
        raise TerraformNotFoundError(
            "terraform not found on PATH. Install it, e.g. `winget install Hashicorp.Terraform`."
        )
    TF_PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "TF_IN_AUTOMATION": "1",
        "TF_INPUT": "0",
        "TF_PLUGIN_CACHE_DIR": str(TF_PLUGIN_CACHE_DIR),
    }
    if log_path is not None:
        return _run_logged([exe, *args], cwd, env, timeout, log_path)
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [exe, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, f"terraform {args[0]} timed out after {timeout}s")
    return CommandResult(proc.returncode == 0, (proc.stdout + proc.stderr).strip())


def _run_logged(
    argv: list[str], cwd: Path, env: dict[str, str], timeout: int, log_path: Path
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as fh:
        start = fh.tell()
        fh.write(f"\n=== terraform {argv[1]} ===\n".encode())
        fh.flush()
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )  # fmt: skip
            ok = proc.returncode == 0
        except subprocess.TimeoutExpired:
            fh.write(f"\nterraform {argv[1]} timed out after {timeout}s\n".encode())
            ok = False
    with log_path.open("rb") as fh:
        fh.seek(start)
        return CommandResult(ok, fh.read().decode("utf-8", errors="replace").strip())


def fmt(workdir: Path) -> CommandResult:
    """Canonically format all .tf files in ``workdir``."""
    return _run(["fmt", "-no-color"], workdir)


def validate_workspace(workdir: Path) -> list[str]:
    """Run ``init -backend=false`` then ``validate``; return error strings (empty = valid)."""
    init = _run(["init", "-backend=false", "-input=false", "-no-color"], workdir)
    if not init.ok:
        tail = "\n".join(init.output.splitlines()[-15:])
        return [f"terraform init failed:\n{tail}"]

    result = _run(["validate", "-json", "-no-color"], workdir)
    try:
        report = json.loads(result.output)
    except json.JSONDecodeError:
        return [] if result.ok else [f"terraform validate failed:\n{result.output[-1500:]}"]

    errors: list[str] = []
    for diag in report.get("diagnostics", []):
        if diag.get("severity") != "error":
            continue
        rng = diag.get("range") or {}
        where = f"{rng.get('filename', '?')}:{rng.get('start', {}).get('line', '?')}"
        errors.append(f"{where}: {diag.get('summary', '')}. {diag.get('detail', '')}".strip())
    return errors


# -- M4 operations (these talk to Azure and the remote state backend) -----------

APPLY_TIMEOUT_S = 60 * 60  # PostgreSQL / Container Apps can take 10+ minutes


def init_backend(workdir: Path, backend_config: dict[str, str], log_path: Path | None = None) -> CommandResult:
    """`terraform init` against the shared remote state (partial backend config)."""
    args = ["init", "-input=false", "-no-color", "-reconfigure"]
    args += [f"-backend-config={key}={value}" for key, value in backend_config.items()]
    return _run(args, workdir, log_path=log_path)


def plan(workdir: Path, plan_file: str = "tfplan", log_path: Path | None = None) -> CommandResult:
    """Create a saved plan. Changes nothing in Azure."""
    return _run(
        ["plan", "-input=false", "-no-color", f"-out={plan_file}"],
        workdir,
        timeout=APPLY_TIMEOUT_S,
        log_path=log_path,
    )


def show_plan_json(workdir: Path, plan_file: str = "tfplan") -> dict[str, Any]:
    """Return the saved plan as parsed JSON (`terraform show -json`)."""
    result = _run(["show", "-json", "-no-color", plan_file], workdir)
    if not result.ok:
        raise RuntimeError(f"terraform show failed: {result.output[-800:]}")
    return json.loads(result.output)


def apply_plan(workdir: Path, plan_file: str = "tfplan", log_path: Path | None = None) -> CommandResult:
    """Apply exactly the saved plan (no re-planning, no surprises). Creates billable resources."""
    return _run(
        ["apply", "-input=false", "-no-color", plan_file],
        workdir,
        timeout=APPLY_TIMEOUT_S,
        log_path=log_path,
    )


def destroy(workdir: Path, log_path: Path | None = None) -> CommandResult:
    """Tear down everything in this instance's state."""
    return _run(
        ["destroy", "-auto-approve", "-input=false", "-no-color"],
        workdir,
        timeout=APPLY_TIMEOUT_S,
        log_path=log_path,
    )


def output_json(workdir: Path) -> dict[str, Any]:
    """Return {output_name: value} for non-sensitive outputs."""
    result = _run(["output", "-json", "-no-color"], workdir)
    if not result.ok:
        raise RuntimeError(f"terraform output failed: {result.output[-800:]}")
    raw = json.loads(result.output or "{}")
    return {name: spec.get("value") for name, spec in raw.items() if not spec.get("sensitive")}
