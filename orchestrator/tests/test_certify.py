"""M5 certifier: control flow, failure handling and what may be published (no database needed)."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.agents.certifier import BUSINESS_RULES, SAFETY_RULES, CertifierAgent
from orchestrator.schemas.certification import Certification, CheckResult, CheckStatus
from orchestrator.tests.cert_helpers import (
    COSMOS_ENDPOINT,
    COSMOS_KEY,
    PASSWORD,
    PG_HOST,
    RESOURCE_GROUP,
    CertCosmos,
    FakeAzure,
    ScriptedPg,
    cosmos_for,
    dataset_for,
    outputs,
    summary_for,
)
from orchestrator.tests.test_terraform_files import load_blueprint
from orchestrator.tools.data_sinks import SinkError

PRIOR = "example-prior-auth.json"  # member/provider/authorization in PostgreSQL, care management in Cosmos


class Env:
    """A deployed prior-auth demo plus the fakes the certifier talks to."""

    def __init__(
        self, *, pg_overrides: dict[str, int] | None = None, rules: list[str] | None = None,
        rules_error: Exception | None = None, status: Any = 200, cosmos: CertCosmos | None = None,
        connect_error: Exception | None = None, drift: dict[str, int] | None = None,
    ) -> None:
        self.bp = load_blueprint(PRIOR)
        self.ds = dataset_for(self.bp)
        self.data = summary_for(self.bp, self.ds)
        self.azure = FakeAzure(rules=rules, rules_error=rules_error)
        counts = {n: len(self.ds.rows(n)) for n in ("member", "provider", "authorization_request")}
        counts.update(drift or {})
        self.pg = ScriptedPg(counts, pg_overrides)
        self.cosmos = cosmos or cosmos_for(self.ds)
        self.urls: list[str] = []

        def connect(**kw: Any) -> ScriptedPg:
            if connect_error:
                raise connect_error
            return self.pg

        def http(url: str) -> int:
            self.urls.append(url)
            if isinstance(status, Exception):
                raise status
            return int(status)

        self.agent = CertifierAgent(
            self.azure,  # type: ignore[arg-type]
            connect_pg=connect, cosmos_database=lambda e, k, d: self.cosmos, http_status=http,
        )

    def run(self, out: dict[str, Any] | None = None, data: Any = "default") -> Certification:
        return self.agent.certify(self.bp, out if out is not None else outputs(), self.data if data == "default" else data)


def by_id(cert: Certification) -> dict[str, CheckResult]:
    ids = [c.id for c in cert.checks]
    assert len(ids) == len(set(ids)), "check ids must be unique"
    return {c.id: c for c in cert.checks}


def failed(cert: Certification) -> set[str]:
    return {c.id for c in cert.checks if c.status == CheckStatus.FAIL}


def test_a_healthy_demo_is_certified_with_evidence() -> None:
    env = Env()
    cert = env.run()
    assert cert.passed and not failed(cert), failed(cert)
    checks = by_id(cert)
    for expected in (
        "deploy.connections", "deploy.endpoint.web_url", "security.outputs.no_secrets",
        "security.postgres.tls", "security.firewall.clean", "data.member.rows",
        "data.authorization_request.ref.member_id", "data.care_plan.ref.member_id",
        "data.care_note.ref.plan_id", "data.member.safe.email_reserved_domain",
        "data.provider.safe.npi_unissued_range", "data.care_plan.safe.synthetic_ids",
    ):
        assert checks[expected].status == CheckStatus.PASS, expected
    assert checks["data.member.rows"].evidence == {"rows": 60, "loaded": 60}
    assert cert.data_seed == env.data.seed and cert.blueprint_version == env.bp.version


def test_firewall_rule_is_open_only_while_the_database_is_checked_and_listed_afterwards() -> None:
    env = Env()
    env.run()
    assert env.azure.events == ["open", "close", "list-rules"]  # cleanup is verified *after* closing
    assert env.pg.closed


def test_every_database_check_is_a_read_only_select() -> None:
    env = Env()
    env.run()
    assert env.pg.queries
    assert all(q.lstrip().upper().startswith("SELECT") for q, _ in env.pg.queries)


def test_row_count_drift_fails_the_table_check() -> None:
    cert = Env(drift={"member": 59}).run()
    assert failed(cert) == {"data.member.rows"} and not cert.passed
    assert by_id(cert)["data.member.rows"].evidence == {"rows": 59, "loaded": 60}


def test_an_emptied_table_fails_even_if_the_record_says_empty() -> None:
    env = Env(drift={"member": 0})
    env.data.targets[0].tables["member"] = 0
    assert "data.member.rows" in failed(env.run())


@pytest.mark.parametrize("rule", [*SAFETY_RULES, *BUSINESS_RULES], ids=lambda r: r.id)
def test_each_rule_violation_fails_exactly_its_check(rule: Any) -> None:
    env = Env(pg_overrides={rule.violation: 3})
    cert = env.run()
    applicable = rule.table in {"member", "provider", "authorization_request"}  # claim lives elsewhere
    kind = "safe" if rule in SAFETY_RULES else "rule"
    expected = {f"data.{rule.table}.{kind}.{rule.id}"} if applicable else set()
    assert failed(cert) == expected
    if applicable:
        assert by_id(cert)[next(iter(expected))].evidence == {"violations": 3}


def test_orphaned_reference_fails() -> None:
    cert = Env(pg_overrides={'LEFT JOIN "member" p': 4}).run()
    assert "data.authorization_request.ref.member_id" in failed(cert)


def test_cosmos_references_are_verified_in_postgres_with_the_actual_ids() -> None:
    env = Env()
    env.run()
    (query, params), = [(q, p) for q, p in env.pg.queries if "unnest" in q and '"member"' in q][:1]
    plan_members = {d["member_id"] for d in env.cosmos.containers["care_plans"].values()}
    assert set(params[0]) == plan_members and params[0] == sorted(plan_members)


def test_cosmos_documents_pointing_at_missing_members_fail() -> None:
    env = Env(pg_overrides={"unnest(": 2})
    assert "data.care_plan.ref.member_id" in failed(env.run())


def test_cosmos_child_pointing_at_a_missing_plan_fails() -> None:
    env = Env()
    next(iter(env.cosmos.containers["care_notes"].values()))["plan_id"] = "SYN-CP99999"
    assert failed(env.run()) == {"data.care_note.ref.plan_id"}


def test_cosmos_non_synthetic_ids_and_count_drift_fail() -> None:
    env = Env()
    plans = env.cosmos.containers["care_plans"]
    plans["REAL-123"] = {"id": "REAL-123", "member_id": "SYN-M000001"}
    cert = env.run()
    assert {"data.care_plan.rows", "data.care_plan.safe.synthetic_ids"} <= failed(cert)


def test_unresolved_cross_store_reference_fails_when_postgres_is_unreachable() -> None:
    cert = Env(connect_error=SinkError("could not connect")).run()
    assert "data.care_plan.ref.member_id" in failed(cert)
    assert "data.db.reachable" in failed(cert)


def test_no_data_loaded_is_not_certifiable() -> None:
    cert = Env().run(data=None)
    assert failed(cert) == {"data.loaded"} and not cert.passed and cert.data_seed is None


def test_missing_connections_output_fails_and_touches_no_database() -> None:
    env = Env()
    cert = env.run(out={"web_url": "https://web.example.test"})
    assert failed(cert) == {"deploy.connections"}
    assert env.pg.queries == [] and env.azure.events == []
    assert "regenerate" in by_id(cert)["deploy.connections"].detail


def test_unreachable_database_fails_without_leaking_the_password() -> None:
    cert = Env(connect_error=SinkError(f"could not connect: password={PASSWORD}")).run()
    check = by_id(cert)["data.db.reachable"]
    assert check.status == CheckStatus.FAIL
    assert "***" in check.detail and PASSWORD not in check.model_dump_json()


def test_firewall_rule_is_closed_even_when_the_check_blows_up() -> None:
    env = Env(connect_error=RuntimeError("boom"))
    env.run()
    assert env.azure.events[:2] == ["open", "close"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [(200, CheckStatus.PASS), (302, CheckStatus.PASS), (404, CheckStatus.WARN), (503, CheckStatus.FAIL),
     (ConnectionError("dns"), CheckStatus.FAIL)],
)
def test_endpoint_outcomes(status: Any, expected: CheckStatus) -> None:
    cert = Env(status=status).run()
    assert by_id(cert)["deploy.endpoint.web_url"].status == expected


def test_plain_http_endpoint_only_warns() -> None:
    cert = Env().run(out=outputs(web_url="http://web.example.test"))
    assert by_id(cert)["deploy.endpoint.web_url"].status == CheckStatus.WARN
    assert cert.passed  # warnings never block certification


def test_demo_without_endpoints_skips_that_check() -> None:
    out = outputs()
    del out["web_url"]
    cert = Env().run(out=out)
    assert by_id(cert)["deploy.endpoints"].status == CheckStatus.SKIP and cert.passed


def test_credential_looking_outputs_fail() -> None:
    cert = Env().run(out=outputs(db_password="hunter2", nested={"api_key": "abc"}, key_vault_name="kv-x"))
    check = by_id(cert)["security.outputs.no_secrets"]
    assert check.status == CheckStatus.FAIL
    assert "db_password" in check.detail and "nested.api_key" in check.detail
    assert "key_vault_name" not in check.detail and "hunter2" not in check.model_dump_json()


@pytest.mark.parametrize(
    ("rules", "error", "expected"),
    [([], None, CheckStatus.PASS), (["AllowAzure", "factory-loader-203-0-113-7"], None, CheckStatus.FAIL),
     (None, __import__("orchestrator.tools.azure_access", fromlist=["x"]).AzureAccessError("403"), CheckStatus.FAIL)],
)
def test_leftover_loader_firewall_rule_fails(rules: Any, error: Any, expected: CheckStatus) -> None:
    cert = Env(rules=rules, rules_error=error).run()
    assert by_id(cert)["security.firewall.clean"].status == expected


def test_skips_alone_do_not_certify() -> None:
    cert = Certification(checks=[], blueprint_version=1)
    assert not cert.passed and cert.summary == {"pass": 0, "warn": 0, "fail": 0, "skip": 0}


def test_published_fields_never_contain_infrastructure_identifiers_or_secrets() -> None:
    """summary/evidence go on the public page; detail (owner-only) may be specific."""
    env = Env(connect_error=SinkError(f"cannot reach {PG_HOST} as {PASSWORD}"), status=ConnectionError("x"))
    cert = env.run(out=outputs(db_password="hunter2"))
    public = " ".join(f"{c.id} {c.title} {c.summary} {c.evidence}" for c in cert.checks)
    for secret in (PASSWORD, COSMOS_KEY, PG_HOST, COSMOS_ENDPOINT, RESOURCE_GROUP, "hunter2", "psql-prior"):
        assert secret not in public, secret
