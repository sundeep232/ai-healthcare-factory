#!/usr/bin/env python3
"""Run M1 (Interpret) and M2 (Plan) end to end against the live Claude API.

Usage (project root, venv active):
    python scripts/run_m1_m2.py "Demo of a claims dashboard for payer executives"
    python scripts/run_m1_m2.py --file intent.txt --out blueprints/my-demo.json
    python scripts/run_m1_m2.py "..." --requirements-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/run_m1_m2.py` from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from orchestrator.agents import (  # noqa: E402
    ClaudeClient,
    InterpreterAgent,
    PlannerAgent,
    StructuredOutputError,
)
from orchestrator.config import get_settings  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M1 Interpret + M2 Plan.")
    parser.add_argument("intent", nargs="?", help="Plain-English description of the demo.")
    parser.add_argument("--file", type=Path, help="Read the intent from a text file.")
    parser.add_argument("--out", type=Path, help="Write the final JSON to this path.")
    parser.add_argument(
        "--requirements-only", action="store_true", help="Stop after M1 (cheaper to iterate)."
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    intent = args.file.read_text(encoding="utf-8") if args.file else args.intent
    if not intent:
        print("❌ Provide an intent string or --file.")
        return 2

    settings = get_settings()
    client = ClaudeClient(settings)

    print("🧠 M1 Interpret...")
    try:
        m1 = InterpreterAgent(client, default_region=settings.demo_location).interpret(intent)
    except (StructuredOutputError, ValueError) as exc:
        print(f"❌ M1 failed: {exc}")
        for err in getattr(exc, "errors", []):
            print(f"   - {err}")
        return 1
    except anthropic.APIError as exc:
        print(f"❌ Anthropic API error: {exc}")
        return 1

    req = m1.data
    print(f"✅ {req.demo_name}  (domains: {', '.join(d.value for d in req.domains)})")
    for note in req.assumptions:
        print(f"   • assumed: {note}")
    for question in req.open_questions:
        print(f"   ? open question: {question}")
    print(f"   tokens in/out: {m1.usage.input_tokens}/{m1.usage.output_tokens}, attempts: {m1.attempts}")

    output_json = req.model_dump_json(indent=2)

    if not args.requirements_only:
        print("\n📐 M2 Plan...")
        try:
            m2 = PlannerAgent(client).plan(req)
        except StructuredOutputError as exc:
            print(f"❌ M2 failed: {exc}")
            for err in exc.errors:
                print(f"   - {err}")
            return 1
        except anthropic.APIError as exc:
            print(f"❌ Anthropic API error: {exc}")
            return 1
        bp = m2.data
        print(f"✅ Blueprint v{bp.version} ({bp.instance_slug}): {len(bp.resources)} resources")
        for res in bp.resources:
            print(f"   - {res.id:<8} {res.type:<20} {res.sku or '-'}")
        for entry in bp.data_plan:
            print(f"   data: {entry.domain.value:<16} -> {entry.target_resource_id} ({entry.record_count:,} records)")
        print(f"   tokens in/out: {m2.usage.input_tokens}/{m2.usage.output_tokens}, attempts: {m2.attempts}")
        output_json = bp.model_dump_json(indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output_json + "\n", encoding="utf-8")
        print(f"\n💾 Saved to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
