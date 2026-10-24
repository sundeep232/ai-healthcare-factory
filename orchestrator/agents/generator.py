"""M3 Generate: Blueprint -> Terraform instance directory.

Claude composes vetted modules (main.tf + outputs.tf). Static files come from
templates. The result is checked by composition rules and ``terraform validate``;
failures are fed back to Claude for a retry. Nothing is applied here (that is M4).
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from orchestrator.agents.claude_client import ClaudeClient, Usage
from orchestrator.config import INSTANCES_DIR, MODULES_DIR, TEMPLATES_DIR
from orchestrator.prompts import load_prompt
from orchestrator.schemas.blueprint import Blueprint
from orchestrator.tools import terraform_runner
from orchestrator.tools.terraform_files import (
    check_composition,
    instance_id,
    module_interfaces,
    render_static_files,
)

# main.tf for a big blueprint can exceed the default token budget.
GENERATE_MAX_TOKENS = 8000


class TerraformFiles(BaseModel):
    """What Claude must return."""

    main_tf: str = Field(description="Contents of main.tf: one module block per resource.")
    outputs_tf: str = Field(description="Contents of outputs.tf: non-secret root outputs.")


@dataclass
class GeneratedInstance:
    """A generated, validated Terraform instance on disk."""

    instance_id: str
    directory: Path
    files: dict[str, str]
    usage: Usage = field(default_factory=Usage)
    attempts: int = 1
    model: str = ""
    terraform_validated: bool = False


class GeneratorAgent:
    """Generates and validates the Terraform for a Blueprint."""

    def __init__(
        self,
        client: ClaudeClient,
        *,
        validate_with_terraform: bool = True,
        instances_dir: Path = INSTANCES_DIR,
        modules_dir: Path = MODULES_DIR,
        templates_dir: Path = TEMPLATES_DIR,
    ) -> None:
        if validate_with_terraform and terraform_runner.terraform_path() is None:
            raise terraform_runner.TerraformNotFoundError(
                "terraform not found on PATH (needed to validate generated code)."
            )
        self._client = client
        self._validate_tf = validate_with_terraform
        self._instances_dir = instances_dir
        self._modules_dir = modules_dir
        self._templates_dir = templates_dir

    def generate(self, blueprint: Blueprint) -> GeneratedInstance:
        """Generate, validate, and write the Terraform for ``blueprint``.

        Raises:
            StructuredOutputError: If Claude can't produce valid Terraform in time.
            TerraformNotFoundError: If validation is on and terraform is missing.
        """
        static_files = render_static_files(blueprint, self._templates_dir)
        system = self._build_system_prompt(blueprint)
        user = (
            "Write main_tf and outputs_tf for this blueprint:\n"
            f"<blueprint>\n{blueprint.model_dump_json(indent=2, exclude={'requirements'})}\n</blueprint>"
        )

        def rules(candidate: TerraformFiles) -> list[str]:
            return check_composition(blueprint, candidate.main_tf, candidate.outputs_tf)

        def terraform_check(candidate: TerraformFiles) -> list[str]:
            # Skip the slow check when the cheap rules already failed (the retry
            # message would be dominated by those errors anyway).
            if not self._validate_tf or rules(candidate):
                return []
            return self._validate_candidate(static_files, candidate)

        result = self._client.structured(
            system=system,
            user=user,
            output_model=TerraformFiles,
            tool_name="submit_terraform",
            tool_description="Submit main.tf and outputs.tf for the blueprint.",
            validators=[rules, terraform_check],
            max_attempts=3,
            max_tokens=GENERATE_MAX_TOKENS,
        )

        files = {**static_files, "main.tf": result.data.main_tf, "outputs.tf": result.data.outputs_tf}
        directory = self._write_instance(blueprint, files)
        return GeneratedInstance(
            instance_id=instance_id(blueprint),
            directory=directory,
            files=files,
            usage=result.usage,
            attempts=result.attempts,
            model=result.model,
            terraform_validated=self._validate_tf,
        )

    # -- internals ---------------------------------------------------------

    def _build_system_prompt(self, blueprint: Blueprint) -> str:
        examples = self._templates_dir / "examples"
        return load_prompt(
            "m3_generate",
            MODULES=module_interfaces((r.type for r in blueprint.resources), self._modules_dir),
            EXAMPLE_MAIN=(examples / "claims-dashboard.main.tf").read_text(encoding="utf-8").strip(),
            EXAMPLE_OUTPUTS=(examples / "claims-dashboard.outputs.tf")
            .read_text(encoding="utf-8")
            .strip(),
        )

    def _validate_candidate(
        self, static_files: dict[str, str], candidate: TerraformFiles
    ) -> list[str]:
        """Run `terraform validate` on a throwaway workspace next to the real instances.

        It must sit at the same depth as a real instance so that the relative
        module paths (../../modules/...) resolve.
        """
        workspace = self._instances_dir / f"_validate-{uuid.uuid4().hex[:8]}"
        try:
            self._write_files(
                workspace,
                {**static_files, "main.tf": candidate.main_tf, "outputs.tf": candidate.outputs_tf},
            )
            return terraform_runner.validate_workspace(workspace)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _write_instance(self, blueprint: Blueprint, files: dict[str, str]) -> Path:
        directory = self._instances_dir / instance_id(blueprint)
        self._write_files(directory, files)
        if self._validate_tf:
            terraform_runner.fmt(directory)  # canonical formatting for readable diffs
        # Keep the blueprint beside its code so the instance is self-describing.
        (directory / "blueprint.json").write_text(
            json.dumps(json.loads(blueprint.model_dump_json()), indent=2) + "\n", encoding="utf-8"
        )
        return directory

    @staticmethod
    def _write_files(directory: Path, files: dict[str, str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (directory / name).write_text(content.rstrip() + "\n", encoding="utf-8")
