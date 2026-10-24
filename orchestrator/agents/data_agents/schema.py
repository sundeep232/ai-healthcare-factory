"""Table layout of the synthetic dataset: single source of truth.

The generators, the PostgreSQL DDL, the Cosmos container mapping and the tests all
derive from these specs, so a column can't exist in one place and be missing in another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orchestrator.schemas.requirements import HealthcareDomain

Row = dict[str, Any]


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str  # PostgreSQL type
    nullable: bool = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    domain: HealthcareDomain
    columns: tuple[Column, ...]
    primary_key: str
    # column -> referenced table (always that table's primary key)
    references: dict[str, str] = field(default_factory=dict)
    indexes: tuple[str, ...] = ()
    container: str = ""  # Cosmos container name when this table is stored in Cosmos

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


def _c(name: str, sql: str, nullable: bool = False) -> Column:
    return Column(name, sql, nullable)


TEXT, INT, MONEY, DATE, BOOL, REAL = "TEXT", "INTEGER", "NUMERIC(12,2)", "DATE", "BOOLEAN", "REAL"

_D = HealthcareDomain

TABLES: dict[str, TableSpec] = {
    t.name: t
    for t in (
        TableSpec(
            name="member",
            domain=_D.MEMBER,
            primary_key="member_id",
            columns=(
                _c("member_id", TEXT),
                _c("first_name", TEXT),
                _c("last_name", TEXT),
                _c("date_of_birth", DATE),
                _c("gender", TEXT),
                _c("address_line", TEXT),
                _c("city", TEXT),
                _c("state", TEXT),
                _c("zip_code", TEXT),
                _c("phone", TEXT),
                _c("email", TEXT),
                _c("plan_type", TEXT),
                _c("coverage_effective_date", DATE),
                _c("coverage_end_date", DATE, nullable=True),
                _c("risk_score", REAL),
                _c("primary_condition", TEXT, nullable=True),
            ),
            indexes=("state", "plan_type"),
        ),
        TableSpec(
            name="provider",
            domain=_D.PROVIDER,
            primary_key="provider_id",
            columns=(
                _c("provider_id", TEXT),
                _c("npi", TEXT),
                _c("name", TEXT),
                _c("specialty", TEXT),
                _c("organization", TEXT),
                _c("city", TEXT),
                _c("state", TEXT),
                _c("in_network", BOOL),
                _c("accepting_new_patients", BOOL),
            ),
            indexes=("specialty", "state"),
        ),
        TableSpec(
            name="claim",
            domain=_D.CLAIMS,
            primary_key="claim_id",
            references={"member_id": "member", "provider_id": "provider"},
            columns=(
                _c("claim_id", TEXT),
                _c("member_id", TEXT),
                _c("provider_id", TEXT),
                _c("service_date", DATE),
                _c("adjudication_date", DATE, nullable=True),
                _c("diagnosis_code", TEXT),
                _c("diagnosis_description", TEXT),
                _c("procedure_code", TEXT),
                _c("procedure_description", TEXT),
                _c("place_of_service", TEXT),
                _c("billed_amount", MONEY),
                _c("allowed_amount", MONEY),
                _c("paid_amount", MONEY),
                _c("member_responsibility", MONEY),
                _c("status", TEXT),
                _c("denial_reason", TEXT, nullable=True),
            ),
            indexes=("member_id", "provider_id", "service_date", "status"),
        ),
        TableSpec(
            name="authorization_request",
            domain=_D.AUTHORIZATION,
            primary_key="auth_id",
            references={"member_id": "member", "provider_id": "provider"},
            columns=(
                _c("auth_id", TEXT),
                _c("member_id", TEXT),
                _c("provider_id", TEXT),
                _c("service_category", TEXT),
                _c("procedure_code", TEXT),
                _c("procedure_description", TEXT),
                _c("diagnosis_code", TEXT),
                _c("requested_date", DATE),
                _c("decision_date", DATE, nullable=True),
                _c("urgency", TEXT),
                _c("status", TEXT),
                _c("units_requested", INT),
                _c("units_approved", INT, nullable=True),
                _c("reviewer_type", TEXT, nullable=True),
                _c("denial_reason", TEXT, nullable=True),
            ),
            indexes=("member_id", "provider_id", "status", "requested_date"),
        ),
        TableSpec(
            name="care_plan",
            domain=_D.CARE_MANAGEMENT,
            primary_key="plan_id",
            references={"member_id": "member"},
            container="care_plans",
            columns=(
                _c("plan_id", TEXT),
                _c("member_id", TEXT),
                _c("program", TEXT),
                _c("status", TEXT),
                _c("risk_tier", TEXT),
                _c("start_date", DATE),
                _c("target_end_date", DATE),
                _c("care_manager", TEXT),
                _c("primary_goal", TEXT),
            ),
            indexes=("member_id", "status"),
        ),
        TableSpec(
            name="care_note",
            domain=_D.CARE_MANAGEMENT,
            primary_key="note_id",
            references={"plan_id": "care_plan", "member_id": "member"},
            container="care_notes",
            columns=(
                _c("note_id", TEXT),
                _c("plan_id", TEXT),
                _c("member_id", TEXT),
                _c("note_date", DATE),
                _c("note_type", TEXT),
                _c("author", TEXT),
                _c("text", TEXT),
            ),
            indexes=("plan_id", "member_id"),
        ),
        TableSpec(
            name="timeline_event",
            domain=_D.CARE_MANAGEMENT,
            primary_key="event_id",
            references={"plan_id": "care_plan", "member_id": "member"},
            container="timeline_events",
            columns=(
                _c("event_id", TEXT),
                _c("plan_id", TEXT),
                _c("member_id", TEXT),
                _c("event_date", DATE),
                _c("event_type", TEXT),
                _c("summary", TEXT),
                _c("reference_id", TEXT, nullable=True),
            ),
            indexes=("plan_id", "member_id", "event_date"),
        ),
    )
}


def tables_for(domain: HealthcareDomain) -> list[TableSpec]:
    """Tables a domain produces, in creation order (parents before children)."""
    return [t for t in TABLES.values() if t.domain == domain]
