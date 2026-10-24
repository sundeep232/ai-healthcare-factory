"""Demo routes: create/inspect demos and drive the M1..M6 stages."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, TypeVar

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from orchestrator.agents.claude_client import StructuredOutputError
from orchestrator.agents.composer import ComposeConfigError, ComposeError
from orchestrator.pipeline import Pipeline
from orchestrator.schemas.certification import Certification, Manifest
from orchestrator.schemas.demo import Demo, DemoStatus, PlanSummary
from orchestrator.storage import DemoNotFoundError, InvalidTransitionError
from orchestrator.tools.terraform_runner import TerraformNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demos", tags=["demos"])
shared_router = APIRouter(prefix="/api/shared", tags=["shared"])
T = TypeVar("T")


class CreateDemoRequest(BaseModel):
    intent: str = Field(min_length=10, max_length=4000, description="Plain-English description of the demo.")


class ConfirmRequest(BaseModel):
    """Explicit acknowledgement for operations that create or destroy cloud resources."""

    confirm: bool = Field(False, description="Must be true to proceed.")


class DemoSummary(BaseModel):
    demo_id: str
    status: DemoStatus
    demo_name: str | None
    instance_slug: str | None
    resource_count: int
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, demo: Demo) -> DemoSummary:
        return cls(
            demo_id=demo.demo_id,
            status=demo.status,
            demo_name=demo.requirements.demo_name if demo.requirements else None,
            instance_slug=demo.blueprint.instance_slug if demo.blueprint else None,
            resource_count=len(demo.blueprint.resources) if demo.blueprint else 0,
            created_at=demo.created_at.isoformat(),
            updated_at=demo.updated_at.isoformat(),
        )


def get_pipeline(request: Request) -> Pipeline:
    """Resolve the pipeline lazily so the API can start (and serve /health) without keys."""
    factory: Callable[[], Pipeline] = request.app.state.pipeline_factory
    try:
        return factory()
    except TerraformNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]


def _guard(fn: Callable[[], T]) -> T:
    """Run a pipeline call and translate domain errors to HTTP errors."""
    try:
        return fn()
    except DemoNotFoundError as exc:
        raise HTTPException(404, "demo not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ComposeConfigError as exc:
        raise HTTPException(503, exc.detail) from exc
    except ComposeError as exc:
        raise HTTPException(502, {"stage": exc.stage, "error": exc.detail}) from exc
    except StructuredOutputError as exc:
        raise HTTPException(422, {"error": str(exc), "details": exc.errors}) from exc
    except anthropic.APIError as exc:
        logger.warning("Anthropic API error: %s", exc)
        raise HTTPException(502, f"Claude API error: {exc}") from exc


@router.post("", status_code=201, response_model=Demo)
def create_demo(body: CreateDemoRequest, pipeline: PipelineDep) -> Demo:
    """M1 Interpret + M2 Plan: intent -> requirements -> blueprint. Costs a few cents of tokens."""
    return _guard(lambda: pipeline.create(body.intent))


@router.get("", response_model=list[DemoSummary])
def list_demos(pipeline: PipelineDep) -> list[DemoSummary]:
    return [DemoSummary.of(d) for d in pipeline.store.list()]


@router.get("/{demo_id}", response_model=Demo)
def get_demo(demo_id: str, pipeline: PipelineDep) -> Demo:
    return _guard(lambda: pipeline.store.get(demo_id))


@router.post("/{demo_id}/generate", response_model=Demo)
def generate(demo_id: str, pipeline: PipelineDep) -> Demo:
    """M3: write and validate the Terraform for the blueprint. No Azure changes."""
    return _guard(lambda: pipeline.generate(demo_id))


@router.post("/{demo_id}/plan", response_model=Demo)
def plan(demo_id: str, pipeline: PipelineDep) -> Demo:
    """M4 dry run: `terraform plan` against the real subscription. Creates nothing."""
    return _guard(lambda: pipeline.plan(demo_id))


@router.post("/{demo_id}/deploy", status_code=202, response_model=Demo)
def deploy(
    demo_id: str, body: ConfirmRequest, background: BackgroundTasks, pipeline: PipelineDep
) -> Demo:
    """M4: apply the Terraform in the background. Creates billable Azure resources.

    Poll GET /api/demos/{id} for status, GET /api/demos/{id}/logs for progress.
    """
    _require_confirm(body, "deploy (creates billable Azure resources)")
    demo = _guard(lambda: pipeline.start_deploy(demo_id))
    background.add_task(pipeline.run_deploy, demo_id)
    return demo


class DataRequest(BaseModel):
    seed: int | None = Field(
        None, ge=0, le=2**32 - 1, description="Override the per-demo default seed (same seed = same data)."
    )


@router.post("/{demo_id}/data/preview")
def preview_data(
    demo_id: str, pipeline: PipelineDep, body: DataRequest | None = None,
    sample: Annotated[int, Query(ge=1, le=50)] = 5,
) -> dict[str, object]:
    """M3b dry run: generate the dataset in memory and return counts + sample rows.

    Touches no Azure resources, so it works before deploy. The same seed that previews
    here is what /seed loads (unless the calendar day changes the history window).
    """
    try:
        return pipeline.preview_data(demo_id, seed=body.seed if body else None, sample=sample)
    except DemoNotFoundError as exc:
        raise HTTPException(404, "demo not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{demo_id}/seed", status_code=202, response_model=Demo)
def seed(
    demo_id: str, background: BackgroundTasks, pipeline: PipelineDep, body: DataRequest | None = None
) -> Demo:
    """M3b: load synthetic data into the deployed databases, in the background.

    Replaces any data from an earlier seed. Opens a temporary firewall rule for this
    machine's IP on PostgreSQL and removes it afterwards. Poll GET /api/demos/{id}.
    """
    demo = _guard(lambda: pipeline.start_seed(demo_id))
    background.add_task(pipeline.run_seed, demo_id, body.seed if body else None)
    return demo


@router.post("/{demo_id}/certify", status_code=202, response_model=Demo)
def certify(demo_id: str, background: BackgroundTasks, pipeline: PipelineDep) -> Demo:
    """M5: verify the live instance against its blueprint, in the background.

    Opens a temporary firewall rule for this machine on PostgreSQL (removed afterwards, and
    checked). Failed checks are results, not errors: poll GET /api/demos/{id}/certification.
    """
    demo = _guard(lambda: pipeline.start_certify(demo_id))
    background.add_task(pipeline.run_certify, demo_id)
    return demo


@router.get("/{demo_id}/certification", response_model=Certification | None)
def get_certification(demo_id: str, pipeline: PipelineDep) -> Certification | None:
    return _guard(lambda: pipeline.store.get(demo_id)).certification


@router.get("/{demo_id}/manifest", response_model=Manifest)
def preview_manifest(demo_id: str, pipeline: PipelineDep) -> Manifest:
    """Exactly what the public share page would show now. Publishes nothing."""
    return _guard(lambda: pipeline.manifest_preview(demo_id))


@router.post("/{demo_id}/publish", response_model=Demo)
def publish(demo_id: str, pipeline: PipelineDep) -> Demo:
    """M6: create the shareable link (needs a passing certification), or refresh its snapshot.

    Anyone with the link can read the manifest; it contains no credentials or hostnames.
    """
    return _guard(lambda: pipeline.publish(demo_id))


@router.delete("/{demo_id}/publish", response_model=Demo)
def unpublish(demo_id: str, pipeline: PipelineDep) -> Demo:
    """Revoke the share link immediately."""
    return _guard(lambda: pipeline.unpublish(demo_id))


@router.post("/{demo_id}/destroy", status_code=202, response_model=Demo)
def destroy(
    demo_id: str, body: ConfirmRequest, background: BackgroundTasks, pipeline: PipelineDep
) -> Demo:
    """Tear down every Azure resource of this demo, in the background."""
    _require_confirm(body, "destroy (deletes all Azure resources of this demo)")
    demo = _guard(lambda: pipeline.start_destroy(demo_id))
    background.add_task(pipeline.run_destroy, demo_id)
    return demo


@router.get("/{demo_id}/plan", response_model=PlanSummary | None)
def get_plan(demo_id: str, pipeline: PipelineDep) -> PlanSummary | None:
    return _guard(lambda: pipeline.store.get(demo_id)).plan


@router.get("/{demo_id}/logs")
def get_logs(
    demo_id: str, pipeline: PipelineDep, tail: Annotated[int, Query(ge=1, le=2000)] = 200
) -> dict[str, str]:
    try:
        return {"log": pipeline.logs(demo_id, tail)}
    except DemoNotFoundError as exc:
        raise HTTPException(404, "demo not found") from exc


def _require_confirm(body: ConfirmRequest, what: str) -> None:
    if not body.confirm:
        raise HTTPException(400, f'send {{"confirm": true}} to {what}')


@shared_router.get("/{token}", response_model=Manifest)
def shared_manifest(token: str, request: Request, response: Response) -> Manifest:
    """Public, read-only. The unguessable token is the credential; unknown/revoked tokens are 404.

    Deliberately independent of the pipeline, so a share-only deployment needs no API keys.
    """
    read: Callable[[str], Manifest | None] = request.app.state.share_reader
    manifest = read(token)
    if manifest is None:
        raise HTTPException(404, "this share link does not exist or was revoked")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return manifest
