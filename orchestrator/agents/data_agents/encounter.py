"""Clinically plausible (member, diagnosis, procedure, provider) selection.

Claims and authorizations share this so that, for example, a knee replacement is only
requested for an adult with a knee diagnosis, from an orthopedic provider.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from itertools import accumulate

from orchestrator.agents.data_agents.base import (
    GenerationContext,
    active_range,
    age_on,
    eligible_conditions,
)
from orchestrator.agents.data_agents.reference import CONDITIONS, PROCEDURES, Condition, Procedure
from orchestrator.agents.data_agents.schema import Row

_CONDITION_BY_CODE = {c.code: c for c in CONDITIONS}


@dataclass(frozen=True)
class Encounter:
    member: Row
    provider: Row
    condition: Condition
    procedure: Procedure
    window: tuple[date, date]  # dates on which the member could receive this service


class EncounterPicker:
    def __init__(self, members: list[Row], providers: list[Row], ctx: GenerationContext) -> None:
        if not members or not providers:
            raise ValueError("members and providers are required to build encounters")
        self._ctx = ctx
        self._members = members
        # Sicker members use more care: weight selection by risk score.
        self._cum_weights = list(accumulate(float(m["risk_score"]) for m in members))
        self._by_specialty: dict[str, list[Row]] = {}
        for p in providers:
            self._by_specialty.setdefault(p["specialty"], []).append(p)
        self._providers = providers

    def pick(self, rng: random.Random, *, needs_auth: bool = False) -> Encounter:
        """Draw one encounter. With ``needs_auth`` only prior-auth procedures are used."""
        for _ in range(25):
            member = rng.choices(self._members, cum_weights=self._cum_weights, k=1)[0]
            window = active_range(member, self._ctx)
            # The service date is anywhere in the window, so the diagnosis must suit the
            # member's age at both ends of it.
            dob = member["date_of_birth"]
            conditions = eligible_conditions(
                age_on(dob, window[0]), member["gender"], age_on(dob, window[1])
            )
            if needs_auth:  # only diagnoses that have something requiring authorization
                conditions = [
                    c for c in conditions if any(PROCEDURES[p].needs_auth for p in c.procedures)
                ]
            if not conditions:
                continue  # e.g. a young child: redraw another member

            own = _CONDITION_BY_CODE.get(member["primary_condition"] or "")
            if own is not None and own in conditions and rng.random() < 0.6:
                condition = own
            else:
                condition = rng.choices(conditions, weights=[c.weight for c in conditions], k=1)[0]

            codes = [
                code
                for code in condition.procedures
                if not needs_auth or PROCEDURES[code].needs_auth
            ]
            procedure = PROCEDURES[rng.choice(codes)]
            return Encounter(
                member=member,
                provider=self._provider_for(rng, condition),
                condition=condition,
                procedure=procedure,
                window=window,
            )
        raise RuntimeError("could not build a plausible encounter (check reference data)")

    def _provider_for(self, rng: random.Random, condition: Condition) -> Row:
        specialty = rng.choice(condition.specialties)
        pool = self._by_specialty.get(specialty)
        if not pool:  # small provider lists may lack this specialty: any listed specialty, else anyone
            pool = next(
                (self._by_specialty[s] for s in condition.specialties if s in self._by_specialty),
                self._providers,
            )
        in_network = [p for p in pool if p["in_network"]]
        # Mostly in-network, occasionally out-of-network (which produces realistic denials).
        if in_network and rng.random() < 0.92:
            return rng.choice(in_network)
        return rng.choice(pool)
