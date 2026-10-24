"""API tests: real FastAPI app + real Pipeline/store, stubbed agents."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from orchestrator.agents.claude_client import StructuredOutputError
from orchestrator.agents.composer import ComposeConfigError, ComposeError
from orchestrator.app import create_app
from orchestrator.pipeline import Pipeline
from orchestrator.schemas import PlanSummary
from orchestrator.storage import FileDemoStore
from orchestrator.tests.test_terraform_files import load_blueprint

INTENT = "Demo of a claims dashboard for payer executives"


class StubComposer:
    def __init__(self) -> None:
        self.deploys = 0
        self.deploy_error: Exception | None = None
        self.plan_error: Exception | None = None

    def plan(self, instance_dir: str) -> PlanSummary:
        if self.plan_error:
            raise self.plan_error
        return PlanSummary(add=7, resources=["module.rg.x"])

    def deploy(self, instance_dir: str) -> tuple[PlanSummary, dict[str, Any]]:
        self.deploys += 1
        if self.deploy_error:
            raise self.deploy_error
        return PlanSummary(add=7), {"web_url": "https://web.example.test"}

    def destroy(self, instance_dir: str) -> None:
        return None

    def read_log(self, instance_dir: str, tail: int = 200) -> str:
        return f"log for {instance_dir}"


@pytest.fixture
def composer() -> StubComposer:
    return StubComposer()


@pytest.fixture
def client(tmp_path: Path, composer: StubComposer) -> TestClient:
    blueprint = load_blueprint()
    pipeline = Pipeline(
        FileDemoStore(tmp_path / "demos"),
        interpreter=SimpleNamespace(interpret=lambda intent: SimpleNamespace(data=blueprint.requirements)),
        planner=SimpleNamespace(plan=lambda req: SimpleNamespace(data=blueprint)),
        generator=SimpleNamespace(
            generate=lambda bp: SimpleNamespace(directory=Path("inst-abc"), attempts=1)
        ),
        composer=composer,
    )
    return TestClient(create_app(pipeline))


def new_demo(client: TestClient) -> str:
    resp = client.post("/api/demos", json={"intent": INTENT})
    assert resp.status_code == 201, resp.text
    return resp.json()["demo_id"]


def generated_demo(client: TestClient) -> str:
    demo_id = new_demo(client)
    assert client.post(f"/api/demos/{demo_id}/generate").status_code == 200
    return demo_id


def status(client: TestClient, demo_id: str) -> str:
    return client.get(f"/api/demos/{demo_id}").json()["status"]


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_list(client: TestClient) -> None:
    demo_id = new_demo(client)
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "planned"
    assert body["blueprint"]["instance_slug"] == "claims-dash"
    listing = client.get("/api/demos").json()
    assert listing[0]["demo_id"] == demo_id and listing[0]["resource_count"] == 6


def test_create_validates_intent(client: TestClient) -> None:
    assert client.post("/api/demos", json={"intent": "short"}).status_code == 422


def test_unknown_demo_is_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/demos/{missing}").status_code == 404
    assert client.get("/api/demos/not-a-uuid").status_code == 404
    assert client.get(f"/api/demos/{missing}/logs").status_code == 404


def test_cannot_deploy_before_generate(client: TestClient, composer: StubComposer) -> None:
    demo_id = new_demo(client)
    resp = client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    assert resp.status_code == 409
    assert composer.deploys == 0


def test_generate_then_plan_stores_summary(client: TestClient) -> None:
    demo_id = generated_demo(client)
    assert client.get(f"/api/demos/{demo_id}").json()["instance_dir"] == "inst-abc"
    plan = client.post(f"/api/demos/{demo_id}/plan").json()["plan"]
    assert plan["add"] == 7
    assert client.get(f"/api/demos/{demo_id}/plan").json()["add"] == 7


@pytest.mark.parametrize("body", [{}, {"confirm": False}])
def test_deploy_requires_explicit_confirmation(
    client: TestClient, composer: StubComposer, body: dict[str, Any]
) -> None:
    demo_id = generated_demo(client)
    assert client.post(f"/api/demos/{demo_id}/deploy", json=body).status_code == 400
    assert composer.deploys == 0
    assert status(client, demo_id) == "generated"


def test_deploy_success(client: TestClient) -> None:
    demo_id = generated_demo(client)
    resp = client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    assert resp.status_code == 202
    assert resp.json()["status"] == "deploying"  # response is taken before the worker finishes

    body = client.get(f"/api/demos/{demo_id}").json()  # TestClient ran the background task
    assert body["status"] == "deployed"
    assert body["outputs"] == {"web_url": "https://web.example.test"}
    assert [e["stage"] for e in body["events"]] == ["plan", "generate", "deploy", "deploy"]


def test_deployed_demo_cannot_be_deployed_again(client: TestClient, composer: StubComposer) -> None:
    demo_id = generated_demo(client)
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    assert client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True}).status_code == 409
    assert composer.deploys == 1


def test_deploy_failure_is_recorded_and_retryable(client: TestClient, composer: StubComposer) -> None:
    composer.deploy_error = ComposeError("apply", "terraform apply failed:\nQuotaExceeded")
    demo_id = generated_demo(client)
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})

    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "failed"
    assert body["failed_stage"] == "apply" and "QuotaExceeded" in body["error"]

    composer.deploy_error = None  # operator fixed quota; retry works
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    assert status(client, demo_id) == "deployed"


def test_unexpected_worker_crash_still_marks_failed(client: TestClient, composer: StubComposer) -> None:
    composer.deploy_error = RuntimeError("disk exploded")
    demo_id = generated_demo(client)
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "failed" and "disk exploded" in body["error"]


def test_destroy_flow(client: TestClient) -> None:
    demo_id = generated_demo(client)
    assert client.post(f"/api/demos/{demo_id}/destroy", json={"confirm": True}).status_code == 409
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})

    assert client.post(f"/api/demos/{demo_id}/destroy", json={}).status_code == 400
    assert client.post(f"/api/demos/{demo_id}/destroy", json={"confirm": True}).status_code == 202
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "destroyed" and body["outputs"] == {}


def test_cannot_regenerate_a_deployed_demo(client: TestClient) -> None:
    demo_id = generated_demo(client)
    client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True})
    assert client.post(f"/api/demos/{demo_id}/generate").status_code == 409


def test_plan_errors_map_to_http_codes(client: TestClient, composer: StubComposer) -> None:
    demo_id = generated_demo(client)
    composer.plan_error = ComposeConfigError("prepare", "missing settings: AZURE_SUBSCRIPTION_ID")
    resp = client.post(f"/api/demos/{demo_id}/plan")
    assert resp.status_code == 503 and "AZURE_SUBSCRIPTION_ID" in resp.json()["detail"]

    composer.plan_error = ComposeError("plan", "Error: bad config")
    resp = client.post(f"/api/demos/{demo_id}/plan")
    assert resp.status_code == 502 and resp.json()["detail"]["stage"] == "plan"


def test_logs(client: TestClient) -> None:
    demo_id = new_demo(client)
    assert client.get(f"/api/demos/{demo_id}/logs").json() == {"log": ""}  # nothing generated yet
    client.post(f"/api/demos/{demo_id}/generate")
    assert client.get(f"/api/demos/{demo_id}/logs?tail=5").json() == {"log": "log for inst-abc"}
    assert client.get(f"/api/demos/{demo_id}/logs?tail=0").status_code == 422


def test_llm_failure_during_create_is_422(tmp_path: Path) -> None:
    def boom(intent: str) -> Any:
        raise StructuredOutputError("No valid output after 2 attempts", errors=["domains: required"])

    pipeline = Pipeline(
        FileDemoStore(tmp_path),
        interpreter=SimpleNamespace(interpret=boom),
        planner=None, generator=None, composer=None,
    )  # fmt: skip
    resp = TestClient(create_app(pipeline)).post("/api/demos", json={"intent": INTENT})
    assert resp.status_code == 422
    assert resp.json()["detail"]["details"] == ["domains: required"]
