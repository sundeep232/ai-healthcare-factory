"""PostgresSink against a real PostgreSQL server.

Skipped unless FACTORY_TEST_PG_DSN points at a disposable database, for example:

    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pw postgres:16
    $env:FACTORY_TEST_PG_DSN = "postgresql://postgres:pw@localhost:5432/postgres"

The test drops and recreates the dataset's tables, so never point it at real data.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from typing import Any

import psycopg
import pytest

from orchestrator.agents.data_agents import GenerationContext, generate_dataset, tables_for
from orchestrator.agents.data_agents.schema import TABLES
from orchestrator.schemas.requirements import HealthcareDomain as D
from orchestrator.tools.data_sinks import PostgresSink, SinkError

DSN = os.environ.get("FACTORY_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="FACTORY_TEST_PG_DSN not set")

COUNTS = {D.MEMBER: 300, D.PROVIDER: 12, D.CLAIMS: 900, D.AUTHORIZATION: 400, D.CARE_MANAGEMENT: 40}


def dataset(seed: int = 1) -> Any:
    ctx = GenerationContext(seed=seed, today=date(2026, 10, 24), history_months=12, counts=COUNTS)
    return generate_dataset(ctx)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[Any]]:
    assert DSN
    with psycopg.connect(DSN, autocommit=True) as c:
        yield c


def scalar(conn: psycopg.Connection[Any], query: str) -> Any:
    return conn.execute(query).fetchone()[0]  # type: ignore[index]


def test_full_load_with_real_constraints(conn: psycopg.Connection[Any]) -> None:
    ds = dataset()
    counts = PostgresSink(conn).load(list(TABLES.values()), ds)
    assert counts == ds.counts()

    # Referential integrity is enforced by the database, and nothing is orphaned.
    for spec in TABLES.values():
        for col, parent in spec.references.items():
            pk = TABLES[parent].primary_key
            orphans = scalar(
                conn,
                f'SELECT count(*) FROM "{spec.name}" c LEFT JOIN "{parent}" p '
                f'ON c."{col}" = p."{pk}" WHERE p."{pk}" IS NULL',
            )
            assert orphans == 0, f"{spec.name}.{col}"
    fk_count = scalar(conn, "SELECT count(*) FROM information_schema.table_constraints "
                            "WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public'")
    assert fk_count == sum(len(s.references) for s in TABLES.values())

    # Types survive the round trip.
    row = conn.execute(
        'SELECT date_of_birth, risk_score, coverage_end_date FROM "member" ORDER BY member_id LIMIT 1'
    ).fetchone()
    assert isinstance(row[0], date) and isinstance(row[1], float)  # type: ignore[index]
    assert scalar(conn, "SELECT sum(paid_amount + member_responsibility - allowed_amount) FROM claim") == 0
    assert scalar(conn, "SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'ix\\_%'") == 19


def test_reseed_replaces_instead_of_appending(conn: psycopg.Connection[Any]) -> None:
    sink = PostgresSink(conn)
    sink.load(list(TABLES.values()), dataset(seed=1))
    first_ids = scalar(conn, "SELECT string_agg(last_name, ',' ORDER BY member_id) FROM member")
    sink.load(list(TABLES.values()), dataset(seed=2))
    assert scalar(conn, "SELECT count(*) FROM member") == COUNTS[D.MEMBER]
    assert scalar(conn, "SELECT count(*) FROM claim") == COUNTS[D.CLAIMS]
    assert scalar(conn, "SELECT string_agg(last_name, ',' ORDER BY member_id) FROM member") != first_ids


def test_failed_load_rolls_back_and_keeps_previous_data(conn: psycopg.Connection[Any]) -> None:
    sink = PostgresSink(conn)
    good = dataset(seed=1)
    sink.load(list(TABLES.values()), good)

    bad = dataset(seed=2)
    bad.tables["claim"][5]["member_id"] = "SYN-M999999"  # violates the foreign key
    with pytest.raises(SinkError, match="PostgreSQL load failed"):
        sink.load(list(TABLES.values()), bad)

    # The drop/create/copy ran in one transaction, so the first dataset is intact.
    assert scalar(conn, "SELECT count(*) FROM claim") == COUNTS[D.CLAIMS]
    assert scalar(conn, "SELECT count(*) FROM member") == COUNTS[D.MEMBER]
    assert scalar(conn, "SELECT min(member_id) FROM member") == "SYN-M000001"


def test_care_management_alone_loads_without_member_table(conn: psycopg.Connection[Any]) -> None:
    """Care-plan tables on their own database: no foreign key to a member table that isn't there."""
    conn.execute('DROP TABLE IF EXISTS "timeline_event", "care_note", "care_plan", '
                 '"authorization_request", "claim", "provider", "member" CASCADE')
    ds = dataset()
    counts = PostgresSink(conn).load(tables_for(D.CARE_MANAGEMENT), ds)
    assert counts["care_plan"] == COUNTS[D.CARE_MANAGEMENT]
    assert scalar(conn, "SELECT to_regclass('public.member') IS NULL")
