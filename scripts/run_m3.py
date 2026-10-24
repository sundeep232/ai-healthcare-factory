#!/usr/bin/env python3
"""Run M3 (Generate): turn a Blueprint JSON file into a validated Terraform instance.

Usage (project root, venv active):
    python scripts/run_m3.py blueprints/example-prior-auth.json

Writes terraform/instances/<slug>-<id8>-v<version>/. Makes no changes in Azure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from orchestrator.agents import ClaudeClient, GeneratorAgent, StructuredOutputError  # noqa: E402
from orchestrator.config import get_settings  # noqa: E402
from orchestrator.schemas import Blueprint  # noqa: E402
from orchestrator.tools.terraform_runner import TerraformNotFoundError  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run M3 Generate on a blueprint JSON file.")
    parser.add_argument("blueprint", type=Path, help="Path to a Blueprint JSON file.")
    parser.add_argument(
        "--skip-validate", action="store_true", help="Skip `terraform validate` (not recommended)."
    )
    args = parser.parse_args()

    blueprint = Blueprint.model_validate(json.loads(args.blueprint.read_text(encoding="utf-8")))
    print(f"🏗️  M3 Generate: {blueprint.instance_slug} v{blueprint.version} "
          f"({len(blueprint.resources)} resources)")

    try:
        agent = GeneratorAgent(
            ClaudeClient(get_settings()), validate_with_terraform=not args.skip_validate
        )
        result = agent.generate(blueprint)
    except TerraformNotFoundError as exc:
        print(f"❌ {exc}")
        return 1
    except StructuredOutputError as exc:
        print(f"❌ M3 failed: {exc}")
        for err in exc.errors:
            print(f"   - {err}")
        return 1
    except anthropic.APIError as exc:
        print(f"❌ Anthropic API error: {exc}")
        return 1

    status = "terraform validate passed" if result.terraform_validated else "NOT validated"
    print(f"✅ {status} after {result.attempts} attempt(s)")
    print(f"   tokens in/out: {result.usage.input_tokens}/{result.usage.output_tokens}")
    print(f"   📁 {result.directory}")
    for name in sorted(result.files):
        print(f"      - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
