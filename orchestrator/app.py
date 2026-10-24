"""FastAPI application factory.

Run locally (project root, venv active):
    uvicorn orchestrator.app:create_app --factory --host 127.0.0.1 --port 8000

Bind to 127.0.0.1 only: there is no authentication yet, and /deploy spends money.

To show a published demo to other people, run a second, read-only instance that is safe
to expose (it only serves share links and the UI, from the same data directory):
    SHARE_ONLY=true uvicorn orchestrator.app:create_app --factory --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from orchestrator.agents import ClaudeClient, GeneratorAgent, InterpreterAgent, PlannerAgent
from orchestrator.agents.certifier import CertifierAgent
from orchestrator.agents.composer import ComposerAgent
from orchestrator.agents.publisher import Publisher
from orchestrator.agents.seeder import SeederAgent
from orchestrator.config import PROJECT_ROOT, Settings, get_settings
from orchestrator.pipeline import Pipeline
from orchestrator.routes import demos
from orchestrator.schemas.certification import Manifest
from orchestrator.storage import DemoStore, FileDemoStore
from orchestrator.storage.publication_store import FilePublicationStore
from orchestrator.tools.azure_access import AzureAccess


UI_DIST: Path = PROJECT_ROOT / "ui" / "dist"


def build_publisher(settings: Settings) -> Publisher:
    return Publisher(
        FilePublicationStore(settings.data_dir / "published"),
        public_base_url=settings.public_base_url,
    )


def build_pipeline(settings: Settings, store: DemoStore | None = None) -> Pipeline:
    """Wire the real agents. Raises if the API key or terraform binary is missing."""
    client = ClaudeClient(settings)
    azure = AzureAccess(settings.azure_subscription_id, client_ip=settings.loader_client_ip)
    return Pipeline(
        store or FileDemoStore(settings.data_dir / "demos"),
        interpreter=InterpreterAgent(client, default_region=settings.demo_location),
        planner=PlannerAgent(client),
        generator=GeneratorAgent(client),
        composer=ComposerAgent(settings),
        seeder=SeederAgent(azure),
        certifier=CertifierAgent(azure),
        publisher=build_publisher(settings),
    )


def create_app(
    pipeline: Pipeline | Callable[[], Pipeline] | None = None,
    *,
    share_only: bool | None = None,
    ui_dist: Path | None = None,
) -> FastAPI:
    """Create the app. Pass a ``pipeline`` (or factory) in tests to avoid real agents.

    ``share_only`` (default: the SHARE_ONLY setting) serves nothing but share links and the UI.
    """
    if share_only is None:
        share_only = pipeline is None and get_settings().share_only
    app = FastAPI(
        title="AI-Driven Healthcare Platform Factory",
        version="0.7.0",
        description="Creates Azure demo environments for healthcare payer use cases.",
    )
    logging.basicConfig(level=get_settings().log_level if pipeline is None else logging.INFO)

    lock = threading.Lock()
    cached: list[Pipeline] = []

    def factory() -> Pipeline:
        if callable(pipeline) and not isinstance(pipeline, Pipeline):
            return pipeline()
        if isinstance(pipeline, Pipeline):
            return pipeline
        with lock:  # build once, lazily: /health must work without keys or terraform
            if not cached:
                cached.append(build_pipeline(get_settings()))
            return cached[0]

    app.state.pipeline_factory = factory
    if share_only:
        publisher = build_publisher(get_settings())
        app.state.share_reader = publisher.read
    else:
        app.include_router(demos.router)
        app.state.share_reader = lambda token: factory().shared_manifest(token)
    app.include_router(demos.shared_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    _mount_ui(app, ui_dist or UI_DIST)
    return app


def _mount_ui(app: FastAPI, dist: Path) -> None:
    """Serve the built React app (if present) with client-side-routing fallback to index.html."""
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str) -> FileResponse:
        if path.startswith("api/") or path in ("api", "docs", "openapi.json", "redoc"):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        if path.startswith("assets/"):
            # A missing asset must 404, not return index.html (which would mask a broken bundle).
            raise HTTPException(404)
        return FileResponse(index)
