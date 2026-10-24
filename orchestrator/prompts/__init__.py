"""Prompt templates (Markdown files) and a tiny loader."""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR: Path = Path(__file__).resolve().parent


def load_prompt(name: str, **replacements: str) -> str:
    """Read prompts/<name>.md and substitute {{KEY}} placeholders.

    Args:
        name: File stem, e.g. "m1_interpret".
        **replacements: Placeholder values; ``CATALOG="..."`` replaces ``{{CATALOG}}``.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
        ValueError: If a {{PLACEHOLDER}} is left unfilled.
    """
    text = (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    if "{{" in text and "}}" in text:
        raise ValueError(f"Prompt '{name}' has unfilled placeholders")
    return text
