"""Helpers for reading a deployment's Terraform outputs."""

from __future__ import annotations

from typing import Any


def public_endpoints(outputs: dict[str, Any]) -> dict[str, str]:
    """Outputs named ``*_url`` that hold an http(s) URL: the demo's intended public entry points."""
    return {
        k: v
        for k, v in sorted(outputs.items())
        if k.endswith("_url") and isinstance(v, str) and v.startswith(("http://", "https://"))
    }
