"""Storage for published manifests (the data behind share links).

Files are named by the SHA-256 of the share token, so listing the folder never reveals a
working link. Only the holder of the token can derive the file name.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from orchestrator.schemas.certification import Manifest

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


class PublicationStore(Protocol):
    def put(self, token: str, manifest: Manifest) -> None: ...
    def get(self, token: str) -> Manifest | None: ...
    def delete(self, token: str) -> None: ...


class FilePublicationStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, token: str) -> Path | None:
        if not TOKEN_RE.match(token):  # rejects traversal and junk before hashing
            return None
        return self._root / f"{hashlib.sha256(token.encode()).hexdigest()}.json"

    def put(self, token: str, manifest: Manifest) -> None:
        path = self._path(token)
        if path is None:
            raise ValueError("invalid share token")
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(manifest.model_dump_json(indent=2))
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    def get(self, token: str) -> Manifest | None:
        path = self._path(token)
        if path is None:
            return None
        with self._lock:
            if not path.is_file():
                return None
            return Manifest.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, token: str) -> None:
        path = self._path(token)
        if path is not None:
            with self._lock:
                path.unlink(missing_ok=True)
