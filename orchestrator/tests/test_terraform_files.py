"""Tests for the deterministic parts of M3 (no Claude, no terraform binary)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.config import MODULES_DIR, TEMPLATES_DIR
from orchestrator.schemas import Blueprint
from orchestrator.tools.catalog import CapabilityCatalog
from orchestrator.tools.terraform_files import (
    check_composition,
    instance_id,
    module_interfaces,
    parse_modules,
    render_static_files,
)

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints"
EXAMPLES = TEMPLATES_DIR / "examples"


def load_blueprint(name: str = "example-claims-dashboard.json") -> Blueprint:
    return Blueprint.model_validate(json.loads((BLUEPRINT_DIR / name).read_text(encoding="utf-8")))


def golden() -> tuple[str, str]:
    return (
        (EXAMPLES / "claims-dashboard.main.tf").read_text(encoding="utf-8"),
        (EXAMPLES / "claims-dashboard.outputs.tf").read_text(encoding="utf-8"),
    )


# -- module library ---------------------------------------------------------


def test_every_catalog_type_has_a_module() -> None:
    for type_ in CapabilityCatalog.load().types:
        for fname in ("main.tf", "variables.tf", "outputs.tf", "versions.tf"):
            assert (MODULES_DIR / type_ / fname).is_file(), f"{type_}/{fname} missing"


def test_every_module_takes_the_standard_inputs() -> None:
    for type_ in CapabilityCatalog.load().types:
        variables = (MODULES_DIR / type_ / "variables.tf").read_text(encoding="utf-8")
        for var in ("name", "suffix", "location", "tags"):
            assert f'variable "{var}"' in variables, f"{type_} lacks variable {var}"
        if type_ != "resource_group":
            assert 'variable "resource_group_name"' in variables


def test_module_interfaces_include_used_modules_only() -> None:
    text = module_interfaces(["key_vault", "cosmos_db"])
    assert "modules/key_vault" in text and "modules/cosmos_db" in text
    assert "modules/container_app" not in text
    assert 'variable "suffix"' in text


# -- static file rendering ---------------------------------------------------


def test_render_static_files() -> None:
    bp = load_blueprint()
    files = render_static_files(bp)
    assert set(files) == {"versions.tf", "providers.tf", "backend.tf", "variables.tf", "base.tf"}
    assert bp.blueprint_id in files["base.tf"]
    assert f'default     = "{bp.instance_slug}"' in files["variables.tf"]
    assert f"instances/{instance_id(bp)}.tfstate" in files["backend.tf"]
    assert all("{{" not in text for text in files.values())


def test_instance_id_includes_slug_and_version() -> None:
    bp = load_blueprint()
    assert instance_id(bp) == f"claims-dash-{bp.blueprint_id[:8]}-v1"


def test_unsafe_region_is_rejected() -> None:
    bp = load_blueprint()
    bp.requirements.azure_region = 'eastus2"\n}'
    with pytest.raises(ValueError, match="azure_region"):
        render_static_files(bp)


# -- composition checks -------------------------------------------------------


def test_parse_modules_finds_every_block() -> None:
    main, _ = golden()
    modules = parse_modules(main)
    assert set(modules) == {"rg", "logs", "kv", "db", "api", "web"}
    assert "DB_HOST" in modules["api"] and "module.web" not in modules["api"]


def test_golden_example_passes_checks() -> None:
    main, outputs = golden()
    assert check_composition(load_blueprint(), main, outputs) == []


def test_empty_main_rejected() -> None:
    assert check_composition(load_blueprint(), "  ", "") == ["main_tf is empty"]


def test_raw_resources_rejected() -> None:
    main, outputs = golden()
    main += '\nresource "azurerm_resource_group" "x" {\n  name = "x"\n}\n'
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("only contain `module` blocks" in e for e in errors)


def test_missing_and_extra_modules() -> None:
    main, outputs = golden()
    start = main.index('module "web"')
    main = main[:start] + 'module "bonus" {\n  source = "../../modules/key_vault"\n}\n'
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("missing module blocks" in e and "web" in e for e in errors)
    assert any("not in the blueprint" in e and "bonus" in e for e in errors)


def test_wrong_module_source() -> None:
    main, outputs = golden()
    main = main.replace("../../modules/key_vault", "../../modules/storage_account")
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("module 'kv'" in e and "source must be" in e for e in errors)


def test_dependency_must_be_visible() -> None:
    main, outputs = golden()
    # api depends on logs; drop every reference to it.
    main = main.replace("  log_analytics_workspace_id = module.logs.id\n", "")
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("depends on 'logs'" in e for e in errors)


def test_explicit_depends_on_satisfies_dependency() -> None:
    main, outputs = golden()
    main = main.replace(
        "  log_analytics_workspace_id = module.logs.id\n", "  depends_on = [module.logs]\n"
    )
    assert check_composition(load_blueprint(), main, outputs) == []


def test_hardcoded_guid_rejected() -> None:
    main, outputs = golden()
    main = main.replace(
        "tags     = local.tags", 'tags     = { sub = "ed52f831-6c7b-4453-9bfe-ea9b770158d6" }', 1
    )
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("GUID" in e for e in errors)


def test_secret_outputs_rejected() -> None:
    main, outputs = golden()
    outputs += '\noutput "pw" {\n  value = module.db.admin_password\n}\n'
    errors = check_composition(load_blueprint(), main, outputs)
    assert any("must not expose secrets" in e for e in errors)


def test_outputs_may_only_contain_outputs() -> None:
    main, _ = golden()
    errors = check_composition(load_blueprint(), main, 'variable "x" {\n}\n')
    assert any("outputs_tf may only contain" in e for e in errors)


def test_key_vault_id_requires_literal_store_flag() -> None:
    main, outputs = golden()
    # Claude forgets the flag -> the secret would silently never be stored.
    forgot = main.replace("  store_admin_password = true\n", "")
    errors = check_composition(load_blueprint(), forgot, outputs)
    assert any("store_admin_password = true" in e for e in errors)


def test_store_flag_must_be_a_literal() -> None:
    main, outputs = golden()
    derived = main.replace("store_admin_password = true", "store_admin_password = module.kv.id != null")
    errors = check_composition(load_blueprint(), derived, outputs)
    assert any("literal" in e for e in errors)


def test_store_flag_without_vault_is_rejected() -> None:
    main, outputs = golden()
    no_vault = main.replace("  key_vault_id         = module.kv.id\n", "")
    errors = check_composition(load_blueprint(), no_vault, outputs)
    assert any("requires key_vault_id" in e for e in errors)
