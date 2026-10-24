"""Authorization data agent: prior-authorization requests and their decisions."""

from __future__ import annotations

import random
from datetime import date, timedelta

from orchestrator.agents.data_agents.base import (
    Dataset,
    GenerationContext,
    pick_weighted,
    random_date,
)
from orchestrator.agents.data_agents.encounter import EncounterPicker
from orchestrator.agents.data_agents.reference import AUTH_DENIAL_REASONS
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

_URGENCY = (("standard", 86), ("expedited", 12), ("retrospective", 2))
_STATUS = (
    ("approved", 66), ("denied", 13), ("partially_approved", 6),
    ("pending", 7), ("in_review", 4), ("withdrawn", 4),
)
# Turnaround in days (min, max) by urgency.
_TURNAROUND = {"standard": (2, 14), "expedited": (0, 3), "retrospective": (5, 20)}
_DECIDED = {"approved", "denied", "partially_approved"}


def _units_requested(rng: random.Random, category: str) -> int:
    if category == "Physical Therapy":
        return rng.randint(6, 24)
    if category == "Specialty Drug":
        return rng.randint(1, 12)
    if category == "Inpatient Admission":
        return rng.randint(1, 7)  # days
    return 1


class AuthorizationAgent:
    domain = HealthcareDomain.AUTHORIZATION

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        rng = ctx.rng(self.domain)
        picker = EncounterPicker(upstream.rows("member"), upstream.rows("provider"), ctx)

        drafts: list[Row] = []
        for _ in range(ctx.counts[self.domain]):
            enc = picker.pick(rng, needs_auth=True)
            proc = enc.procedure
            requested = random_date(rng, *enc.window)
            urgency = pick_weighted(rng, _URGENCY)
            status = pick_weighted(rng, _STATUS)

            low, high = _TURNAROUND[urgency]
            decided_on = requested + timedelta(days=rng.randint(low, high))
            if status in _DECIDED and decided_on >= ctx.today:
                status = rng.choice(("pending", "in_review"))  # not decided yet
            decision: date | None = decided_on if status in _DECIDED else None

            units = _units_requested(rng, proc.category)
            approved_units: int | None = None
            reviewer = denial = None
            if status == "approved":
                approved_units = units
                reviewer = "auto-approval" if rng.random() < 0.45 else "nurse reviewer"
            elif status == "partially_approved":
                approved_units = max(1, int(units * rng.uniform(0.4, 0.85)))
                if approved_units >= units:  # single-unit requests can't be partial
                    status, approved_units = "approved", units
                reviewer = "nurse reviewer"
            elif status == "denied":
                approved_units = 0
                reviewer = "medical director"
                denial = rng.choice(AUTH_DENIAL_REASONS)
            elif status == "in_review":
                reviewer = "nurse reviewer"

            drafts.append(
                {
                    "member_id": enc.member["member_id"],
                    "provider_id": enc.provider["provider_id"],
                    "service_category": proc.category,
                    "procedure_code": proc.code,
                    "procedure_description": proc.description,
                    "diagnosis_code": enc.condition.code,
                    "requested_date": requested,
                    "decision_date": decision,
                    "urgency": urgency,
                    "status": status,
                    "units_requested": units,
                    "units_approved": approved_units,
                    "reviewer_type": reviewer,
                    "denial_reason": denial,
                }
            )

        drafts.sort(key=lambda r: (r["requested_date"], r["member_id"], r["procedure_code"]))
        rows = [{"auth_id": f"SYN-A{i:06d}", **row} for i, row in enumerate(drafts, start=1)]
        return {"authorization_request": rows}
