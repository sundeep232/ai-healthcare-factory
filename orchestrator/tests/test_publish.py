"""M6 publishing, the certify/publish pipeline stages, and the public share endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from orchestrator.agents.certifier import CertifierAgent
from orchestrator.agents.publisher import Publisher, build_manifest
from orchestrator.app import create_app
from orchestrator.pipeline import Pipeline
from orchestrator.schemas import PlanSummary
from orchestrator.schemas.certification import Certification, CheckCategory, CheckResult, CheckStatus
from orchestrator.schemas.demo import DemoStatus
from orchestrator.storage import FileDemoStore, InvalidTransitionError
from orchestrator.storage.publication_store import FilePublicationStore
from orchestrator.tests.cert_helpers import (
    COSMOS_ENDPOINT,
    PASSWORD,
    PG_HOST,
    RESOURCE_GROUP,
    FakeAzure,
    ScriptedPg,
    deployed_demo,
    passing_certification,
    cosmos_for,
)
from orchestrator.tests.test_terraform_files import load_blueprint

# =============================================================================
# Manifest + store
# =============================================================================


def test_manifest_is_built_from_an_allow_list_and_contains_no_secrets_or_hosts() -> None:
    demo = deployed_demo(certified=True)
    demo.outputs["db_password"] = "hunter2"  # would be a certification failure, but must never be copied
    blob = build_manifest(demo).model_dump_json()
    for forbidden in (PASSWORD, PG_HOST, COSMOS_ENDPOINT, RESOURCE_GROUP, "hunter2", "psql-prior",
                      "owner only", "pgadmin", "factory_connections", "kv-prior"):
        assert forbidden not in blob, forbidden


def test_manifest_describes_the_demo() -> None:
    demo = deployed_demo(certified=True)
    manifest = build_manifest(demo)
    assert manifest.demo_name == demo.requirements.demo_name  # type: ignore[union-attr]
    assert [e.url for e in manifest.endpoints] == ["https://web.example.test"]
    assert {t.name for t in manifest.tables} >= {"member", "provider", "authorization_request", "care_plan"}
    assert [t.name for t in manifest.tables][:2] == ["member", "provider"]  # schema order, not alphabetical
    assert manifest.certification.passed and manifest.data_seed == demo.data.seed  # type: ignore[union-attr]
    assert "synthetic" in manifest.synthetic_data_notice


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: setattr(d, "status", DemoStatus.GENERATED), "only a deployed demo"),
        (lambda d: setattr(d, "certification", None), "not certified"),
        (lambda d: setattr(d, "data", None), "data changed"),
        (lambda d: setattr(d.data, "seed", 999), "data changed"),
        (lambda d: setattr(d, "certification", Certification(checks=[CheckResult(
            id="x", category=CheckCategory.DATA, title="t", status=CheckStatus.FAIL)], blueprint_version=1,
            data_seed=3)), "did not pass"),
    ],
)
def test_only_a_certified_deployed_demo_with_unchanged_data_can_be_published(mutate: Any, message: str) -> None:
    demo = deployed_demo(certified=True)
    mutate(demo)
    with pytest.raises(InvalidTransitionError, match=message):
        build_manifest(demo)


def test_store_names_files_by_token_hash_and_rejects_bad_tokens(tmp_path: Path) -> None:
    store = FilePublicationStore(tmp_path)
    manifest = build_manifest(deployed_demo(certified=True))
    token = "A" * 32
    store.put(token, manifest)
    names = [p.name for p in tmp_path.iterdir()]
    assert len(names) == 1 and token not in names[0] and names[0].endswith(".json")
    assert store.get(token) == manifest
    for bad in ("../etc/passwd", "short", "a/b" * 10, "", "x" * 100):
        assert store.get(bad) is None
        store.delete(bad)  # no error
        with pytest.raises(ValueError):
            store.put(bad, manifest)
    store.delete(token)
    assert store.get(token) is None


def test_publish_refresh_keeps_the_same_link_and_new_publish_makes_a_new_one(tmp_path: Path) -> None:
    publisher = Publisher(FilePublicationStore(tmp_path), public_base_url="https://demos.example.com/")
    demo = deployed_demo(certified=True)
    first, _ = publisher.publish(demo)
    assert first.share_url == f"https://demos.example.com/share/{first.token}"
    assert len(first.token) >= 30
    demo.publication = first
    again, _ = publisher.publish(demo)
    assert again.token == first.token
    other, _ = publisher.publish(deployed_demo(certified=True))
    assert other.token != first.token
    assert Publisher(FilePublicationStore(tmp_path)).publish(deployed_demo(certified=True))[0].share_url.startswith("/share/")


# =============================================================================
# Pipeline
# =============================================================================


class StubCertifier:
    def __init__(self, bp: Any) -> None:
        self.bp, self.fail, self.crash, self.calls = bp, False, None, 0

    def certify(self, blueprint: Any, outputs: dict[str, Any], data: Any) -> Certification:
        self.calls += 1
        if self.crash:
            raise self.crash
        cert = passing_certification(self.bp, seed=data.seed if data else 0)
        if self.fail:
            cert.checks.append(CheckResult(id="bad", category=CheckCategory.DATA, title="bad",
                                           status=CheckStatus.FAIL, summary="no"))
        return cert


class StubComposer:
    def deploy(self, d: str) -> tuple[PlanSummary, dict[str, Any]]:
        return PlanSummary(add=1), {"web_url": "https://web.example.test"}

    def destroy(self, d: str) -> None:
        return None

    def plan(self, d: str) -> PlanSummary:
        return PlanSummary()

    def read_log(self, d: str, tail: int = 200) -> str:
        return ""


class StubSeeder:
    def seed(self, bp: Any, outputs: Any, *, seed: int) -> Any:
        from orchestrator.tests.cert_helpers import dataset_for, summary_for

        return summary_for(bp, dataset_for(bp), seed=seed)


@pytest.fixture
def world(tmp_path: Path) -> SimpleNamespace:
    bp = load_blueprint("example-prior-auth.json")
    certifier = StubCertifier(bp)
    publisher = Publisher(FilePublicationStore(tmp_path / "pub"), public_base_url="https://demos.example.com")
    pipeline = Pipeline(
        FileDemoStore(tmp_path / "demos"),
        interpreter=SimpleNamespace(interpret=lambda i: SimpleNamespace(data=bp.requirements)),
        planner=SimpleNamespace(plan=lambda r: SimpleNamespace(data=bp)),
        generator=SimpleNamespace(generate=lambda b: SimpleNamespace(directory=Path("inst-abc"), attempts=1)),
        composer=StubComposer(), seeder=StubSeeder(), certifier=certifier, publisher=publisher,
    )
    demo = pipeline.create("Prior authorization demo for the utilization management team")
    pipeline.generate(demo.demo_id)
    pipeline.start_deploy(demo.demo_id)
    pipeline.run_deploy(demo.demo_id)
    pipeline.start_seed(demo.demo_id)
    pipeline.run_seed(demo.demo_id)
    return SimpleNamespace(pipeline=pipeline, id=demo.demo_id, certifier=certifier, publisher=publisher, bp=bp,
                           tmp=tmp_path, composer=StubComposer())


def certify(w: SimpleNamespace) -> Any:
    w.pipeline.start_certify(w.id)
    w.pipeline.run_certify(w.id)
    return w.pipeline.store.get(w.id)


def test_certify_then_publish_creates_a_working_link(world: SimpleNamespace) -> None:
    demo = certify(world)
    assert demo.status == DemoStatus.DEPLOYED and demo.certification.passed
    demo = world.pipeline.publish(world.id)
    assert demo.publication.share_url == f"https://demos.example.com/share/{demo.publication.token}"
    assert world.pipeline.shared_manifest(demo.publication.token).demo_id == world.id


def test_cannot_publish_without_certification(world: SimpleNamespace) -> None:
    with pytest.raises(InvalidTransitionError, match="not certified"):
        world.pipeline.publish(world.id)


def test_certify_is_a_busy_state_and_cannot_overlap(world: SimpleNamespace) -> None:
    world.pipeline.start_certify(world.id)
    assert world.pipeline.store.get(world.id).status.is_busy
    with pytest.raises(InvalidTransitionError):
        world.pipeline.start_certify(world.id)
    with pytest.raises(InvalidTransitionError):
        world.pipeline.start_seed(world.id)


def test_certify_needs_a_deployed_demo(tmp_path: Path, world: SimpleNamespace) -> None:
    other = world.pipeline.create("Another prior authorization demo for the team")
    with pytest.raises(InvalidTransitionError):
        world.pipeline.start_certify(other.demo_id)


def test_a_crashing_certifier_becomes_a_failed_check_and_the_demo_stays_deployed(world: SimpleNamespace) -> None:
    world.certifier.crash = RuntimeError("kaboom")
    demo = certify(world)
    assert demo.status == DemoStatus.DEPLOYED and demo.error is None
    assert not demo.certification.passed
    assert demo.certification.checks[0].id == "certify.run" and "kaboom" in demo.certification.checks[0].detail
    with pytest.raises(InvalidTransitionError, match="did not pass"):
        world.pipeline.publish(world.id)


def test_failed_recertification_revokes_a_live_link(world: SimpleNamespace) -> None:
    certify(world)
    token = world.pipeline.publish(world.id).publication.token
    world.certifier.fail = True
    demo = certify(world)
    assert demo.publication is None and not demo.certification.passed
    assert world.pipeline.shared_manifest(token) is None
    assert any("revoked" in e.message for e in demo.events)


def test_passing_recertification_keeps_the_link(world: SimpleNamespace) -> None:
    certify(world)
    token = world.pipeline.publish(world.id).publication.token
    assert certify(world).publication.token == token


@pytest.mark.parametrize("action", ["seed", "destroy"])  # a deployed demo cannot be redeployed
def test_changing_the_instance_unpublishes_and_uncertifies(world: SimpleNamespace, action: str) -> None:
    certify(world)
    token = world.pipeline.publish(world.id).publication.token
    getattr(world.pipeline, f"start_{action}")(world.id)
    demo = world.pipeline.store.get(world.id)
    assert demo.publication is None and demo.certification is None
    assert world.pipeline.shared_manifest(token) is None
    events = [e.message for e in demo.events]
    assert any("share link revoked" in m for m in events) and any("certification cleared" in m for m in events)


def test_unpublish_revokes_immediately_and_is_not_repeatable(world: SimpleNamespace) -> None:
    certify(world)
    token = world.pipeline.publish(world.id).publication.token
    assert world.pipeline.unpublish(world.id).publication is None
    assert world.pipeline.shared_manifest(token) is None
    with pytest.raises(InvalidTransitionError, match="not published"):
        world.pipeline.unpublish(world.id)


def test_destroy_completion_leaves_nothing_certified(world: SimpleNamespace) -> None:
    certify(world)
    world.pipeline.start_destroy(world.id)
    world.pipeline.run_destroy(world.id)
    demo = world.pipeline.store.get(world.id)
    assert demo.status == DemoStatus.DESTROYED and demo.certification is None and demo.publication is None


def test_the_real_certifier_runs_through_the_pipeline(world: SimpleNamespace) -> None:
    """End-to-end wiring with the real CertifierAgent against fakes (no Azure)."""
    from orchestrator.tests.cert_helpers import dataset_for

    ds = dataset_for(world.bp)
    pg = ScriptedPg({n: len(ds.rows(n)) for n in ("member", "provider", "authorization_request")})
    # seed counts in the stored demo come from StubSeeder using the same dataset, so they agree
    world.pipeline._certifier = CertifierAgent(
        FakeAzure(), connect_pg=lambda **kw: pg, cosmos_database=lambda e, k, d: cosmos_for(ds),  # type: ignore[arg-type]
        http_status=lambda u: 200,
    )
    # StubComposer outputs lack factory_connections: the certifier must say so, not crash.
    demo = certify(world)
    assert not demo.certification.passed
    assert [c.id for c in demo.certification.checks if c.status == CheckStatus.FAIL] == ["deploy.connections"]


# =============================================================================
# HTTP API
# =============================================================================


@pytest.fixture
def client(world: SimpleNamespace) -> TestClient:
    return TestClient(create_app(world.pipeline))


def test_api_certify_publish_share_and_revoke(client: TestClient, world: SimpleNamespace) -> None:
    demo_url = f"/api/demos/{world.id}"
    assert client.post(f"{demo_url}/publish").status_code == 409
    assert client.get(f"{demo_url}/manifest").status_code == 409

    resp = client.post(f"{demo_url}/certify")  # TestClient runs background tasks before returning
    assert resp.status_code == 202 and resp.json()["status"] == "certifying"
    cert = client.get(f"{demo_url}/certification").json()
    assert cert["passed"] is True and cert["summary"]["pass"] == 1

    assert client.get(f"{demo_url}/manifest").json()["certification"]["passed"] is True
    published = client.post(f"{demo_url}/publish").json()["publication"]
    token = published["token"]

    shared = client.get(f"/api/shared/{token}")
    assert shared.status_code == 200 and shared.json()["demo_id"] == world.id
    assert shared.headers["cache-control"] == "no-store" and "noindex" in shared.headers["x-robots-tag"]
    assert "detail" not in json.dumps(shared.json()["certification"]["checks"])

    assert client.delete(f"{demo_url}/publish").json()["publication"] is None
    assert client.get(f"/api/shared/{token}").status_code == 404
    assert client.delete(f"{demo_url}/publish").status_code == 409


@pytest.mark.parametrize("token", ["nope", "A" * 30, "..%2F..%2Fetc", "x" * 200])
def test_api_unknown_share_tokens_are_404(client: TestClient, token: str) -> None:
    assert client.get(f"/api/shared/{token}").status_code == 404


def test_api_certify_conflicts(client: TestClient, world: SimpleNamespace) -> None:
    assert client.post("/api/demos/00000000-0000-0000-0000-000000000000/certify").status_code == 404
    world.pipeline.start_certify(world.id)
    assert client.post(f"/api/demos/{world.id}/certify").status_code == 409


# =============================================================================
# Share-only mode and UI hosting
# =============================================================================


def test_share_only_server_exposes_only_share_links(tmp_path: Path, world: SimpleNamespace, monkeypatch: Any) -> None:
    from orchestrator import app as app_module
    from orchestrator.config import Settings

    certify(world)
    token = world.pipeline.publish(world.id).publication.token
    settings = Settings(claude_api_key="x", data_dir=tmp_path, _env_file=None)  # type: ignore[call-arg]
    settings = settings.model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    (tmp_path / "published").mkdir(exist_ok=True)
    for f in (world.tmp / "pub").iterdir():
        (tmp_path / "published" / f.name).write_bytes(f.read_bytes())

    public = TestClient(create_app(share_only=True))
    assert public.get(f"/api/shared/{token}").json()["demo_id"] == world.id
    assert public.get("/health").status_code == 200
    for method, path in (("get", "/api/demos"), ("post", "/api/demos"), ("post", f"/api/demos/{world.id}/deploy"),
                         ("post", f"/api/demos/{world.id}/destroy"), ("get", f"/api/demos/{world.id}")):
        assert getattr(public, method)(path).status_code in (404, 405), path


def test_ui_is_served_with_spa_fallback_and_never_shadows_the_api(tmp_path: Path, world: SimpleNamespace) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside")
    client = TestClient(create_app(world.pipeline, ui_dist=dist))

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/share/anything").text == "<html>app</html>"  # client-side route
    assert client.get("/assets/a.js").text == "console.log(1)"
    assert client.get("/assets/missing.js").status_code == 404  # not index.html
    assert client.get("/api/demos").status_code == 200
    assert client.get("/api/nope").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}
    assert "outside" not in client.get("/..%2Fsecret.txt").text
    assert "outside" not in client.get("/%2e%2e/secret.txt").text


def test_no_ui_mounted_when_not_built(world: SimpleNamespace, tmp_path: Path) -> None:
    client = TestClient(create_app(world.pipeline, ui_dist=tmp_path / "missing"))
    assert client.get("/").status_code == 404
