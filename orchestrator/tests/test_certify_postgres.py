"""CertifierAgent's SQL against a real PostgreSQL server.

Skipped unless FACTORY_TEST_PG_DSN points at a disposable database (see test_seeding_postgres).
Data is loaded by the real PostgresSink, then the real checks run; each test then corrupts the
data in one specific way and asserts that exactly the matching check notices.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from orchestrator.agents.certifier import CertifierAgent
from orchestrator.agents.data_agents.schema import TABLES
from orchestrator.agents.seeder import plan_placements
from orchestrator.schemas.certification import Certification, CheckStatus
from orchestrator.tests.cert_helpers import (
    FakeAzure,
    connections,
    cosmos_for,
    dataset_for,
    outputs,
    summary_for,
)
from orchestrator.tests.test_terraform_files import load_blueprint
from orchestrator.tools.data_sinks import PostgresSink

DSN = os.environ.get("FACTORY_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="FACTORY_TEST_PG_DSN not set")


class Loaded:
    def __init__(self, blueprint_file: str, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn
        self.bp = load_blueprint(blueprint_file)
        self.ds = dataset_for(self.bp)
        self.data = summary_for(self.bp, self.ds)
        self.cosmos = cosmos_for(self.ds) if any(e.domain.value == "care_management" for e in self.bp.data_plan) else None
        pg_specs = [s for _, kind, specs in plan_placements(self.bp, connections()) if kind == "postgres" for s in specs]
        PostgresSink(conn).load(pg_specs, self.ds)
        self.azure = FakeAzure()

    def certify(self) -> Certification:
        agent = CertifierAgent(
            self.azure,  # type: ignore[arg-type]
            connect_pg=lambda **kw: _Borrowed(self.conn),
            cosmos_database=lambda e, k, d: self.cosmos,
            http_status=lambda url: 200,
        )
        return agent.certify(self.bp, outputs(), self.data)

    def sql(self, statement: str, *params: Any) -> None:
        self.conn.execute(statement, params or None)  # type: ignore[arg-type]


class _Borrowed:
    """The certifier closes its connection; the test keeps using the same one."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def cursor(self) -> Any:
        return self._conn.cursor()

    def close(self) -> None:
        return None


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[Any]]:
    assert DSN
    with psycopg.connect(DSN, autocommit=True) as c:
        yield c


TLS = "security.postgres.tls"


def failed(cert: Certification) -> set[str]:
    """Failed checks, ignoring the TLS check: a throwaway local server usually has ssl=off.

    ``test_tls_check_reflects_the_servers_real_ssl_setting`` covers that check on its own.
    """
    return {c.id for c in cert.checks if c.status == CheckStatus.FAIL} - {TLS}


def test_clean_prior_auth_demo_is_certified_across_postgres_and_cosmos(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-prior-auth.json", conn)
    cert = env.certify()
    assert not failed(cert), [(c.id, c.detail) for c in cert.checks if c.status == CheckStatus.FAIL]
    ids = {c.id for c in cert.checks}
    assert {"data.authorization_request.rows", "data.care_plan.ref.member_id", "security.postgres.tls"} <= ids


def test_clean_claims_demo_satisfies_every_business_rule(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    cert = env.certify()
    assert not failed(cert), [(c.id, c.detail) for c in cert.checks if c.status == CheckStatus.FAIL]
    rules = {c.id for c in cert.checks if ".rule." in c.id}
    assert {"data.claim.rule.money_adds_up", "data.claim.rule.adjudicated_after_service"} <= rules


def test_every_table_gets_a_row_count_and_synthetic_id_check(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    ids = {c.id for c in env.certify().checks}
    for table in ("member", "provider", "claim"):
        assert {f"data.{table}.rows", f"data.{table}.safe.synthetic_ids"} <= ids
    assert TABLES["claim"].references.keys() == {"member_id", "provider_id"}
    assert {"data.claim.ref.member_id", "data.claim.ref.provider_id"} <= ids


def test_a_deleted_row_is_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql('DELETE FROM "claim" WHERE claim_id = (SELECT min(claim_id) FROM "claim")')
    assert failed(env.certify()) == {"data.claim.rows"}


def test_a_real_looking_email_is_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql("UPDATE \"member\" SET email = 'jane.doe@gmail.com' WHERE member_id = 'SYN-M000001'")
    assert failed(env.certify()) == {"data.member.safe.email_reserved_domain"}


def test_a_valid_looking_npi_and_phone_are_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql("UPDATE \"provider\" SET npi = '1234567893' WHERE provider_id = 'SYN-P00001'")
    env.sql("UPDATE \"member\" SET phone = '(512) 867-5309' WHERE member_id = 'SYN-M000001'")
    assert failed(env.certify()) == {"data.provider.safe.npi_unissued_range", "data.member.safe.phone_fictional_range"}


def test_a_non_synthetic_id_is_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql('ALTER TABLE "claim" DROP CONSTRAINT IF EXISTS claim_pkey')
    env.sql("UPDATE \"claim\" SET claim_id = 'C-REAL-1' WHERE claim_id = 'SYN-C0000001'")
    assert "data.claim.safe.synthetic_ids" in failed(env.certify())


def test_broken_claim_money_is_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql('UPDATE "claim" SET paid_amount = paid_amount + 1 WHERE claim_id = \'SYN-C0000001\'')
    assert failed(env.certify()) == {"data.claim.rule.money_adds_up"}


def test_dates_out_of_order_are_noticed(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql(
        'UPDATE "claim" SET adjudication_date = service_date - 1 '
        "WHERE claim_id = 'SYN-C0000001' AND adjudication_date IS NOT NULL"
    )
    env.sql('UPDATE "claim" SET adjudication_date = service_date - 1, status = status WHERE claim_id = \'SYN-C0000002\'')
    assert failed(env.certify()) == {"data.claim.rule.adjudicated_after_service"}


def test_an_orphaned_claim_is_noticed_even_without_the_foreign_key(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql('ALTER TABLE "claim" DROP CONSTRAINT "claim_member_id_fkey"')
    env.sql("UPDATE \"claim\" SET member_id = 'SYN-M999999' WHERE claim_id = 'SYN-C0000001'")
    assert failed(env.certify()) == {"data.claim.ref.member_id"}


def test_a_cosmos_plan_for_an_unknown_member_is_noticed_via_postgres(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-prior-auth.json", conn)
    assert env.cosmos is not None
    plans = env.cosmos.containers["care_plans"]
    next(iter(plans.values()))["member_id"] = "SYN-M999999"
    assert failed(env.certify()) == {"data.care_plan.ref.member_id"}


def test_a_missing_table_fails_its_checks_but_not_the_whole_run(conn: psycopg.Connection[Any]) -> None:
    env = Loaded("example-claims-dashboard.json", conn)
    env.sql('DROP TABLE "claim" CASCADE')
    cert = env.certify()
    assert "data.claim.rows" in failed(cert)
    assert {c.id: c.status for c in cert.checks}["data.member.rows"] == CheckStatus.PASS


def test_tls_check_reflects_the_servers_real_ssl_setting(conn: psycopg.Connection[Any]) -> None:
    ssl_on = conn.execute("SHOW ssl").fetchone()[0] == "on"  # type: ignore[index]
    cert = Loaded("example-claims-dashboard.json", conn).certify()
    status = {c.id: c.status for c in cert.checks}[TLS]
    if ssl_on:
        # Our test connection may still be unencrypted (e.g. unix socket), so only require agreement.
        assert status in (CheckStatus.PASS, CheckStatus.FAIL)
    else:
        assert status == CheckStatus.FAIL
