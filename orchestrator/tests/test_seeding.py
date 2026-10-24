"""M3b loading: Azure access, sinks, seeder, pipeline and API. All offline (fakes only)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from orchestrator.agents.data_agents import GenerationContext, build_context, generate_dataset, tables_for
from orchestrator.agents.data_agents.schema import TABLES
from orchestrator.agents.seeder import SeedError, SeederAgent
from orchestrator.app import create_app
from orchestrator.pipeline import Pipeline, default_seed
from orchestrator.schemas.demo import SeedSummary, SeedTarget
from orchestrator.schemas.requirements import HealthcareDomain as D
from orchestrator.storage import FileDemoStore
from orchestrator.tests.test_api import INTENT, StubComposer
from orchestrator.tests.test_terraform_files import load_blueprint
from orchestrator.tools.azure_access import PG_ADMIN_SECRET, AzureAccess, AzureAccessError
from orchestrator.tools.data_sinks import (
    CosmosSink,
    PostgresSink,
    SinkError,
    build_schema_statements,
    connect_postgres,
    order_by_dependency,
    to_document,
)

TODAY = date(2026, 10, 24)
PASSWORD = "S3cr3t-Pa55word!"


def render(stmts: list[Any]) -> list[str]:
    return [s.as_string(None) for s in stmts]


# =============================================================================
# Azure access
# =============================================================================


class FakeCredential:
    def get_token(self, *scopes: str) -> SimpleNamespace:
        return SimpleNamespace(token="tkn-123")


def access(handler: Any, **kw: Any) -> AzureAccess:
    return AzureAccess(
        "sub-1",
        credential=FakeCredential(),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
        **kw,
    )


def test_public_ip_override_wins_and_is_validated() -> None:
    assert access(lambda r: httpx.Response(500), client_ip=" 203.0.113.7 ").public_ip() == "203.0.113.7"
    with pytest.raises(AzureAccessError, match="IPv4"):
        access(lambda r: httpx.Response(500), client_ip="2001:db8::1").public_ip()


def test_public_ip_lookup_falls_back_to_second_service() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "ipify" in str(req.url):
            return httpx.Response(503)
        return httpx.Response(200, text="198.51.100.9\n")

    assert access(handler).public_ip() == "198.51.100.9"


def test_public_ip_rejects_ipv6_and_garbage_from_lookup() -> None:
    with pytest.raises(AzureAccessError, match="LOADER_CLIENT_IP"):
        access(lambda r: httpx.Response(200, text="2001:db8::1")).public_ip()


def firewall_handler(log: list[str], *, delete_status: int = 202) -> Any:
    def handler(req: httpx.Request) -> httpx.Response:
        log.append(f"{req.method} {req.url.path.split('/')[-1] or req.url.path}")
        assert req.headers["Authorization"] == "Bearer tkn-123"
        if req.method == "PUT":
            body = json.loads(req.content)
            assert body == {"properties": {"startIpAddress": "203.0.113.7", "endIpAddress": "203.0.113.7"}}
            assert "firewallRules/factory-loader-203-0-113-7" in req.url.path
            return httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/op/1"})
        if req.method == "DELETE":
            return httpx.Response(delete_status, headers={"Azure-AsyncOperation": "https://management.azure.com/op/2"})
        return httpx.Response(200, json={"status": "Succeeded"})  # operation poll

    return handler


def test_firewall_rule_opens_waits_and_closes() -> None:
    log: list[str] = []
    az = access(firewall_handler(log))
    with az.postgres_firewall_rule("rg-x", "psql-x", "203.0.113.7") as rule:
        assert rule == "factory-loader-203-0-113-7"
        assert log == ["PUT factory-loader-203-0-113-7", "GET 1"]
    assert log[-2:] == ["DELETE factory-loader-203-0-113-7", "GET 2"]
    assert az.warnings == []


def test_firewall_rule_is_removed_even_if_the_load_fails() -> None:
    log: list[str] = []
    az = access(firewall_handler(log))
    with pytest.raises(RuntimeError, match="boom"):
        with az.postgres_firewall_rule("rg-x", "psql-x", "203.0.113.7"):
            raise RuntimeError("boom")
    assert any(entry.startswith("DELETE") for entry in log)


def test_failed_cleanup_is_reported_not_raised() -> None:
    log: list[str] = []
    az = access(firewall_handler(log, delete_status=403))
    with az.postgres_firewall_rule("rg-x", "psql-x", "203.0.113.7"):
        pass
    assert len(az.warnings) == 1 and "delete it manually" in az.warnings[0]
    assert "factory-loader-203-0-113-7" in az.warnings[0]


def test_firewall_open_failure_is_an_error_with_azure_message() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "AuthorizationFailed", "message": "nope"}})

    with pytest.raises(AzureAccessError, match="AuthorizationFailed: nope") as err:
        with access(handler).postgres_firewall_rule("rg", "srv", "203.0.113.7"):
            pass
    assert "tkn-123" not in str(err.value) and "?api-version" not in str(err.value)


def test_long_running_operation_failure_surfaces() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PUT":
            return httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/op"})
        return httpx.Response(200, json={"status": "Failed", "error": {"message": "bad ip"}})

    with pytest.raises(AzureAccessError, match="failed"):
        with access(handler).postgres_firewall_rule("rg", "srv", "203.0.113.7"):
            pass


def test_cosmos_key_and_missing_subscription() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST" and req.url.path.endswith("/databaseAccounts/acct/listKeys")
        return httpx.Response(200, json={"primaryMasterKey": "KEY=="})

    assert access(handler).cosmos_primary_key("rg", "acct") == "KEY=="
    with pytest.raises(AzureAccessError, match="AZURE_SUBSCRIPTION_ID"):
        AzureAccess("", credential=FakeCredential()).cosmos_primary_key("rg", "acct")


def test_get_secret_returns_value_and_wraps_errors() -> None:
    ok = AzureAccess(
        "s", secret_client=lambda vault: SimpleNamespace(get_secret=lambda n: SimpleNamespace(value=f"{vault}/{n}"))
    )
    assert ok.get_secret("kv-1", "pg") == "kv-1/pg"

    def boom(vault: str) -> Any:
        raise PermissionError("forbidden")

    with pytest.raises(AzureAccessError, match="kv-1.*forbidden"):
        AzureAccess("s", secret_client=boom).get_secret("kv-1", "pg")
    empty = AzureAccess("s", secret_client=lambda v: SimpleNamespace(get_secret=lambda n: SimpleNamespace(value="")))
    with pytest.raises(AzureAccessError, match="empty"):
        empty.get_secret("kv-1", "pg")


# =============================================================================
# PostgreSQL sink
# =============================================================================


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self._last = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, stmt: Any) -> None:
        text = stmt.as_string(None)
        self.conn.statements.append(text)
        self._last = text

    @contextmanager
    def copy(self, stmt: Any) -> Iterator[Any]:
        text = stmt.as_string(None)
        table = text.split('"')[1]
        self.conn.statements.append(text)
        if self.conn.fail_copy:
            raise psycopg.errors.UniqueViolation("duplicate key")
        rows = self.conn.copied.setdefault(table, [])
        yield SimpleNamespace(write_row=rows.append)

    def fetchone(self) -> tuple[int]:
        table = self._last.split('"')[1]
        return (self.conn.count_override.get(table, len(self.conn.copied.get(table, []))),)


class FakeConn:
    def __init__(self, *, fail_copy: bool = False, count_override: dict[str, int] | None = None) -> None:
        self.statements: list[str] = []
        self.copied: dict[str, list[list[Any]]] = {}
        self.events: list[str] = []
        self.fail_copy, self.count_override, self.closed = fail_copy, count_override or {}, False

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        self.events.append("commit")

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


def test_dependency_order_puts_parents_first_and_ignores_outside_parents() -> None:
    names = [s.name for s in order_by_dependency(TABLES.values())]
    for spec in TABLES.values():
        for parent in spec.references.values():
            assert names.index(parent) < names.index(spec.name)
    # With the member table elsewhere, care_plan has no parent in this set: still orderable.
    assert [s.name for s in order_by_dependency(tables_for(D.CARE_MANAGEMENT))][0] == "care_plan"


def test_schema_has_foreign_keys_only_to_tables_in_the_same_database() -> None:
    together = " ".join(render(build_schema_statements(list(TABLES.values()))[0]))
    assert 'FOREIGN KEY ("member_id") REFERENCES "member" ("member_id")' in together
    assert 'FOREIGN KEY ("plan_id") REFERENCES "care_plan" ("plan_id")' in together
    alone = " ".join(render(build_schema_statements(tables_for(D.CARE_MANAGEMENT))[0]))
    assert "REFERENCES \"member\"" not in alone and 'REFERENCES "care_plan"' in alone


def test_schema_quotes_identifiers_and_drops_children_first() -> None:
    stmts = render(build_schema_statements(list(TABLES.values()))[0])
    drops = [s for s in stmts if s.startswith("DROP")]
    creates = [s for s in stmts if s.startswith("CREATE TABLE")]
    assert 'CREATE TABLE "authorization_request"' in " ".join(creates)  # a bare AUTHORIZATION is reserved
    assert drops[0].startswith('DROP TABLE IF EXISTS "timeline_event"')
    assert drops[-1].startswith('DROP TABLE IF EXISTS "member"')
    assert all("CASCADE" in d for d in drops)
    assert '"claim_id" TEXT NOT NULL' in " ".join(creates)
    assert '"denial_reason" TEXT,' in " ".join(creates)


def small_dataset() -> Any:
    ctx = GenerationContext(
        seed=1, today=TODAY, history_months=6,
        counts={D.MEMBER: 100, D.PROVIDER: 5, D.CLAIMS: 40, D.AUTHORIZATION: 20, D.CARE_MANAGEMENT: 10},
    )
    return generate_dataset(ctx)


def test_postgres_load_is_one_transaction_that_replaces_data() -> None:
    ds, conn = small_dataset(), FakeConn()
    counts = PostgresSink(conn).load(list(TABLES.values()), ds)
    assert counts == ds.counts()
    assert conn.events == ["begin", "commit"]
    first_copy = next(i for i, s in enumerate(conn.statements) if s.startswith("COPY"))
    assert all(s.startswith(("DROP", "CREATE TABLE")) for s in conn.statements[:first_copy])
    assert conn.statements[-8:][0].startswith("CREATE INDEX") or any(
        s.startswith("CREATE INDEX") for s in conn.statements
    )
    # Indexes are built after the bulk copy, not before.
    last_copy = max(i for i, s in enumerate(conn.statements) if s.startswith("COPY"))
    first_index = min(i for i, s in enumerate(conn.statements) if s.startswith("CREATE INDEX"))
    assert first_index > last_copy
    member_row = conn.copied["member"][0]
    assert member_row[0] == "SYN-M000001" and len(member_row) == len(TABLES["member"].columns)


def test_postgres_load_failure_rolls_back_and_wraps_error() -> None:
    conn = FakeConn(fail_copy=True)
    with pytest.raises(SinkError, match="PostgreSQL load failed.*duplicate key"):
        PostgresSink(conn).load(list(TABLES.values()), small_dataset())
    assert conn.events == ["begin", "rollback"]


def test_postgres_count_mismatch_is_detected() -> None:
    conn = FakeConn(count_override={"claim": 3})
    with pytest.raises(SinkError, match="'claim' has 3 rows, expected 40"):
        PostgresSink(conn).load(list(TABLES.values()), small_dataset())


def test_connect_retries_then_succeeds() -> None:
    attempts: list[dict[str, Any]] = []

    def connect(**kw: Any) -> str:
        attempts.append(kw)
        if len(attempts) < 3:
            raise psycopg.OperationalError("connection timed out")
        return "conn"

    sleeps: list[float] = []
    out = connect_postgres(
        host="h", database="d", user="u", password=PASSWORD, delay=5, sleep=sleeps.append, connect=connect
    )
    assert out == "conn" and len(attempts) == 3 and sleeps == [5, 5]
    assert attempts[0]["sslmode"] == "require" and attempts[0]["autocommit"] is True


def test_connect_gives_up_without_leaking_the_password() -> None:
    def connect(**kw: Any) -> Any:
        raise psycopg.OperationalError(f"auth failed for password {PASSWORD}")

    with pytest.raises(SinkError) as err:
        connect_postgres(
            host="h", database="d", user="u", password=PASSWORD, attempts=2, sleep=lambda _s: None, connect=connect
        )
    assert PASSWORD not in str(err.value) and "***" in str(err.value)


# =============================================================================
# Cosmos sink
# =============================================================================


class FakeContainer:
    def __init__(self, path: str = "/id") -> None:
        self.path, self.items = path, {}

    def read(self) -> dict[str, Any]:
        return {"partitionKey": {"paths": [self.path]}}

    def query_items(self, query: str, enable_cross_partition_query: bool = False) -> list[Any]:
        if "COUNT" in query:
            return [len(self.items)]
        field = self.path.lstrip("/")
        return [{"id": k, "pk": v.get(field)} for k, v in self.items.items()]

    def delete_item(self, item_id: str, partition_key: Any) -> None:
        del self.items[item_id]

    def upsert_item(self, doc: dict[str, Any]) -> None:
        json.dumps(doc)  # must be JSON-serialisable
        self.items[doc["id"]] = doc


class FakeCosmosDb:
    def __init__(self, existing: dict[str, FakeContainer] | None = None) -> None:
        self.containers = existing or {}
        self.created: list[str] = []

    def create_container_if_not_exists(self, id: str, partition_key: Any) -> FakeContainer:
        if id not in self.containers:
            self.containers[id] = FakeContainer(partition_key)
            self.created.append(id)
        return self.containers[id]


def test_to_document_is_json_safe_and_sets_id() -> None:
    row = {"claim_id": "c1", "service_date": date(2026, 1, 2), "paid": __import__("decimal").Decimal("1.50"), "x": None}
    doc = to_document(row, "c1")
    assert doc == {"claim_id": "c1", "service_date": "2026-01-02", "paid": 1.5, "x": None, "id": "c1"}
    json.dumps(doc)


def test_cosmos_load_creates_missing_containers_and_replaces_stale_items() -> None:
    ds = small_dataset()
    stale = FakeContainer()
    stale.items["old-doc"] = {"id": "old-doc"}
    db = FakeCosmosDb({"care_plans": stale})  # exists already (as Terraform would create it)
    counts = CosmosSink(db, lambda path: path).load(tables_for(D.CARE_MANAGEMENT), ds)

    assert counts == {n: len(ds.rows(n)) for n in ("care_plan", "care_note", "timeline_event")}
    assert sorted(db.created) == ["care_notes", "timeline_events"]  # only the missing ones
    assert "old-doc" not in db.containers["care_plans"].items
    doc = next(iter(db.containers["care_plans"].items.values()))
    assert doc["id"] == doc["plan_id"] and isinstance(doc["start_date"], str)


def test_cosmos_respects_a_different_partition_key() -> None:
    db = FakeCosmosDb({c: FakeContainer("/member_id") for c in ("care_plans", "care_notes", "timeline_events")})
    CosmosSink(db, lambda p: p).load(tables_for(D.CARE_MANAGEMENT), small_dataset())  # rows carry member_id

    db2 = FakeCosmosDb({"care_plans": FakeContainer("/nope")})
    with pytest.raises(SinkError, match="partitioned on /nope"):
        CosmosSink(db2, lambda p: p).load(tables_for(D.CARE_MANAGEMENT), small_dataset())


def test_cosmos_rejects_tables_without_a_container_and_wraps_sdk_errors() -> None:
    with pytest.raises(SinkError, match="no Cosmos container"):
        CosmosSink(FakeCosmosDb(), lambda p: p).load([TABLES["claim"]], small_dataset())

    class Exploding(FakeCosmosDb):
        def create_container_if_not_exists(self, id: str, partition_key: Any) -> Any:
            raise ConnectionError("dns")

    with pytest.raises(SinkError, match="care_plans.*ConnectionError"):
        CosmosSink(Exploding(), lambda p: p).load(tables_for(D.CARE_MANAGEMENT), small_dataset())


# =============================================================================
# Seeder
# =============================================================================


class FakeAzure:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.warnings: list[str] = []

    def public_ip(self) -> str:
        self.events.append("ip")
        return "203.0.113.7"

    def get_secret(self, vault: str, name: str) -> str:
        self.events.append(f"secret:{vault}/{name}")
        return PASSWORD

    def cosmos_primary_key(self, rg: str, account: str) -> str:
        self.events.append(f"cosmoskey:{rg}/{account}")
        return "COSMOSKEY"

    @contextmanager
    def postgres_firewall_rule(self, rg: str, server: str, ip: str) -> Iterator[str]:
        self.events.append(f"open:{rg}/{server}/{ip}")
        try:
            yield "rule"
        finally:
            self.events.append("close")


def connections(**override: Any) -> dict[str, Any]:
    conns = {
        "resource_group": "rg-prior-auth",
        "key_vault": "kv-prior",
        "postgres": {
            "db": {"server_name": "psql-prior", "host": "psql-prior.postgres.database.azure.com",
                   "database": "appdb", "admin_login": "pgadmin"}
        },
        "cosmos": {
            "docs": {"account_name": "cosmos-prior", "endpoint": "https://cosmos-prior.documents.azure.com:443/",
                     "database": "care_management"}
        },
    }
    conns.update(override)
    return {"factory_connections": conns}


def make_seeder(az: FakeAzure, pg: FakeConn, cosmos: FakeCosmosDb) -> SeederAgent:
    return SeederAgent(
        az,  # type: ignore[arg-type]
        connect_pg=lambda **kw: pg,
        cosmos_database=lambda endpoint, key, db: cosmos,
        partition_key=lambda p: p,
    )


def test_seed_loads_each_domain_where_the_data_plan_says() -> None:
    bp, az, pg, cosmos = load_blueprint("example-prior-auth.json"), FakeAzure(), FakeConn(), FakeCosmosDb()
    summary = make_seeder(az, pg, cosmos).seed(bp, connections(), seed=5, today=TODAY)

    by_id = {t.resource_id: t for t in summary.targets}
    assert set(by_id) == {"db", "docs"}
    assert by_id["db"].kind == "postgres" and by_id["docs"].kind == "cosmos"
    assert by_id["db"].tables == {"member": 2000, "provider": 80, "authorization_request": 3000}
    assert by_id["docs"].tables["care_plan"] == 300
    assert summary.total_rows == sum(sum(t.tables.values()) for t in summary.targets)
    assert summary.seed == 5 and summary.as_of == TODAY
    # Care-management data went to Cosmos, not Postgres.
    assert "care_plan" not in pg.copied and "care_plans" in cosmos.containers


def test_seed_opens_firewall_only_around_the_postgres_load_and_uses_vault_secret() -> None:
    bp, az = load_blueprint("example-prior-auth.json"), FakeAzure()
    make_seeder(az, FakeConn(), FakeCosmosDb()).seed(bp, connections(), seed=5, today=TODAY)
    assert az.events == [
        "ip",
        f"secret:kv-prior/{PG_ADMIN_SECRET}",
        "open:rg-prior-auth/psql-prior/203.0.113.7",
        "close",
        "cosmoskey:rg-prior-auth/cosmos-prior",
    ]


def test_seed_result_never_contains_secrets() -> None:
    bp = load_blueprint("example-prior-auth.json")
    summary = make_seeder(FakeAzure(), FakeConn(), FakeCosmosDb()).seed(bp, connections(), seed=5, today=TODAY)
    blob = summary.model_dump_json()
    assert PASSWORD not in blob and "COSMOSKEY" not in blob


def test_seed_is_reproducible_for_a_seed() -> None:
    bp = load_blueprint("example-prior-auth.json")
    a, b = FakeConn(), FakeConn()
    make_seeder(FakeAzure(), a, FakeCosmosDb()).seed(bp, connections(), seed=11, today=TODAY)
    make_seeder(FakeAzure(), b, FakeCosmosDb()).seed(bp, connections(), seed=11, today=TODAY)
    assert a.copied == b.copied


def test_seed_without_connections_output_explains_how_to_fix() -> None:
    bp = load_blueprint("example-prior-auth.json")
    seeder = make_seeder(FakeAzure(), FakeConn(), FakeCosmosDb())
    with pytest.raises(SeedError, match="redeploy"):
        seeder.seed(bp, {"web_url": "https://x"}, seed=1, today=TODAY)


def test_seed_needs_vault_for_postgres_and_connection_facts_for_every_target() -> None:
    bp = load_blueprint("example-prior-auth.json")
    seeder = make_seeder(FakeAzure(), FakeConn(), FakeCosmosDb())
    with pytest.raises(SeedError, match="Key Vault"):
        seeder.seed(bp, connections(key_vault=None), seed=1, today=TODAY)
    with pytest.raises(SeedError, match="no connection facts for cosmos resource 'docs'"):
        seeder.seed(bp, connections(cosmos={}), seed=1, today=TODAY)


def test_postgres_failure_closes_firewall_and_connection_and_hides_password() -> None:
    bp, az, pg = load_blueprint("example-prior-auth.json"), FakeAzure(), FakeConn(fail_copy=True)
    with pytest.raises(SeedError) as err:
        make_seeder(az, pg, FakeCosmosDb()).seed(bp, connections(), seed=1, today=TODAY)
    assert err.value.stage == "postgres" and PASSWORD not in str(err.value)
    assert az.events[-1] == "close" and pg.closed


def test_cosmos_failure_is_a_seed_error() -> None:
    class Down(FakeCosmosDb):
        def create_container_if_not_exists(self, id: str, partition_key: Any) -> Any:
            raise TimeoutError("cosmos unreachable")

    bp = load_blueprint("example-prior-auth.json")
    with pytest.raises(SeedError, match="cosmos"):
        make_seeder(FakeAzure(), FakeConn(), Down()).seed(bp, connections(), seed=1, today=TODAY)


def test_claims_blueprint_goes_entirely_to_postgres() -> None:
    bp, az = load_blueprint(), FakeAzure()
    conns = connections(
        resource_group="rg-claims", key_vault="kv-claims", cosmos={},
    )
    summary = make_seeder(az, FakeConn(), FakeCosmosDb()).seed(bp, conns, seed=3, today=TODAY)
    assert [t.kind for t in summary.targets] == ["postgres"]
    assert set(summary.targets[0].tables) == {"member", "provider", "claim"}
    assert summary.targets[0].tables["claim"] == 50000


# =============================================================================
# Pipeline + API
# =============================================================================


class StubSeeder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, Any]]] = []
        self.error: Exception | None = None

    def seed(self, blueprint: Any, outputs: dict[str, Any], *, seed: int) -> SeedSummary:
        self.calls.append((seed, outputs))
        if self.error:
            raise self.error
        return SeedSummary(
            seed=seed, as_of=TODAY, total_rows=42,
            targets=[SeedTarget(resource_id="db", kind="postgres", host="h", tables={"member": 42})],
            warnings=["firewall rule 'x' could not be removed"],
        )


@pytest.fixture
def seeder() -> StubSeeder:
    return StubSeeder()


@pytest.fixture
def client(tmp_path: Path, seeder: StubSeeder) -> TestClient:
    blueprint = load_blueprint("example-prior-auth.json")
    pipeline = Pipeline(
        FileDemoStore(tmp_path / "demos"),
        interpreter=SimpleNamespace(interpret=lambda intent: SimpleNamespace(data=blueprint.requirements)),
        planner=SimpleNamespace(plan=lambda req: SimpleNamespace(data=blueprint)),
        generator=SimpleNamespace(generate=lambda bp: SimpleNamespace(directory=Path("inst-abc"), attempts=1)),
        composer=StubComposer(),
        seeder=seeder,
    )
    return TestClient(create_app(pipeline))


def deployed(client: TestClient) -> str:
    demo_id = client.post("/api/demos", json={"intent": INTENT}).json()["demo_id"]
    client.post(f"/api/demos/{demo_id}/generate")
    assert client.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True}).status_code == 202
    assert client.get(f"/api/demos/{demo_id}").json()["status"] == "deployed"
    return demo_id


def test_cannot_seed_before_deploy(client: TestClient, seeder: StubSeeder) -> None:
    demo_id = client.post("/api/demos", json={"intent": INTENT}).json()["demo_id"]
    assert client.post(f"/api/demos/{demo_id}/seed").status_code == 409
    assert seeder.calls == []


def test_seed_success_records_summary_and_returns_to_deployed(client: TestClient, seeder: StubSeeder) -> None:
    demo_id = deployed(client)
    resp = client.post(f"/api/demos/{demo_id}/seed")
    assert resp.status_code == 202 and resp.json()["status"] == "seeding"

    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "deployed" and body["failed_stage"] is None
    assert body["data"]["total_rows"] == 42 and body["data"]["seed"] == default_seed(demo_id)
    assert seeder.calls[0][1] == {"web_url": "https://web.example.test"}  # live outputs are passed in
    messages = [e["message"] for e in body["events"] if e["stage"] == "seed"]
    assert any("loaded 42 rows" in m for m in messages) and any("warning" in m for m in messages)


def test_seed_accepts_an_explicit_seed(client: TestClient, seeder: StubSeeder) -> None:
    demo_id = deployed(client)
    client.post(f"/api/demos/{demo_id}/seed", json={"seed": 1234})
    assert seeder.calls[0][0] == 1234
    assert client.post(f"/api/demos/{demo_id}/seed", json={"seed": -1}).status_code == 422


def test_seed_failure_marks_failed_at_data_stage_and_can_be_retried(
    client: TestClient, seeder: StubSeeder
) -> None:
    demo_id = deployed(client)
    seeder.error = SeedError("postgres", "could not connect")
    client.post(f"/api/demos/{demo_id}/seed")
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "failed" and body["failed_stage"] == "data"
    assert "postgres: could not connect" in body["error"]

    seeder.error = None  # fixed; retry from FAILED
    assert client.post(f"/api/demos/{demo_id}/seed").status_code == 202
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "deployed" and body["error"] is None and body["data"] is not None


def test_unexpected_seed_crash_is_recorded_not_raised(client: TestClient, seeder: StubSeeder) -> None:
    demo_id = deployed(client)
    seeder.error = RuntimeError("kaboom")
    assert client.post(f"/api/demos/{demo_id}/seed").status_code == 202
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "failed" and "kaboom" in body["error"]


def test_seed_is_exclusive_with_other_operations(tmp_path: Path, seeder: StubSeeder) -> None:
    """While SEEDING, a second seed, deploy or destroy is refused (409)."""
    blueprint = load_blueprint("example-prior-auth.json")
    pipeline = Pipeline(
        FileDemoStore(tmp_path / "demos"),
        interpreter=SimpleNamespace(interpret=lambda i: SimpleNamespace(data=blueprint.requirements)),
        planner=SimpleNamespace(plan=lambda r: SimpleNamespace(data=blueprint)),
        generator=SimpleNamespace(generate=lambda bp: SimpleNamespace(directory=Path("inst"), attempts=1)),
        composer=StubComposer(),
        seeder=seeder,
    )
    c = TestClient(create_app(pipeline))
    demo_id = deployed(c)
    pipeline.start_seed(demo_id)  # claimed but its worker has not finished
    assert c.get(f"/api/demos/{demo_id}").json()["status"] == "seeding"
    assert c.post(f"/api/demos/{demo_id}/seed").status_code == 409
    assert c.post(f"/api/demos/{demo_id}/destroy", json={"confirm": True}).status_code == 409
    assert c.post(f"/api/demos/{demo_id}/deploy", json={"confirm": True}).status_code == 409


def test_destroy_clears_the_data_summary(client: TestClient) -> None:
    demo_id = deployed(client)
    client.post(f"/api/demos/{demo_id}/seed")
    assert client.get(f"/api/demos/{demo_id}").json()["data"] is not None
    client.post(f"/api/demos/{demo_id}/destroy", json={"confirm": True})
    body = client.get(f"/api/demos/{demo_id}").json()
    assert body["status"] == "destroyed" and body["data"] is None


def test_preview_needs_no_deployment_and_matches_the_plan(client: TestClient) -> None:
    demo_id = client.post("/api/demos", json={"intent": INTENT}).json()["demo_id"]
    resp = client.post(f"/api/demos/{demo_id}/data/preview?sample=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["member"] == 2000 and body["counts"]["care_plan"] == 300
    assert body["targets"] == {"member": "db", "provider": "db", "authorization": "db", "care_management": "docs"}
    assert len(body["samples"]["member"]) == 3
    assert body["samples"]["member"][0]["member_id"] == "SYN-M000001"
    assert body["seed"] == default_seed(demo_id)

    again = client.post(f"/api/demos/{demo_id}/data/preview?sample=3", json={"seed": body["seed"]}).json()
    assert again["samples"] == body["samples"]  # deterministic
    other = client.post(f"/api/demos/{demo_id}/data/preview?sample=3", json={"seed": 1}).json()
    assert other["samples"]["member"] != body["samples"]["member"]


def test_preview_unknown_demo_is_404(client: TestClient) -> None:
    assert client.post("/api/demos/00000000-0000-0000-0000-000000000000/data/preview").status_code == 404


def test_default_seed_is_stable_per_demo() -> None:
    assert default_seed("12345678-aaaa-bbbb-cccc-000000000000") == 0x12345678
    assert build_context(load_blueprint(), seed=1, today=TODAY).counts[D.CLAIMS] == 50000
