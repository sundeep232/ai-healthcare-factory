"""Deterministic pieces of M3: static root files, module docs, composition checks.

Claude only writes ``main.tf`` (module wiring) and ``outputs.tf``. Everything that
could cause damage if hallucinated (providers, backend, naming, state key) is
rendered from reviewed templates, and Claude's output is checked by rules here
before it is ever handed to ``terraform validate``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from orchestrator.config import MODULES_DIR, TEMPLATES_DIR
from orchestrator.schemas.blueprint import Blueprint

# template file -> output file name
STATIC_TEMPLATES: dict[str, str] = {
    "versions.tf.tmpl": "versions.tf",
    "providers.tf.tmpl": "providers.tf",
    "backend.tf.tmpl": "backend.tf",
    "variables.tf.tmpl": "variables.tf",
    "base.tf.tmpl": "base.tf",
}

_REGION_RE = re.compile(r"^[a-z0-9]{3,40}$")
_GUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
_SECRET_OUTPUT_RE = re.compile(
    r"password|primary_key|secondary_key|connection_string|access_key|api_key", re.IGNORECASE
)
# A block header at column 0: keyword, optional quoted labels, then "{".
_TOP_LEVEL_BLOCK_RE = re.compile(r'^(\w+)(?:\s+"[^"]*")*\s*\{', re.MULTILINE)
_MODULE_START_RE = re.compile(r'^module\s+"([^"]+)"\s*\{', re.MULTILINE)
_SOURCE_RE = re.compile(r'^\s*source\s*=\s*"([^"]+)"', re.MULTILINE)


def instance_id(blueprint: Blueprint) -> str:
    """Stable folder/state-key name for a blueprint version: <slug>-<id8>-v<version>."""
    return f"{blueprint.instance_slug}-{blueprint.blueprint_id[:8]}-v{blueprint.version}"


def render_static_files(blueprint: Blueprint, templates_dir: Path = TEMPLATES_DIR) -> dict[str, str]:
    """Render providers/backend/variables/base files from templates (no LLM involved)."""
    region = blueprint.requirements.azure_region
    if not _REGION_RE.match(region):
        raise ValueError(f"Unsafe azure_region value: {region!r}")

    values = {
        "SLUG": blueprint.instance_slug,
        "LOCATION": region,
        "BLUEPRINT_ID": blueprint.blueprint_id,
        "VERSION": str(blueprint.version),
        "TTL_DAYS": str(blueprint.requirements.ttl_days),
        "INSTANCE_ID": instance_id(blueprint),
    }
    files: dict[str, str] = {}
    for template_name, out_name in STATIC_TEMPLATES.items():
        text = (templates_dir / template_name).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        if "{{" in text:
            raise ValueError(f"Unfilled placeholder in template {template_name}")
        files[out_name] = text
    return files


def module_interfaces(types: Iterable[str], modules_dir: Path = MODULES_DIR) -> str:
    """Concatenate each used module's variables.tf and outputs.tf for the prompt.

    Reading the real files (rather than a hand-written summary) means the docs
    given to Claude can never drift from the actual module interfaces.
    """
    sections: list[str] = []
    for type_ in sorted(set(types)):
        mod = modules_dir / type_
        variables = (mod / "variables.tf").read_text(encoding="utf-8")
        outputs = (mod / "outputs.tf").read_text(encoding="utf-8")
        sections.append(
            f"### module: ../../modules/{type_}\n"
            f"```hcl\n# variables.tf\n{variables.strip()}\n\n# outputs.tf\n{outputs.strip()}\n```"
        )
    return "\n\n".join(sections)


def _block_end(text: str, open_idx: int) -> int:
    """Index just past the brace matching the '{' at ``open_idx`` (skips quoted strings)."""
    depth = 0
    in_string = False
    i = open_idx
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def parse_modules(main_tf: str) -> dict[str, str]:
    """Return {module_label: block_text} for every top-level module block."""
    modules: dict[str, str] = {}
    for match in _MODULE_START_RE.finditer(main_tf):
        end = _block_end(main_tf, match.end() - 1)
        modules[match.group(1)] = main_tf[match.start() : end]
    return modules


def _top_level_kinds(text: str) -> set[str]:
    """Block keywords appearing at column 0 (module, resource, output, ...)."""
    return {m.group(1) for m in _TOP_LEVEL_BLOCK_RE.finditer(text)}


def check_composition(blueprint: Blueprint, main_tf: str, outputs_tf: str) -> list[str]:
    """Return rule violations in Claude's main.tf / outputs.tf (empty = acceptable)."""
    errors: list[str] = []

    if not main_tf.strip():
        return ["main_tf is empty"]

    # 1. main.tf is composition only: modules, no raw resources/providers/backends.
    bad_kinds = _top_level_kinds(main_tf) - {"module"}
    if bad_kinds:
        errors.append(
            f"main_tf may only contain `module` blocks; found: {sorted(bad_kinds)}. "
            "providers, backend, variables, random suffix and locals already exist."
        )
    if outputs_tf.strip():
        bad_out = _top_level_kinds(outputs_tf) - {"output"}
        if bad_out:
            errors.append(f"outputs_tf may only contain `output` blocks; found: {sorted(bad_out)}")

    # 2. One module block per blueprint resource, labelled by resource id.
    modules = parse_modules(main_tf)
    expected = {r.id: r for r in blueprint.resources}
    missing = sorted(set(expected) - set(modules))
    extra = sorted(set(modules) - set(expected))
    if missing:
        errors.append(f"missing module blocks for resource ids: {missing}")
    if extra:
        errors.append(f"module blocks not in the blueprint: {extra}")

    # 3. Each module must use the right catalog module and honour depends_on.
    for res_id, res in expected.items():
        block = modules.get(res_id)
        if block is None:
            continue
        source = _SOURCE_RE.search(block)
        want = f"../../modules/{res.type}"
        if not source or source.group(1) != want:
            got = source.group(1) if source else None
            errors.append(f"module '{res_id}': source must be \"{want}\", got {got!r}")
        for dep in res.depends_on:
            if f"module.{dep}" not in block:
                errors.append(
                    f"module '{res_id}': blueprint says it depends on '{dep}' but the block never "
                    f"references module.{dep} (use its outputs or add depends_on = [module.{dep}])"
                )

    # 3b. Plan-time rule: the secret flag must be a literal, and must accompany key_vault_id.
    #     (`terraform validate` can't see this; only a real `plan` does.)
    for res_id, res in expected.items():
        block = modules.get(res_id)
        if block is None or res.type != "postgresql_flexible":
            continue
        has_vault = re.search(r"^\s*key_vault_id\s*=", block, re.MULTILINE) is not None
        flag = re.search(r"^\s*store_admin_password\s*=\s*(\S+)", block, re.MULTILINE)
        if has_vault and not (flag and flag.group(1) == "true"):
            errors.append(
                f"module '{res_id}': when key_vault_id is set you must also set the literal "
                "`store_admin_password = true`"
            )
        if flag and flag.group(1) not in {"true", "false"}:
            errors.append(
                f"module '{res_id}': store_admin_password must be the literal true or false, "
                f"got {flag.group(1)!r}"
            )
        if flag and flag.group(1) == "true" and not has_vault:
            errors.append(f"module '{res_id}': store_admin_password = true requires key_vault_id")

    # 4. Safety: no hard-coded subscription/tenant IDs, no secrets in root outputs.
    for fname, text in (("main_tf", main_tf), ("outputs_tf", outputs_tf)):
        if _GUID_RE.search(text):
            errors.append(f"{fname}: contains a hard-coded GUID; use variables instead")
    secret_hit = _SECRET_OUTPUT_RE.search(outputs_tf)
    if secret_hit:
        errors.append(
            f"outputs_tf: must not expose secrets (matched '{secret_hit.group(0)}'). "
            "Secrets stay in Key Vault."
        )
    return errors
