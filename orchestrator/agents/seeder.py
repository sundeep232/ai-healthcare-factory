"""M3b Seed: generate the synthetic dataset and load it into a deployed demo.

The data plan in the blueprint says which store each domain lands in. Connection facts
come from the ``factory_connections`` Terraform output; secrets are fetched at the last
moment (Key Vault / ARM) and never persisted.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from typing import Any

from orchestrator.agents.data_agents import build_context, generate_dataset, tables_for
from orchestrator.agents.data_agents.schema import TableSpec
from orchestrator.schemas.blueprint import Blueprint
from orchestrator.schemas.demo import SeedSummary, SeedTarget
from orchestrator.tools.azure_access import PG_ADMIN_SECRET, AzureAccess, AzureAccessError
from orchestrator.tools.data_sinks import CosmosSink, PostgresSink, SinkError, connect_postgres
from orchestrator.tools.terraform_files import CONNECTIONS_OUTPUT

logger = logging.getLogger(__name__)

KIND_BY_TYPE = {"postgresql_flexible": "postgres", "cosmos_db": "cosmos"}


class SeedError(RuntimeError):
    """Seeding failed; ``stage`` says where (connections, secrets, postgres, cosmos, ...)."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


def _default_cosmos_database(endpoint: str, key: str, database: str) -> Any:
    from azure.cosmos import CosmosClient

    return CosmosClient(endpoint, credential=key).get_database_client(database)


def _partition_key(path: str) -> Any:
    from azure.cosmos import PartitionKey

    return PartitionKey(path=path)


def resolve_connections(outputs: dict[str, Any]) -> dict[str, Any]:
    """The deterministic ``factory_connections`` output, or a SeedError if the deployment lacks it."""
    conns = outputs.get(CONNECTIONS_OUTPUT)
    if not isinstance(conns, dict) or not conns.get("resource_group"):
        raise SeedError(
            "connections",
            f"this deployment has no '{CONNECTIONS_OUTPUT}' output. It predates data loading: "
            "regenerate (M3) and redeploy (M4) it first.",
        )
    return conns


def plan_placements(
    blueprint: Blueprint, conns: dict[str, Any]
) -> list[tuple[str, str, list[TableSpec]]]:
    """Group tables by target resource, as the blueprint's data plan dictates."""
    types = {r.id: r.type for r in blueprint.resources}
    tables: dict[str, list[TableSpec]] = defaultdict(list)
    for entry in blueprint.data_plan:
        tables[entry.target_resource_id].extend(tables_for(entry.domain))

    placements: list[tuple[str, str, list[TableSpec]]] = []
    for resource_id, specs in tables.items():
        kind = KIND_BY_TYPE.get(types.get(resource_id, ""))
        if kind is None:
            raise SeedError(
                "plan", f"resource '{resource_id}' ({types.get(resource_id)}) cannot hold data"
            )
        if resource_id not in (conns.get(kind) or {}):
            raise SeedError(
                "connections", f"no connection facts for {kind} resource '{resource_id}'"
            )
        if kind == "cosmos":
            bad = [s.name for s in specs if not s.container]
            if bad:
                raise SeedError("plan", f"tables {bad} cannot be stored in Cosmos DB")
        placements.append((resource_id, kind, specs))
    return placements


class SeederAgent:
    def __init__(
        self,
        azure: AzureAccess,
        *,
        connect_pg: Callable[..., Any] = connect_postgres,
        cosmos_database: Callable[[str, str, str], Any] = _default_cosmos_database,
        partition_key: Callable[[str], Any] = _partition_key,
    ) -> None:
        self._azure = azure
        self._connect_pg = connect_pg
        self._cosmos_database = cosmos_database
        self._partition_key = partition_key

    def seed(
        self,
        blueprint: Blueprint,
        outputs: dict[str, Any],
        *,
        seed: int,
        today: date | None = None,
    ) -> SeedSummary:
        conns = resolve_connections(outputs)
        placements = plan_placements(blueprint, conns)

        ctx = build_context(blueprint, seed=seed, today=today)
        dataset = generate_dataset(ctx)
        self._azure.warnings.clear()

        results: list[SeedTarget] = []
        postgres_targets = [p for p in placements if p[1] == "postgres"]
        client_ip = self._azure.public_ip() if postgres_targets else ""
        for resource_id, kind, specs in placements:
            if kind == "postgres":
                results.append(self._load_postgres(conns, resource_id, specs, dataset, client_ip))
            else:
                results.append(self._load_cosmos(conns, resource_id, specs, dataset))

        return SeedSummary(
            seed=seed,
            as_of=ctx.today,
            targets=results,
            total_rows=sum(sum(t.tables.values()) for t in results),
            warnings=list(self._azure.warnings),
        )

    # -- loading -----------------------------------------------------------

    def _load_postgres(
        self, conns: dict[str, Any], resource_id: str, specs: list[TableSpec], dataset: Any, client_ip: str
    ) -> SeedTarget:
        info = conns["postgres"][resource_id]
        vault = conns.get("key_vault")
        if not vault:
            raise SeedError(
                "secrets", "no Key Vault in this deployment, so the database password is unavailable"
            )
        password = ""
        try:
            password = self._azure.get_secret(vault, PG_ADMIN_SECRET)
            with self._azure.postgres_firewall_rule(
                conns["resource_group"], info["server_name"], client_ip
            ):
                conn = self._connect_pg(
                    host=info["host"],
                    database=info["database"],
                    user=info["admin_login"],
                    password=password,
                )
                try:
                    counts = PostgresSink(conn).load(specs, dataset)
                finally:
                    conn.close()
        except (AzureAccessError, SinkError) as exc:
            detail = str(exc).replace(password, "***") if password else str(exc)
            raise SeedError("postgres", detail) from exc
        return SeedTarget(resource_id=resource_id, kind="postgres", host=info["host"], tables=counts)

    def _load_cosmos(
        self, conns: dict[str, Any], resource_id: str, specs: list[TableSpec], dataset: Any
    ) -> SeedTarget:
        info = conns["cosmos"][resource_id]
        try:
            key = self._azure.cosmos_primary_key(conns["resource_group"], info["account_name"])
            database = self._cosmos_database(info["endpoint"], key, info["database"])
            counts = CosmosSink(database, self._partition_key).load(specs, dataset)
        except (AzureAccessError, SinkError) as exc:
            raise SeedError("cosmos", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - SDK auth/network errors
            raise SeedError("cosmos", f"{type(exc).__name__}: {exc}") from exc
        return SeedTarget(resource_id=resource_id, kind="cosmos", host=info["endpoint"], tables=counts)
