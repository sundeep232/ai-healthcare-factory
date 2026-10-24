"""M1 Interpret: natural-language intent -> Requirements JSON."""

from __future__ import annotations

from orchestrator.agents.claude_client import ClaudeClient, StructuredResult
from orchestrator.prompts import load_prompt
from orchestrator.schemas.requirements import Requirements

MAX_INTENT_CHARS = 4000


class InterpreterAgent:
    """Turns a business user's description into validated Requirements."""

    def __init__(self, client: ClaudeClient) -> None:
        self._client = client
        self._system = load_prompt("m1_interpret")

    def interpret(self, intent: str) -> StructuredResult[Requirements]:
        """Interpret ``intent`` into Requirements.

        Raises:
            ValueError: If the intent is empty or too long.
            StructuredOutputError: If Claude can't produce valid Requirements.
        """
        intent = intent.strip()
        if not intent:
            raise ValueError("Intent must not be empty")
        if len(intent) > MAX_INTENT_CHARS:
            raise ValueError(f"Intent too long ({len(intent)} > {MAX_INTENT_CHARS} chars)")

        # Delimit untrusted text so the prompt can instruct Claude to treat it as data.
        user_message = f"<intent>\n{intent}\n</intent>"

        return self._client.structured(
            system=self._system,
            user=user_message,
            output_model=Requirements,
            tool_name="submit_requirements",
            tool_description="Submit the structured requirements for the requested demo.",
        )
