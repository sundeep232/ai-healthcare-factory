"""Persistence for Demo records.

A JSON-file store keeps local development dependency-free. The interface is
small on purpose so a Cosmos DB implementation (the shared `runs` container) can
replace it later without touching callers.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from orchestrator.schemas.demo import Demo, DemoStatus

_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class DemoNotFoundError(KeyError):
    """No demo with that id."""


class InvalidTransitionError(RuntimeError):
    """The demo is not in a state that allows the requested operation."""


class DemoStore(Protocol):
    def create(self, demo: Demo) -> Demo: ...
    def get(self, demo_id: str) -> Demo: ...
    def list(self) -> list[Demo]: ...
    def save(self, demo: Demo) -> Demo: ...
    def begin(self, demo_id: str, allowed: Iterable[DemoStatus], to: DemoStatus) -> Demo: ...


class FileDemoStore:
    """One JSON file per demo under ``root``; writes are atomic and process-locked."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, demo_id: str) -> Path:
        if not _ID_RE.match(demo_id):  # also blocks path traversal like "../x"
            raise DemoNotFoundError(demo_id)
        return self._root / f"{demo_id}.json"

    def _write(self, demo: Demo) -> None:
        demo.updated_at = datetime.now(timezone.utc)
        path = self._path(demo.demo_id)
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(demo.model_dump_json(indent=2))
            os.replace(tmp, path)  # atomic on Windows and POSIX
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def create(self, demo: Demo) -> Demo:
        with self._lock:
            self._write(demo)
        return demo

    def get(self, demo_id: str) -> Demo:
        path = self._path(demo_id)
        with self._lock:
            if not path.is_file():
                raise DemoNotFoundError(demo_id)
            return Demo.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Demo]:
        with self._lock:
            demos = [Demo.model_validate_json(p.read_text(encoding="utf-8")) for p in self._root.glob("*.json")]
        return sorted(demos, key=lambda d: d.created_at, reverse=True)

    def save(self, demo: Demo) -> Demo:
        with self._lock:
            self._write(demo)
        return demo

    def begin(self, demo_id: str, allowed: Iterable[DemoStatus], to: DemoStatus) -> Demo:
        """Atomically move a demo to ``to`` if it is currently in one of ``allowed``.

        This is the guard against double-clicks: two concurrent deploy requests
        can't both pass, because the second sees `deploying`.
        """
        allowed_set = set(allowed)
        with self._lock:
            demo = self.get(demo_id)
            if demo.status not in allowed_set:
                wanted = ", ".join(sorted(s.value for s in allowed_set))
                raise InvalidTransitionError(
                    f"demo is '{demo.status.value}'; this operation needs one of: {wanted}"
                )
            demo.status = to
            demo.error = None
            demo.failed_stage = None
            self._write(demo)
            return demo


def update(store: DemoStore, demo_id: str, mutate: Callable[[Demo], None]) -> Demo:
    """Read-modify-write helper for background workers."""
    demo = store.get(demo_id)
    mutate(demo)
    return store.save(demo)
