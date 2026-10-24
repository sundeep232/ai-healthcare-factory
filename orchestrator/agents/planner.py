"""M2 Plan: Requirements -> versioned Blueprint JSON."""

from __future__ import annotations

from orchestrator.agents.claude_client import ClaudeClient, StructuredResult
from orchestrator.prompts import load_prompt
from orchestrator.schemas.blueprint import Blueprint, BlueprintDraft
from orchestrator.schemas.requirements import Requirements
from orchestrator.tools.catalog import CapabilityCatalog


class PlannerAgent:
    """Designs a catalog-constrained Blueprint for validated Requirements."""

    def __init__(self, client: ClaudeClient, catalog: CapabilityCatalog | None = None) -> None:
        self._client = client
        self._catalog = catalog or CapabilityCatalog.load()
        self._system = load_prompt("m2_plan", CATALOG=self._catalog.render_for_prompt())

    def plan(
        self, requirements: Requirements, parent: Blueprint | None = None
    ) -> StructuredResult[Blueprint]:
        """Produce a Blueprint.

        Args:
            requirements: Output of M1.
            parent: Prior blueprint when re-planning (M7); the new version is parent+1.

        Raises:
            StructuredOutputError: If no catalog-valid blueprint is produced.
        """
        user_message = (
            "Design the blueprint for these requirements:\n"
            f"<requirements>\n{requirements.model_dump_json(indent=2)}\n</requirements>"
        )

        result = self._client.structured(
            system=self._system,
            user=user_message,
            output_model=BlueprintDraft,
            tool_name="submit_blueprint",
            tool_description="Submit the planned Azure resources and synthetic data plan.",
            # Deterministic rule check; failures are fed back to Claude for a retry.
            validators=[lambda draft: self._catalog.validate_blueprint(draft, requirements)],
        )

        version = parent.version + 1 if parent else 1
        blueprint = Blueprint(
            **result.data.model_dump(),
            requirements=requirements,
            version=version,
            parent_version=parent.version if parent else None,
        )
        return StructuredResult(
            data=blueprint, usage=result.usage, attempts=result.attempts, model=result.model
        )
