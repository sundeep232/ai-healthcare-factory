"""Writers that put a generated Dataset into live PostgreSQL / Cosmos DB instances.

Both are idempotent "replace" loads: running M3b again swaps the data for the new seed
instead of appending, so a demo can be re-seeded at will.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql

from orchestrator.agents.data_agents.base import Dataset
from orchestrator.agents.data_agents.schema import TableSpec

logger = logging.getLogger(__name__)


class SinkError(RuntimeError):
    """A load failed; the message says which store and why."""


# -- PostgreSQL ----------------------------------------------------------------


def order_by_dependency(specs: Iterable[TableSpec]) -> list[TableSpec]:
    """Parents before children, considering only references inside this set."""
    pending = {s.name: s for s in specs}
    ordered: list[TableSpec] = []
    while pending:
        ready = [
            s
            for s in pending.values()
            if all(p == s.name or p not in pending for p in s.references.values())
        ]
        if not ready:
            raise SinkError(f"circular table references among {sorted(pending)}")
        for spec in ready:
            ordered.append(spec)
            del pending[spec.name]
    return ordered


def build_schema_statements(specs: list[TableSpec]) -> tuple[list[sql.Composable], list[sql.Composable]]:
    """(drop+create statements, index statements) for the given tables."""
    ordered = order_by_dependency(specs)
    in_set = {s.name for s in ordered}

    drops = [
        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(s.name))
        for s in reversed(ordered)
    ]
    creates: list[sql.Composable] = []
    for spec in ordered:
        parts: list[sql.Composable] = []
        for col in spec.columns:
            nullability = sql.SQL("") if col.nullable else sql.SQL(" NOT NULL")
            parts.append(
                sql.SQL("{} {}{}").format(
                    sql.Identifier(col.name), sql.SQL(col.sql_type), nullability
                )
            )
        parts.append(sql.SQL("PRIMARY KEY ({})").format(sql.Identifier(spec.primary_key)))
        for col_name, parent in spec.references.items():
            if parent in in_set:
                parent_pk = next(s.primary_key for s in ordered if s.name == parent)
                parts.append(
                    sql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
                        sql.Identifier(col_name), sql.Identifier(parent), sql.Identifier(parent_pk)
                    )
                )
        creates.append(
            sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier(spec.name), sql.SQL(", ").join(parts))
        )
    indexes = [
        sql.SQL("CREATE INDEX {} ON {} ({})").format(
            sql.Identifier(f"ix_{spec.name}_{col}"), sql.Identifier(spec.name), sql.Identifier(col)
        )
        for spec in ordered
        for col in spec.indexes
    ]
    return drops + creates, indexes


class PostgresSink:
    def __init__(self, connection: Any) -> None:
        """``connection``: an open psycopg connection (the sink commits or rolls back)."""
        self._conn = connection

    def load(self, specs: list[TableSpec], dataset: Dataset) -> dict[str, int]:
        """Replace the tables with the dataset's rows; returns verified row counts."""
        ordered = order_by_dependency(specs)
        schema, indexes = build_schema_statements(specs)
        try:
            with self._conn.transaction():
                with self._conn.cursor() as cur:
                    for stmt in schema:
                        cur.execute(stmt)
                    for spec in ordered:
                        self._copy(cur, spec, dataset.rows(spec.name))
                    for stmt in indexes:
                        cur.execute(stmt)
            counts = self._count(ordered)
        except psycopg.Error as exc:
            raise SinkError(f"PostgreSQL load failed: {exc}") from exc

        for spec in ordered:
            expected = len(dataset.rows(spec.name))
            if counts[spec.name] != expected:
                raise SinkError(
                    f"PostgreSQL table '{spec.name}' has {counts[spec.name]} rows, expected {expected}"
                )
        return counts

    @staticmethod
    def _copy(cur: Any, spec: TableSpec, rows: list[dict[str, Any]]) -> None:
        statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(spec.name),
            sql.SQL(", ").join(sql.Identifier(c) for c in spec.column_names),
        )
        with cur.copy(statement) as copy:
            for row in rows:
                copy.write_row([row[c] for c in spec.column_names])

    def _count(self, specs: list[TableSpec]) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._conn.cursor() as cur:
            for spec in specs:
                cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(spec.name)))
                counts[spec.name] = int(cur.fetchone()[0])
        return counts


def connect_postgres(
    *,
    host: str,
    database: str,
    user: str,
    password: str,
    attempts: int = 24,
    delay: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    connect: Callable[..., Any] = psycopg.connect,
) -> Any:
    """Connect with retries: a new firewall rule takes a short while to take effect."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return connect(
                host=host,
                dbname=database,
                user=user,
                password=password,
                sslmode="require",
                connect_timeout=10,
                autocommit=True,  # PostgresSink opens its own explicit transaction
            )
        except psycopg.OperationalError as exc:
            last = exc
            logger.info("postgres not reachable yet (attempt %d/%d)", attempt, attempts)
            if attempt < attempts:
                sleep(delay)
    detail = str(last).replace(password, "***")
    raise SinkError(f"could not connect to PostgreSQL at {host}: {detail}")


# -- Cosmos DB ------------------------------------------------------------------


def to_document(row: dict[str, Any], id_value: str) -> dict[str, Any]:
    """JSON-safe copy of a row with the Cosmos ``id`` set."""
    doc: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, date):
            doc[key] = value.isoformat()
        elif isinstance(value, Decimal):
            doc[key] = float(value)
        else:
            doc[key] = value
    doc["id"] = id_value
    return doc


class CosmosSink:
    def __init__(self, database: Any, partition_key_factory: Callable[[str], Any]) -> None:
        """``database``: a Cosmos DatabaseProxy; ``partition_key_factory``: path -> PartitionKey."""
        self._db = database
        self._pk = partition_key_factory

    def load(self, specs: list[TableSpec], dataset: Dataset) -> dict[str, int]:
        counts: dict[str, int] = {}
        for spec in specs:
            if not spec.container:
                raise SinkError(f"table '{spec.name}' has no Cosmos container mapping")
            rows = dataset.rows(spec.name)
            try:
                container = self._db.create_container_if_not_exists(
                    id=spec.container, partition_key=self._pk("/id")
                )
                pk_field = self._partition_field(container)
                self._clear(container, pk_field)
                for row in rows:
                    doc = to_document(row, str(row[spec.primary_key]))
                    if pk_field not in doc:
                        raise SinkError(
                            f"container '{spec.container}' is partitioned on /{pk_field}, "
                            f"which '{spec.name}' rows do not have"
                        )
                    container.upsert_item(doc)
                found = list(
                    container.query_items(
                        "SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
                    )
                )[0]
            except SinkError:
                raise
            except Exception as exc:  # noqa: BLE001 - azure SDK error types vary
                raise SinkError(
                    f"Cosmos load of '{spec.container}' failed: {type(exc).__name__}: {exc}"
                ) from exc
            if found != len(rows):
                raise SinkError(
                    f"Cosmos container '{spec.container}' has {found} items, expected {len(rows)}"
                )
            counts[spec.name] = found
        return counts

    @staticmethod
    def _partition_field(container: Any) -> str:
        paths = container.read()["partitionKey"]["paths"]
        return str(paths[0]).lstrip("/")

    @staticmethod
    def _clear(container: Any, pk_field: str) -> None:
        query = f'SELECT c.id, c["{pk_field}"] AS pk FROM c'
        for item in list(container.query_items(query, enable_cross_partition_query=True)):
            container.delete_item(item["id"], partition_key=item.get("pk", item["id"]))
