"""Shared types and helpers for the synthetic-data agents."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, TypeVar

from orchestrator.agents.data_agents.reference import CONDITIONS, Condition
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

T = TypeVar("T")

DAYS_PER_MONTH = 30


@dataclass(frozen=True)
class GenerationContext:
    """Everything that makes a dataset reproducible."""

    seed: int
    today: date
    history_months: int
    counts: Mapping[HealthcareDomain, int]  # primary-entity count per domain

    @property
    def window_start(self) -> date:
        return self.today - timedelta(days=self.history_months * DAYS_PER_MONTH)

    def rng(self, domain: HealthcareDomain) -> random.Random:
        """Independent stream per domain: adding a domain never reshuffles the others."""
        return random.Random(f"{self.seed}:{domain.value}")


@dataclass
class Dataset:
    """Generated rows by table name."""

    tables: dict[str, list[Row]] = field(default_factory=dict)

    def rows(self, table: str) -> list[Row]:
        return self.tables.get(table, [])

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


class DataAgent(Protocol):
    """One agent per healthcare domain."""

    domain: HealthcareDomain

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        """Produce this domain's tables, using ``upstream`` for referential integrity."""
        ...


# -- helpers -----------------------------------------------------------------


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pick_weighted(rng: random.Random, options: Sequence[tuple[T, float]]) -> T:
    items = [o for o, _ in options]
    return rng.choices(items, weights=[w for _, w in options], k=1)[0]


def random_date(rng: random.Random, start: date, end: date) -> date:
    if end < start:
        raise ValueError(f"empty date range {start}..{end}")
    return start + timedelta(days=rng.randint(0, (end - start).days))


def age_on(dob: date, when: date) -> int:
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def active_range(member: Row, ctx: GenerationContext) -> tuple[date, date]:
    """Dates on which the member was covered and inside the history window."""
    start = max(ctx.window_start, member["coverage_effective_date"])
    end = member["coverage_end_date"] or (ctx.today - timedelta(days=1))
    return start, min(end, ctx.today - timedelta(days=1))


def eligible_conditions(age: int, sex: str, age_to: int | None = None) -> list[Condition]:
    """Conditions valid for someone aged ``age`` (through ``age_to`` if a span is given)."""
    oldest = age if age_to is None else age_to
    return [
        c
        for c in CONDITIONS
        if c.min_age <= age and oldest <= c.max_age and (c.sex is None or c.sex == sex)
    ]


def weighted_sample_without_replacement(
    rng: random.Random, items: Sequence[T], weights: Sequence[float], k: int
) -> list[T]:
    """Efraimidis-Spirakis: heavier items are likelier to be chosen, none twice."""
    keyed = sorted(
        ((rng.random() ** (1.0 / max(w, 1e-9)), i) for i, w in enumerate(weights)), reverse=True
    )
    return [items[i] for _, i in keyed[:k]]
