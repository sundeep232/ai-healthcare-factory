"""Fakes shared by the M5/M6 tests: Azure, Cosmos, a scripted PostgreSQL, and a seeded Demo."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from orchestrator.agents.data_agents import GenerationContext, generate_dataset
from orchestrator.agents.data_agents.base import Dataset
from orchestrator.agents.seeder import plan_placements
from orchestrator.schemas.blueprint import Blueprint
from orchestrator.schemas.certification import Certification, CheckCategory, CheckResult, CheckStatus
from orchestrator.schemas.demo import Demo, DemoStatus, SeedSummary, SeedTarget
from orchestrator.tests.test_terraform_files import load_blueprint

PASSWORD = "S3cret-Pg-Passw0rd"
COSMOS_KEY = "COSMOS-PRIMARY-KEY"
PG_HOST = "psql-prior.postgres.database.azure.com"
COSMOS_ENDPOINT = "https://cosmos-prior.documents.azure.com:443/"
RESOURCE_GROUP = "rg-prior-auth"
TODAY = date(2026, 10, 24)

SMALL = dict(member=60, provider=6, claims=120, authorization=50, care_management=12)


def connections(**override: Any) -> dict[str, Any]:
    conns: dict[str, Any] = {
        "resource_group": RESOURCE_GROUP,
        "key_vault": "kv-prior",
        "postgres": {
            "db": {"server_name": "psql-prior", "host": PG_HOST, "database": "appdb", "admin_login": "pgadmin"}
        },
        "cosmos": {"docs": {"account_name": "cosmos-prior", "endpoint": COSMOS_ENDPOINT, "database": "care"}},
    }
    conns.update(override)
    return conns


def outputs(**extra: Any) -> dict[str, Any]:
    return {"factory_connections": connections(), "web_url": "https://web.example.test", **extra}


class FakeAzure:
    def __init__(self, *, rules: list[str] | None = None, rules_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self.warnings: list[str] = []
        self.rules = rules or []
        self.rules_error = rules_error

    def public_ip(self) -> str:
        return "203.0.113.7"

    def get_secret(self, vault: str, name: str) -> str:
        return PASSWORD

    def cosmos_primary_key(self, rg: str, account: str) -> str:
        return COSMOS_KEY

    @contextmanager
    def postgres_firewall_rule(self, rg: str, server: str, ip: str) -> Iterator[str]:
        self.events.append("open")
        try:
            yield "rule"
        finally:
            self.events.append("close")

    def postgres_firewall_rule_names(self, rg: str, server: str) -> list[str]:
        self.events.append("list-rules")
        if self.rules_error:
            raise self.rules_error
        return list(self.rules)


class ScriptedCursor:
    def __init__(self, conn: ScriptedPg) -> None:
        self.conn, self.value = conn, 0

    def __enter__(self) -> ScriptedCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        self.conn.queries.append((query, params))
        self.value = self.conn.answer(query)

    def fetchone(self) -> tuple[int]:
        return (self.value,)


class ScriptedPg:
    """Answers every certifier query with a single number: 0 violations unless scripted otherwise."""

    def __init__(self, counts: dict[str, int], overrides: dict[str, int] | None = None) -> None:
        self.counts, self.overrides = counts, overrides or {}
        self.queries: list[tuple[str, Any]] = []
        self.closed = False

    def answer(self, query: str) -> int:
        for needle, value in self.overrides.items():
            if needle in query:
                return value
        if "pg_stat_ssl" in query:
            return 1
        m = re.fullmatch(r'SELECT count\(\*\) FROM "(\w+)"', query)
        if m:
            return self.counts[m.group(1)]
        return 0

    def cursor(self) -> ScriptedCursor:
        return ScriptedCursor(self)

    def close(self) -> None:
        self.closed = True


class CertContainer:
    """Understands exactly the queries the certifier sends to Cosmos."""

    def __init__(self, items: dict[str, dict[str, Any]]) -> None:
        self.items = items

    def query_items(self, query: str, enable_cross_partition_query: bool = False) -> list[Any]:
        if query == "SELECT VALUE COUNT(1) FROM c":
            return [len(self.items)]
        if "NOT STARTSWITH(c.id, 'SYN-')" in query:
            return [sum(1 for k in self.items if not k.startswith("SYN-"))]
        m = re.fullmatch(r"SELECT DISTINCT VALUE c\['(\w+)'\] FROM c", query)
        if m:
            return sorted({d[m.group(1)] for d in self.items.values()})
        if query == "SELECT VALUE c.id FROM c":
            return list(self.items)
        raise AssertionError(f"unexpected Cosmos query: {query}")


class CertCosmos:
    def __init__(self, containers: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.containers = containers

    def get_container_client(self, name: str) -> CertContainer:
        return CertContainer(self.containers[name])


def dataset_for(bp: Blueprint, seed: int = 3) -> Dataset:
    counts = {e.domain: min(e.record_count, SMALL[e.domain.value]) for e in bp.data_plan}
    return generate_dataset(
        GenerationContext(seed=seed, today=TODAY, history_months=12, counts=counts)  # type: ignore[arg-type]
    )


def summary_for(bp: Blueprint, ds: Dataset, seed: int = 3) -> SeedSummary:
    """What a successful seed would have recorded for this dataset."""
    targets = [
        SeedTarget(
            resource_id=rid, kind=kind, host="h",  # type: ignore[arg-type]
            tables={s.name: len(ds.rows(s.name)) for s in specs},
        )
        for rid, kind, specs in plan_placements(bp, connections())
    ]
    return SeedSummary(seed=seed, as_of=TODAY, targets=targets, total_rows=sum(len(r) for r in ds.tables.values()))


def cosmos_for(ds: Dataset) -> CertCosmos:
    from orchestrator.agents.data_agents.schema import tables_for
    from orchestrator.schemas.requirements import HealthcareDomain
    from orchestrator.tools.data_sinks import to_document

    containers: dict[str, dict[str, dict[str, Any]]] = {}
    for spec in tables_for(HealthcareDomain.CARE_MANAGEMENT):
        containers[spec.container] = {
            str(r[spec.primary_key]): to_document(r, str(r[spec.primary_key])) for r in ds.rows(spec.name)
        }
    return CertCosmos(containers)


def passing_certification(bp: Blueprint, seed: int = 3) -> Certification:
    return Certification(
        checks=[
            CheckResult(
                id="data.member.rows", category=CheckCategory.DATA, title="Table 'member' holds the loaded data",
                status=CheckStatus.PASS, summary="'member' has 60 rows, as loaded.", evidence={"rows": 60},
                detail="owner only: connected to psql-prior with pgadmin",
            )
        ],
        blueprint_version=bp.version,
        data_seed=seed,
    )


def deployed_demo(name: str = "example-prior-auth.json", *, certified: bool = False) -> Demo:
    bp = load_blueprint(name)
    ds = dataset_for(bp)
    demo = Demo(
        intent="Prior authorization demo for the utilization management team",
        requirements=bp.requirements, blueprint=bp, status=DemoStatus.DEPLOYED,
        instance_dir="inst-abc", outputs=outputs(), data=summary_for(bp, ds),
    )
    if certified:
        demo.certification = passing_certification(bp)
    return demo
