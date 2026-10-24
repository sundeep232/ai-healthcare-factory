"""M5 Certify: prove that a live demo matches its blueprint, and keep the evidence.

Every check asks the *running* instance (not our own records) and yields a CheckResult.
Database checks are all of one shape: "how many rows violate this rule?". The expected
answer is zero, which keeps checks easy to read, test and extend.

Public-safety contract: ``summary`` and ``evidence`` appear on the share page, so they only
hold counts, table names and our own wording. ``detail`` is owner-only diagnostics.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from orchestrator.agents.data_agents.schema import TABLES, TableSpec
from orchestrator.agents.seeder import (
    SeedError,
    _default_cosmos_database,
    plan_placements,
    resolve_connections,
)
from orchestrator.schemas.blueprint import Blueprint
from orchestrator.schemas.certification import (
    Certification,
    CheckCategory,
    CheckResult,
    CheckStatus,
)
from orchestrator.schemas.demo import SeedSummary, SeedTarget
from orchestrator.tools.azure_access import PG_ADMIN_SECRET, AzureAccess, AzureAccessError
from orchestrator.tools.data_sinks import SinkError, connect_postgres
from orchestrator.tools.outputs import public_endpoints
from orchestrator.tools.terraform_files import CONNECTIONS_OUTPUT

logger = logging.getLogger(__name__)

LOADER_RULE_PREFIX = "factory-loader-"
SYNTHETIC_PREFIX = "SYN-"

_D, _S = CheckCategory.DATA, CheckStatus


@dataclass(frozen=True)
class Rule:
    """A table rule: ``violation`` is a SQL predicate that is TRUE for a bad row."""

    id: str
    table: str
    title: str
    violation: str


# Facts that must hold for every generated row. Column names come from our own schema.
BUSINESS_RULES: tuple[Rule, ...] = (
    Rule("money_adds_up", "claim", "Paid plus member share equals the allowed amount",
         "paid_amount + member_responsibility <> allowed_amount"),
    Rule("allowed_within_billed", "claim", "Allowed amount never exceeds the billed amount",
         "allowed_amount > billed_amount"),
    Rule("no_negative_amounts", "claim", "No claim has a negative dollar amount",
         "billed_amount < 0 OR allowed_amount < 0 OR paid_amount < 0 OR member_responsibility < 0"),
    Rule("adjudicated_after_service", "claim", "Claims are adjudicated on or after the service date",
         "adjudication_date IS NOT NULL AND adjudication_date < service_date"),
    Rule("decided_after_requested", "authorization_request",
         "Authorization decisions come on or after the request date",
         "decision_date IS NOT NULL AND decision_date < requested_date"),
    Rule("units_within_request", "authorization_request",
         "Approved units never exceed requested units",
         "units_approved IS NOT NULL AND units_approved > units_requested"),
    Rule("coverage_dates_ordered", "member", "Coverage ends after it begins",
         "coverage_end_date IS NOT NULL AND coverage_end_date < coverage_effective_date"),
)

# Proof that no real PHI/PII could be in the data: identifiers are in reserved/invalid ranges.
SAFETY_RULES: tuple[Rule, ...] = (
    Rule("email_reserved_domain", "member", "Member emails use the reserved .invalid domain",
         "email NOT LIKE '%@example.invalid'"),
    Rule("phone_fictional_range", "member", "Phone numbers are in the fictional 555-01XX range",
         "phone !~ '555-01[0-9]{2}$'"),
    Rule("npi_unissued_range", "provider", "Provider NPIs are in the unissued 9XXXXXXXXX range",
         "npi !~ '^9[0-9]{9}$'"),
)

_SECRET_KEY = re.compile(
    r"password|passwd|secret|token|connection_?string|primary_?key|access_?key|api_?key|account_?key",
    re.IGNORECASE,
)


def _http_status(url: str) -> int:
    """HTTP status of ``url``. Two tries: a scale-to-zero app needs a moment to wake."""
    last: Exception | None = None
    for _ in range(2):
        try:
            return httpx.get(url, timeout=20.0, follow_redirects=True).status_code
        except httpx.HTTPError as exc:
            last = exc
    raise last  # type: ignore[misc]


@dataclass
class _Run:
    """Mutable state of one certification run."""

    blueprint: Blueprint
    outputs: dict[str, Any]
    data: SeedSummary | None
    checks: list[CheckResult] = field(default_factory=list)
    # (child table, column) -> (parent spec, distinct child values) for cross-store references
    pending_refs: dict[tuple[str, str], tuple[TableSpec, set[str]]] = field(default_factory=dict)

    def add(
        self, id: str, category: CheckCategory, title: str, status: CheckStatus,
        summary: str, detail: str = "", **evidence: Any,
    ) -> None:
        self.checks.append(CheckResult(
            id=id, category=category, title=title, status=status,
            summary=summary, detail=detail, evidence=evidence,
        ))

    def count(self, status: CheckStatus) -> int:
        return sum(1 for c in self.checks if c.status == status)


class CertifierAgent:
    def __init__(
        self,
        azure: AzureAccess,
        *,
        connect_pg: Callable[..., Any] = connect_postgres,
        cosmos_database: Callable[[str, str, str], Any] = _default_cosmos_database,
        http_status: Callable[[str], int] = _http_status,
    ) -> None:
        self._azure = azure
        self._connect_pg = connect_pg
        self._cosmos_database = cosmos_database
        self._http_status = http_status

    def certify(
        self, blueprint: Blueprint, outputs: dict[str, Any], data: SeedSummary | None
    ) -> Certification:
        """Run every applicable check. Never raises: problems become failed checks."""
        run = _Run(blueprint, outputs, data)
        conns = self._check_deployment(run)
        self._check_endpoints(run)
        self._check_outputs_hold_no_secrets(run)
        if conns is not None:
            self._check_data(run, conns)
            self._check_firewall_is_clean(run, conns)
        return Certification(
            checks=run.checks,
            blueprint_version=blueprint.version,
            data_seed=data.seed if data else None,
        )

    # -- deployment ----------------------------------------------------------

    def _check_deployment(self, run: _Run) -> dict[str, Any] | None:
        try:
            conns = resolve_connections(run.outputs)
        except SeedError as exc:
            run.add("deploy.connections", CheckCategory.DEPLOYMENT, "Deployment exposes its connection facts",
                    _S.FAIL, "The deployment does not expose the facts needed to verify it.", exc.detail)
            return None
        run.add("deploy.connections", CheckCategory.DEPLOYMENT, "Deployment exposes its connection facts",
                _S.PASS, "The deployment exposes the facts needed to verify it.")
        return conns

    def _check_endpoints(self, run: _Run) -> None:
        urls = public_endpoints(run.outputs)

        if not urls:
            run.add("deploy.endpoints", CheckCategory.DEPLOYMENT, "Public endpoints respond", _S.SKIP,
                    "This demo has no public endpoints.")
            return
        for name, url in sorted(urls.items()):
            check_id, title = f"deploy.endpoint.{name}", f"Endpoint '{name}' responds"
            try:
                code = self._http_status(url)
            except Exception as exc:  # noqa: BLE001 - any transport failure means "not reachable"
                run.add(check_id, CheckCategory.DEPLOYMENT, title, _S.FAIL,
                        "The endpoint did not respond.", f"{type(exc).__name__}: {exc}")
                continue
            if code >= 500:
                run.add(check_id, CheckCategory.DEPLOYMENT, title, _S.FAIL,
                        f"The endpoint answered with a server error (HTTP {code}).", status_code=code)
            elif url.startswith("http://"):
                run.add(check_id, CheckCategory.DEPLOYMENT, title, _S.WARN,
                        f"The endpoint responds (HTTP {code}) but is not served over HTTPS.",
                        status_code=code)
            elif code >= 400:
                run.add(check_id, CheckCategory.DEPLOYMENT, title, _S.WARN,
                        f"The endpoint is up but answered HTTP {code}; app content may not be deployed yet.",
                        status_code=code)
            else:
                run.add(check_id, CheckCategory.DEPLOYMENT, title, _S.PASS,
                        f"The endpoint responds over HTTPS (HTTP {code}).", status_code=code)

    # -- security ------------------------------------------------------------

    def _check_outputs_hold_no_secrets(self, run: _Run) -> None:
        leaks = sorted(_secret_paths(run.outputs))
        title = "Deployment outputs expose no credentials"
        if leaks:
            run.add("security.outputs.no_secrets", CheckCategory.SECURITY, title, _S.FAIL,
                    "Some deployment outputs look like credentials.", ", ".join(leaks), leaks=len(leaks))
        else:
            run.add("security.outputs.no_secrets", CheckCategory.SECURITY, title, _S.PASS,
                    "No deployment output looks like a credential.", leaks=0)

    def _check_firewall_is_clean(self, run: _Run, conns: dict[str, Any]) -> None:
        """Runs last, after our own temporary rule is gone, to prove cleanup really happened."""
        servers = {
            rid: info["server_name"]
            for rid, info in (conns.get("postgres") or {}).items()
            if isinstance(info, dict) and info.get("server_name")
        }
        title = "No temporary loader firewall rules remain"
        if not servers:
            run.add("security.firewall.clean", CheckCategory.SECURITY, title, _S.SKIP,
                    "This demo has no PostgreSQL server.")
            return
        leftovers: list[str] = []
        try:
            for server in servers.values():
                names = self._azure.postgres_firewall_rule_names(conns["resource_group"], server)
                leftovers += [n for n in names if n.startswith(LOADER_RULE_PREFIX)]
        except AzureAccessError as exc:
            run.add("security.firewall.clean", CheckCategory.SECURITY, title, _S.FAIL,
                    "Could not read the database firewall rules to verify.", str(exc))
            return
        if leftovers:
            run.add("security.firewall.clean", CheckCategory.SECURITY, title, _S.FAIL,
                    "A temporary firewall rule from data loading is still open.",
                    f"leftover rules: {', '.join(leftovers)}. Delete them in the Azure portal.",
                    leftover_rules=len(leftovers))
        else:
            run.add("security.firewall.clean", CheckCategory.SECURITY, title, _S.PASS,
                    "Database firewall has no temporary loader rules.", leftover_rules=0)

    # -- data ----------------------------------------------------------------

    def _check_data(self, run: _Run, conns: dict[str, Any]) -> None:
        if run.data is None:
            run.add("data.loaded", _D, "Synthetic data is loaded", _S.FAIL,
                    "No synthetic data has been loaded into this demo yet.",
                    "Run the data step (seed) before certifying.")
            return
        try:
            placements = plan_placements(run.blueprint, conns)
        except SeedError as exc:
            run.add("data.plan", _D, "Data plan matches the deployment", _S.FAIL,
                    "The blueprint's data plan does not match what was deployed.", exc.detail)
            return

        loaded = {t.resource_id: t for t in run.data.targets}
        # Cosmos first: PostgreSQL checks then verify the cross-store references it collected.
        for rid, kind, specs in sorted(placements, key=lambda p: p[1] != "cosmos"):
            record = loaded.get(rid)
            if record is None:
                run.add(f"data.{rid}.loaded", _D, "Data load was recorded", _S.FAIL,
                        f"The data load recorded nothing for '{rid}'.")
                continue
            if kind == "cosmos":
                self._check_cosmos(run, conns, rid, specs, record)
            else:
                self._check_postgres(run, conns, rid, specs, record)

        for (table, column), (parent, _values) in sorted(run.pending_refs.items()):
            run.add(f"data.{table}.ref.{column}", _D, _ref_title(table, column, parent.name), _S.FAIL,
                    "Could not verify: the database holding the parent table was unreachable.")

    # PostgreSQL

    def _check_postgres(
        self, run: _Run, conns: dict[str, Any], rid: str, specs: list[TableSpec], record: SeedTarget
    ) -> None:
        info = conns["postgres"][rid]
        vault = conns.get("key_vault")
        password = ""
        try:
            if not vault:
                raise AzureAccessError("no Key Vault in this deployment")
            password = self._azure.get_secret(vault, PG_ADMIN_SECRET)
            ip = self._azure.public_ip()
            with self._azure.postgres_firewall_rule(conns["resource_group"], info["server_name"], ip):
                conn = self._connect_pg(
                    host=info["host"], database=info["database"],
                    user=info["admin_login"], password=password,
                )
                try:
                    self._postgres_checks(run, conn, specs, record)
                finally:
                    conn.close()
        except (AzureAccessError, SinkError, SeedError) as exc:
            self._unreachable(run, f"data.{rid}.reachable", "PostgreSQL is reachable", str(exc), password)
        except Exception as exc:  # noqa: BLE001 - driver errors vary
            self._unreachable(
                run, f"data.{rid}.reachable", "PostgreSQL is reachable",
                f"{type(exc).__name__}: {exc}", password,
            )

    def _postgres_checks(self, run: _Run, conn: Any, specs: list[TableSpec], record: SeedTarget) -> None:
        names = {s.name for s in specs}

        # TLS: our own session must be encrypted, which is what `sslmode=require` promises.
        self._query_check(
            run, conn, "security.postgres.tls", CheckCategory.SECURITY, "Database connections are encrypted",
            "SELECT count(*) FROM pg_stat_ssl WHERE pid = pg_backend_pid() AND ssl",
            ok=lambda n: n == 1, ok_summary="The verification session used TLS.",
            bad_summary="The verification session was not encrypted.", key="encrypted_sessions",
        )

        for spec in specs:
            expected = record.tables.get(spec.name)
            self._query_check(
                run, conn, f"data.{spec.name}.rows", _D, f"Table '{spec.name}' holds the loaded data",
                f'SELECT count(*) FROM "{spec.name}"',
                ok=lambda n, e=expected: e is not None and n == e and n > 0,
                ok_summary=f"'{spec.name}' has {expected:,} rows, as loaded." if expected else "",
                bad_summary=f"'{spec.name}' does not hold the rows that were loaded.",
                key="rows", extra={"loaded": expected},
            )
            for column, parent in spec.references.items():
                if parent in names:
                    pk = TABLES[parent].primary_key
                    self._query_check(
                        run, conn, f"data.{spec.name}.ref.{column}", _D, _ref_title(spec.name, column, parent),
                        f'SELECT count(*) FROM "{spec.name}" c LEFT JOIN "{parent}" p '
                        f'ON c."{column}" = p."{pk}" WHERE p."{pk}" IS NULL',
                        ok=lambda n: n == 0,
                        ok_summary=f"Every '{spec.name}.{column}' points to a real '{parent}'.",
                        bad_summary=f"Some '{spec.name}' rows point to a '{parent}' that does not exist.",
                        key="orphans",
                    )
            self._query_check(
                run, conn, f"data.{spec.name}.safe.synthetic_ids", _D,
                f"'{spec.name}' ids carry the synthetic prefix",
                f'SELECT count(*) FROM "{spec.name}" WHERE "{spec.primary_key}" NOT LIKE \'{SYNTHETIC_PREFIX}%\'',
                ok=lambda n: n == 0, ok_summary=f"Every '{spec.name}' id starts with {SYNTHETIC_PREFIX}.",
                bad_summary=f"Some '{spec.name}' ids are not marked synthetic.", key="violations",
            )

        for rule in (*SAFETY_RULES, *BUSINESS_RULES):
            if rule.table not in names:
                continue
            kind = "safe" if rule in SAFETY_RULES else "rule"
            self._query_check(
                run, conn, f"data.{rule.table}.{kind}.{rule.id}", _D, rule.title,
                f'SELECT count(*) FROM "{rule.table}" WHERE {rule.violation}',
                ok=lambda n: n == 0, ok_summary=f"{rule.title}: verified.",
                bad_summary=f"Rule broken: {rule.title.lower()}.", key="violations",
            )

        # Cross-store references: Cosmos children whose parent table lives here.
        for key in [k for k, (parent, _) in run.pending_refs.items() if parent.name in names]:
            parent, values = run.pending_refs.pop(key)
            table, column = key
            self._query_check(
                run, conn, f"data.{table}.ref.{column}", _D, _ref_title(table, column, parent.name),
                f'SELECT count(*) FROM unnest(%s::text[]) AS v(id) LEFT JOIN "{parent.name}" p '
                f'ON p."{parent.primary_key}" = v.id WHERE p."{parent.primary_key}" IS NULL',
                params=(sorted(values),),
                ok=lambda n: n == 0,
                ok_summary=f"Every '{table}.{column}' points to a real '{parent.name}'.",
                bad_summary=f"Some '{table}' documents point to a '{parent.name}' that does not exist.",
                key="orphans", extra={"distinct_references": len(values)},
            )

    def _query_check(
        self, run: _Run, conn: Any, check_id: str, category: CheckCategory, title: str, query: str,
        *, ok: Callable[[int], bool], ok_summary: str, bad_summary: str, key: str,
        params: tuple[Any, ...] = (), extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            with conn.cursor() as cur:
                # No params => none passed at all, so '%' inside LIKE patterns stays literal.
                cur.execute(query, params or None)
                n = int(cur.fetchone()[0])
        except Exception as exc:  # noqa: BLE001 - a broken query fails this check, not the run
            run.add(check_id, category, title, _S.FAIL, "The check could not be run.",
                    f"{type(exc).__name__}: {exc}")
            return
        passed = ok(n)
        run.add(check_id, category, title, _S.PASS if passed else _S.FAIL,
                ok_summary if passed else bad_summary, **{key: n, **(extra or {})})

    # Cosmos DB

    def _check_cosmos(
        self, run: _Run, conns: dict[str, Any], rid: str, specs: list[TableSpec], record: SeedTarget
    ) -> None:
        info = conns["cosmos"][rid]
        key = ""
        try:
            key = self._azure.cosmos_primary_key(conns["resource_group"], info["account_name"])
            database = self._cosmos_database(info["endpoint"], key, info["database"])
            by_name = {s.name: s for s in specs}
            for spec in specs:
                self._cosmos_table_checks(run, database, spec, record, by_name)
        except (AzureAccessError, SinkError) as exc:
            self._unreachable(run, f"data.{rid}.reachable", "Cosmos DB is reachable", str(exc), key)
        except Exception as exc:  # noqa: BLE001
            self._unreachable(
                run, f"data.{rid}.reachable", "Cosmos DB is reachable", f"{type(exc).__name__}: {exc}", key
            )

    def _cosmos_table_checks(
        self, run: _Run, database: Any, spec: TableSpec, record: SeedTarget, by_name: dict[str, TableSpec]
    ) -> None:
        def query(container_name: str, text: str) -> list[Any]:
            container = database.get_container_client(container_name)
            return list(container.query_items(text, enable_cross_partition_query=True))

        def scalar(text: str) -> int:
            return int(query(spec.container, text)[0])

        expected = record.tables.get(spec.name)
        self._cosmos_check(
            run, f"data.{spec.name}.rows", f"Container '{spec.container}' holds the loaded data",
            lambda: scalar("SELECT VALUE COUNT(1) FROM c"),
            ok=lambda n: expected is not None and n == expected and n > 0,
            ok_summary=f"'{spec.container}' has {expected:,} documents, as loaded." if expected else "",
            bad_summary=f"'{spec.container}' does not hold the documents that were loaded.",
            key="rows", extra={"loaded": expected},
        )
        self._cosmos_check(
            run, f"data.{spec.name}.safe.synthetic_ids", f"'{spec.name}' ids carry the synthetic prefix",
            lambda: scalar(f"SELECT VALUE COUNT(1) FROM c WHERE NOT STARTSWITH(c.id, '{SYNTHETIC_PREFIX}')"),
            ok=lambda n: n == 0, ok_summary=f"Every '{spec.name}' id starts with {SYNTHETIC_PREFIX}.",
            bad_summary=f"Some '{spec.name}' ids are not marked synthetic.", key="violations",
        )
        for column, parent_name in spec.references.items():
            parent = TABLES[parent_name]
            title = _ref_title(spec.name, column, parent_name)
            check_id = f"data.{spec.name}.ref.{column}"
            try:
                referenced = {str(v) for v in query(spec.container, f"SELECT DISTINCT VALUE c['{column}'] FROM c")}
            except Exception as exc:  # noqa: BLE001
                run.add(check_id, _D, title, _S.FAIL, "The check could not be run.",
                        f"{type(exc).__name__}: {exc}")
                continue
            if parent_name not in by_name:
                # Parent lives in another database: PostgreSQL verifies these once it is open.
                run.pending_refs[(spec.name, column)] = (parent, referenced)
                continue
            self._cosmos_check(
                run, check_id, title,
                lambda p=parent, r=referenced: len(r - {str(v) for v in query(p.container, "SELECT VALUE c.id FROM c")}),
                ok=lambda n: n == 0,
                ok_summary=f"Every '{spec.name}.{column}' points to a real '{parent_name}'.",
                bad_summary=f"Some '{spec.name}' documents point to a '{parent_name}' that does not exist.",
                key="orphans", extra={"distinct_references": len(referenced)},
            )
    def _cosmos_check(
        self, run: _Run, check_id: str, title: str, measure: Callable[[], int],
        *, ok: Callable[[int], bool], ok_summary: str, bad_summary: str, key: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            n = measure()
        except Exception as exc:  # noqa: BLE001
            run.add(check_id, _D, title, _S.FAIL, "The check could not be run.", f"{type(exc).__name__}: {exc}")
            return
        passed = ok(n)
        run.add(check_id, _D, title, _S.PASS if passed else _S.FAIL,
                ok_summary if passed else bad_summary, **{key: n, **(extra or {})})

    # -- shared --------------------------------------------------------------

    @staticmethod
    def _unreachable(run: _Run, check_id: str, title: str, error: str, secret: str) -> None:
        detail = error.replace(secret, "***") if secret else error
        logger.warning("certify: %s: %s", check_id, detail)
        run.add(check_id, _D, title, _S.FAIL, "The database could not be reached to verify its data.", detail)


def _ref_title(table: str, column: str, parent: str) -> str:
    return f"'{table}.{column}' references only existing '{parent}' rows"


def _secret_paths(value: Any, path: str = "") -> list[str]:
    """Dotted paths of dict keys that look like credentials and hold a non-empty value."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            here = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY.search(str(key)) and isinstance(inner, (str, int, float)) and inner not in ("", 0):
                found.append(here)
            else:
                found += _secret_paths(inner, here)
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            found += _secret_paths(inner, f"{path}[{i}]")
    return found


__all__ = ["BUSINESS_RULES", "CONNECTIONS_OUTPUT", "SAFETY_RULES", "CertifierAgent", "Rule"]
