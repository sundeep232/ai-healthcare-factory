"""Claims data agent: adjudicated medical claims tied to real members and providers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from orchestrator.agents.data_agents.base import (
    Dataset,
    GenerationContext,
    money,
    pick_weighted,
    random_date,
)
from orchestrator.agents.data_agents.encounter import EncounterPicker
from orchestrator.agents.data_agents.reference import CLAIM_DENIAL_REASONS
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

_STATUS = (("paid", 84), ("denied", 9), ("pending", 4), ("adjusted", 3))
# Fixed copays by place of service; remainder of member cost share is coinsurance.
_COPAY = {"Office": 25.0, "Emergency Room": 250.0, "Outpatient Hospital": 75.0}
_PLAN_COINSURANCE = {
    "HMO": 0.10, "PPO": 0.20, "EPO": 0.15, "Medicare Advantage": 0.15, "Medicaid Managed Care": 0.0,
}


class ClaimsAgent:
    domain = HealthcareDomain.CLAIMS

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        rng = ctx.rng(self.domain)
        picker = EncounterPicker(upstream.rows("member"), upstream.rows("provider"), ctx)

        drafts: list[Row] = []
        for _ in range(ctx.counts[self.domain]):
            enc = picker.pick(rng)
            proc, member, provider = enc.procedure, enc.member, enc.provider
            service = random_date(rng, *enc.window)

            allowed_full = proc.allowed * rng.uniform(0.85, 1.25)
            if not provider["in_network"]:
                allowed_full *= 0.65
            billed = allowed_full * rng.uniform(1.6, 3.2)

            status = pick_weighted(rng, _STATUS)
            adjudicated = service + timedelta(days=rng.randint(3, 35))
            if adjudicated >= ctx.today:  # too recent to have been decided
                status, adjudicated = "pending", None

            denial = None
            allowed = paid = responsibility = Decimal(0)
            if status == "denied":
                adjudicated = adjudicated or service + timedelta(days=3)
                if proc.needs_auth and rng.random() < 0.5:
                    denial = "Missing or invalid prior authorization"
                elif not provider["in_network"] and rng.random() < 0.5:
                    denial = "Out-of-network provider"
                else:
                    denial = rng.choice(CLAIM_DENIAL_REASONS)
            elif status != "pending":
                allowed = money(allowed_full * (rng.uniform(0.9, 1.0) if status == "adjusted" else 1.0))
                coinsurance = _PLAN_COINSURANCE[member["plan_type"]]
                responsibility = min(
                    allowed,
                    money(
                        _COPAY.get(proc.place_of_service, 0.0)
                        + float(allowed) * coinsurance * rng.random()
                    ),
                )
                paid = allowed - responsibility  # exact: both are already cents

            drafts.append(
                {
                    "member_id": member["member_id"],
                    "provider_id": provider["provider_id"],
                    "service_date": service,
                    "adjudication_date": adjudicated,
                    "diagnosis_code": enc.condition.code,
                    "diagnosis_description": enc.condition.description,
                    "procedure_code": proc.code,
                    "procedure_description": proc.description,
                    "place_of_service": proc.place_of_service,
                    "billed_amount": money(billed),
                    "allowed_amount": allowed,
                    "paid_amount": paid,
                    "member_responsibility": responsibility,
                    "status": status,
                    "denial_reason": denial,
                }
            )

        # Chronological ids make the data feel like a real feed.
        drafts.sort(key=lambda r: (r["service_date"], r["member_id"], r["procedure_code"]))
        rows = [{"claim_id": f"SYN-C{i:07d}", **row} for i, row in enumerate(drafts, start=1)]
        return {"claim": rows}
