"""FastAPI application factory.

Run locally (project root, venv active):
    uvicorn orchestrator.app:create_app --factory --host 127.0.0.1 --port 8000

Bind to 127.0.0.1 only: there is no authentication yet, and /deploy spends money.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from fastapi import FastAPI

from orchestrator.agents import ClaudeClient, GeneratorAgent, InterpreterAgent, PlannerAgent
from orchestrator.agents.composer import ComposerAgent
from orchestrator.agents.seeder import SeederAgent
from orchestrator.config import Settings, get_settings
from orchestrator.pipeline import Pipeline
from orchestrator.routes import demos
from orchestrator.storage import DemoStore, FileDemoStore
from orchestrator.tools.azure_access import AzureAccess


def build_pipeline(settings: Settings, store: DemoStore | None = None) -> Pipeline:
    """Wire the real agents. Raises if the API key or terraform binary is missing."""
    client = ClaudeClient(settings)
    return Pipeline(
        store or FileDemoStore(settings.data_dir / "demos"),
        interpreter=InterpreterAgent(client, default_region=settings.demo_location),
        planner=PlannerAgent(client),
        generator=GeneratorAgent(client),
        composer=ComposerAgent(settings),
        seeder=SeederAgent(
            AzureAccess(settings.azure_subscription_id, client_ip=settings.loader_client_ip)
        ),
    )


def create_app(pipeline: Pipeline | Callable[[], Pipeline] | None = None) -> FastAPI:
    """Create the app. Pass a ``pipeline`` (or factory) in tests to avoid real agents."""
    app = FastAPI(
        title="AI-Driven Healthcare Platform Factory",
        version="0.6.0",
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
    app.include_router(demos.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
