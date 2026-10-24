"""Member data agent: fictional health-plan members."""

from __future__ import annotations

from datetime import timedelta

from orchestrator.agents.data_agents.base import (
    Dataset,
    GenerationContext,
    age_on,
    eligible_conditions,
    pick_weighted,
    random_date,
)
from orchestrator.agents.data_agents.reference import (
    CITIES,
    FIRST_NAMES_F,
    FIRST_NAMES_M,
    LAST_NAMES,
    PLAN_TYPES,
    STREETS,
)
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

# Real area codes for the covered cities' region, combined with the 555-01XX range that
# is reserved for fictional use, so no generated phone number can reach a real person.
AREA_CODES = ("816", "402", "515", "316", "612", "314", "918", "405", "501", "214", "512", "303")


class MemberAgent:
    domain = HealthcareDomain.MEMBER

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        rng = ctx.rng(self.domain)
        n = ctx.counts[self.domain]
        rows: list[Row] = []
        for i in range(1, n + 1):
            plan = pick_weighted(rng, PLAN_TYPES)
            sex = "F" if rng.random() < 0.52 else "M"
            first = rng.choice(FIRST_NAMES_F if sex == "F" else FIRST_NAMES_M)
            last = rng.choice(LAST_NAMES)

            if plan == "Medicare Advantage":
                age = rng.randint(65, 92)
            elif plan == "Medicaid Managed Care":
                age = min(64, int(rng.triangular(0, 64, 22)))
            else:
                age = min(64, int(rng.triangular(0, 64, 42)))
            dob = ctx.today - timedelta(days=age * 365 + rng.randint(0, 364))
            age = age_on(dob, ctx.today)

            city, state, zip_prefix = rng.choice(CITIES)
            effective = ctx.today - timedelta(
                days=rng.randint(45, ctx.history_months * 30 + 3 * 365)
            )
            end = None
            if rng.random() < 0.07:  # a few members leave during the window
                earliest = max(ctx.window_start, effective) + timedelta(days=30)
                latest = ctx.today - timedelta(days=15)
                if earliest <= latest:
                    end = random_date(rng, earliest, latest)

            chronic = [c for c in eligible_conditions(age, sex) if c.chronic]
            chance = 0.8 if age >= 65 else 0.45
            condition = None
            if chronic and rng.random() < chance:
                condition = rng.choices(chronic, weights=[c.weight for c in chronic], k=1)[0]

            risk = 0.55 + age / 100 + (0.9 if condition else 0.0) + rng.uniform(-0.2, 0.45)
            rows.append(
                {
                    "member_id": f"SYN-M{i:06d}",
                    "first_name": first,
                    "last_name": last,
                    "date_of_birth": dob,
                    "gender": sex,
                    "address_line": f"{rng.randint(100, 9899)} {rng.choice(STREETS)}",
                    "city": city,
                    "state": state,
                    "zip_code": f"{zip_prefix}{rng.randint(0, 99):02d}",
                    "phone": f"({rng.choice(AREA_CODES)}) 555-01{rng.randint(0, 99):02d}",
                    # .invalid is reserved (RFC 2606): can never be a real mailbox.
                    "email": f"{first}.{last}.{i}@example.invalid".lower(),
                    "plan_type": plan,
                    "coverage_effective_date": effective,
                    "coverage_end_date": end,
                    "risk_score": round(max(0.2, risk), 2),
                    "primary_condition": condition.code if condition else None,
                }
            )
        return {"member": rows}
