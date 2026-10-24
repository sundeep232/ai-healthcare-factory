"""Real `terraform validate` runs (offline except for the first provider download).

Skipped automatically when the terraform binary is not installed.
"""

from __future__ import annotations

import shutil
import uuid

import pytest

from orchestrator.config import INSTANCES_DIR, MODULES_DIR
from orchestrator.tests.test_terraform_files import golden, load_blueprint
from orchestrator.tools import terraform_runner
from orchestrator.tools.catalog import CapabilityCatalog
from orchestrator.tools.terraform_files import render_static_files

pytestmark = pytest.mark.skipif(
    terraform_runner.terraform_path() is None, reason="terraform is not installed"
)


@pytest.mark.parametrize("type_", CapabilityCatalog.load().types)
def test_module_validates(type_: str) -> None:
    assert terraform_runner.validate_workspace(MODULES_DIR / type_) == []


def test_golden_composition_validates() -> None:
    """The reference main.tf + generated static files form a valid root module."""
    main, outputs = golden()
    workspace = INSTANCES_DIR / f"_test-{uuid.uuid4().hex[:8]}"
    try:
        workspace.mkdir(parents=True)
        files = {**render_static_files(load_blueprint()), "main.tf": main, "outputs.tf": outputs}
        for name, content in files.items():
            (workspace / name).write_text(content, encoding="utf-8")
        assert terraform_runner.validate_workspace(workspace) == []
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_validate_reports_bad_wiring() -> None:
    """A reference to a non-existent module output yields a readable file:line error."""
    main, outputs = golden()
    broken = main.replace("module.db.fqdn", "module.db.hostname")
    assert broken != main
    workspace = INSTANCES_DIR / f"_test-{uuid.uuid4().hex[:8]}"
    try:
        workspace.mkdir(parents=True)
        files = {**render_static_files(load_blueprint()), "main.tf": broken, "outputs.tf": outputs}
        for name, content in files.items():
            (workspace / name).write_text(content, encoding="utf-8")
        errors = terraform_runner.validate_workspace(workspace)
        assert errors and any("main.tf" in e for e in errors)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
