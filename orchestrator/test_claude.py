#!/usr/bin/env python3
"""Smoke test: verify the Claude integration works end to end.

Loads CLAUDE_API_KEY from the project-root .env, sends one prompt, and prints
the response, the model that actually served the request, token usage, and an
estimated cost.

Usage (from project root, venv active):
    python orchestrator/test_claude.py
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# --- Configuration ----------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
ENV_PATH: Path = PROJECT_ROOT / ".env"

DEFAULT_MODEL: str = "claude-sonnet-5-5"
# Models don't reliably know their own version, so the prompt doesn't ask.
# The serving model is read from the API response instead (message.model).
PROMPT: str = "Say hello and describe what you can do in exactly 2 sentences"
MAX_TOKENS: int = 200

# Default pricing (USD per million tokens). These are Sonnet-tier rates and are
# an ASSUMPTION for newer models; override in .env if pricing differs:
#   CLAUDE_INPUT_COST_PER_MTOK=3.00
#   CLAUDE_OUTPUT_COST_PER_MTOK=15.00
DEFAULT_INPUT_COST_PER_MTOK: float = 3.00
DEFAULT_OUTPUT_COST_PER_MTOK: float = 15.00

BOX_WIDTH: int = 70
PLACEHOLDER_PREFIX: str = "sk-ant-api03-your-key"


# --- Helpers ----------------------------------------------------------------

def print_box(text: str, width: int = BOX_WIDTH) -> None:
    """Print text wrapped inside a unicode box border."""
    inner = width - 4
    print("┌" + "─" * (width - 2) + "┐")
    for paragraph in text.splitlines() or [""]:
        for line in textwrap.wrap(paragraph, inner) or [""]:
            print(f"│ {line.ljust(inner)} │")
    print("└" + "─" * (width - 2) + "┘")


def get_pricing() -> tuple[float, float]:
    """Return (input, output) USD per million tokens, honoring .env overrides.

    Must be called after load_dotenv() so overrides in .env are visible.
    """
    try:
        return (
            float(os.getenv("CLAUDE_INPUT_COST_PER_MTOK", DEFAULT_INPUT_COST_PER_MTOK)),
            float(os.getenv("CLAUDE_OUTPUT_COST_PER_MTOK", DEFAULT_OUTPUT_COST_PER_MTOK)),
        )
    except ValueError:
        print("⚠️  Invalid pricing override in .env; using default rates.")
        return DEFAULT_INPUT_COST_PER_MTOK, DEFAULT_OUTPUT_COST_PER_MTOK


def calculate_cost(
    input_tokens: int, output_tokens: int, input_rate: float, output_rate: float
) -> float:
    """Return the estimated USD cost for the given token counts and rates."""
    return (
        input_tokens / 1_000_000 * input_rate
        + output_tokens / 1_000_000 * output_rate
    )


def load_api_key() -> str:
    """Load CLAUDE_API_KEY from .env; exit with a helpful message if invalid."""
    if not ENV_PATH.exists():
        print(f"❌ No .env file found at {ENV_PATH}")
        print("   Fix: Copy-Item .env.example .env   (then add your key)")
        sys.exit(1)

    load_dotenv(ENV_PATH)
    api_key = os.getenv("CLAUDE_API_KEY", "").strip()

    if not api_key or api_key.startswith(PLACEHOLDER_PREFIX):
        print("❌ CLAUDE_API_KEY is missing or still the placeholder value.")
        print(f"   Edit {ENV_PATH} and set a real key from console.anthropic.com")
        sys.exit(1)

    print("🔑 API key loaded")
    return api_key


# --- Main -------------------------------------------------------------------

def main() -> int:
    """Run the smoke test. Returns a process exit code."""
    # Ensure emoji / box characters render on Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    api_key = load_api_key()
    model = os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
    input_rate, output_rate = get_pricing()
    client = anthropic.Anthropic(api_key=api_key)

    print(f"📡 Calling Claude ({model})...")
    try:
        message = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": PROMPT}],
        )
    except anthropic.AuthenticationError:
        print("❌ Authentication failed — check CLAUDE_API_KEY.")
        return 1
    except anthropic.NotFoundError as exc:
        print(f"❌ Model '{model}' not found or not available to this key: {exc.message}")
        print("   Fix: set CLAUDE_MODEL in .env to a model your account can use.")
        return 1
    except anthropic.RateLimitError:
        print("⏳ Rate limited — wait a moment and retry.")
        return 1
    except anthropic.APIConnectionError as exc:
        print(f"🌐 Could not reach the Anthropic API: {exc}")
        return 1
    except anthropic.APIStatusError as exc:
        print(f"❌ API error {exc.status_code}: {exc.message}")
        return 1

    # Concatenate text blocks from the response
    response_text = "".join(
        block.text for block in message.content if block.type == "text"
    )

    print("\n✅ Response:")
    print_box(response_text)

    # Authoritative source for which model served the request
    print(f"\n🤖 Served by model: {message.model}")

    in_tok = message.usage.input_tokens
    out_tok = message.usage.output_tokens
    cost = calculate_cost(in_tok, out_tok, input_rate, output_rate)

    print("\n📊 Token usage:")
    print(f"   Input tokens : {in_tok:,}")
    print(f"   Output tokens: {out_tok:,}")
    print(f"   Total tokens : {in_tok + out_tok:,}")
    print(
        f"💰 Estimated cost: ${cost:.6f}  "
        f"(${input_rate}/M in + ${output_rate}/M out)"
    )
    print("\n🎉 Claude integration is working!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
