"""Provider data agent: fictional clinicians and practices."""

from __future__ import annotations

from orchestrator.agents.data_agents.base import Dataset, GenerationContext
from orchestrator.agents.data_agents.reference import (
    CITIES,
    FIRST_NAMES_F,
    FIRST_NAMES_M,
    LAST_NAMES,
    ORG_PREFIXES,
    ORG_SUFFIX_BY_SPECIALTY,
    SPECIALTIES,
    SPECIALTY_WEIGHTS,
)
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

_CREDENTIALS = {
    "Behavioral Health": ("PhD", "LCSW", "PsyD"),
    "Physical Medicine": ("MD", "DO", "DPT"),
}


class ProviderAgent:
    domain = HealthcareDomain.PROVIDER

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        rng = ctx.rng(self.domain)
        n = ctx.counts[self.domain]
        # The most common specialties each get a provider first, so even a tiny provider
        # list can serve the claims and authorizations that follow.
        by_weight = [s for _, s in sorted(zip(SPECIALTY_WEIGHTS, SPECIALTIES), reverse=True)]

        used_npis: set[str] = set()
        rows: list[Row] = []
        for i in range(1, n + 1):
            specialty = (
                by_weight[i - 1]
                if i <= len(by_weight)
                else rng.choices(SPECIALTIES, weights=SPECIALTY_WEIGHTS, k=1)[0]
            )
            # Real NPIs never begin with 9, so these cannot collide with a real provider.
            npi = f"9{rng.randrange(10**9):09d}"
            while npi in used_npis:
                npi = f"9{rng.randrange(10**9):09d}"
            used_npis.add(npi)

            first = rng.choice(FIRST_NAMES_F + FIRST_NAMES_M)
            last = rng.choice(LAST_NAMES)
            credential = rng.choice(_CREDENTIALS.get(specialty, ("MD", "MD", "DO", "NP")))
            city, state, _ = rng.choice(CITIES)
            rows.append(
                {
                    "provider_id": f"SYN-P{i:05d}",
                    "npi": npi,
                    "name": f"{first} {last}, {credential}",
                    "specialty": specialty,
                    "organization": f"{rng.choice(ORG_PREFIXES)} {ORG_SUFFIX_BY_SPECIALTY[specialty]}",
                    "city": city,
                    "state": state,
                    "in_network": rng.random() < 0.88,
                    "accepting_new_patients": rng.random() < 0.8,
                }
            )
        return {"provider": rows}
