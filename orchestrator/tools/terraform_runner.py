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


def _run(args: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT_S) -> CommandResult:
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
