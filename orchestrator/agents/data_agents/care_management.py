"""Care Management data agent: care plans, notes and a per-plan timeline."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from orchestrator.agents.data_agents.base import (
    Dataset,
    GenerationContext,
    pick_weighted,
    random_date,
    weighted_sample_without_replacement,
)
from orchestrator.agents.data_agents.reference import (
    CARE_MANAGERS,
    CARE_PROGRAM_FALLBACK,
    CARE_PROGRAMS,
    NOTE_TEMPLATES,
    TIMELINE_ENTRIES,
)
from orchestrator.agents.data_agents.schema import Row
from orchestrator.schemas.requirements import HealthcareDomain

_STATUS = (("active", 62), ("completed", 24), ("closed", 14))
_NOTE_TYPES = tuple(NOTE_TEMPLATES)
_PROGRAM_BY_CONDITION = {code: (name, goal) for name, codes, goal in CARE_PROGRAMS for code in codes}
_PROGRAM_GOALS = {name: goal for name, _, goal in CARE_PROGRAMS}
_PROGRAM_WEIGHTS = tuple((name, 1.0) for name, _, _ in CARE_PROGRAMS)


def _tier(risk: float) -> str:
    return "high" if risk >= 2.0 else "medium" if risk >= 1.2 else "low"


class CareManagementAgent:
    domain = HealthcareDomain.CARE_MANAGEMENT

    def generate(self, ctx: GenerationContext, upstream: Dataset) -> dict[str, list[Row]]:
        rng = ctx.rng(self.domain)
        members = upstream.rows("member")
        if not members:
            raise ValueError("care management needs members")

        # Optional enrichment: tie timeline events to the member's real auths and claims.
        auths: dict[str, list[Row]] = defaultdict(list)
        for a in upstream.rows("authorization_request"):
            auths[a["member_id"]].append(a)
        claims: dict[str, list[Row]] = defaultdict(list)
        for c in upstream.rows("claim"):
            claims[c["member_id"]].append(c)

        n = ctx.counts[self.domain]
        # Higher-risk members are likelier to be enrolled. More plans than members is allowed
        # (a member can have several programs over time): sample everyone, then repeat.
        weights = [float(m["risk_score"]) ** 2 for m in members]
        chosen = weighted_sample_without_replacement(rng, members, weights, min(n, len(members)))
        while len(chosen) < n:
            chosen.append(rng.choice(members))

        plans: list[Row] = []
        notes: list[Row] = []
        events: list[Row] = []
        for idx, member in enumerate(chosen, start=1):
            plan_id = f"SYN-CP{idx:05d}"
            program, goal = _PROGRAM_BY_CONDITION.get(member["primary_condition"] or "", (None, ""))
            if program is None:
                program = (
                    pick_weighted(rng, _PROGRAM_WEIGHTS)
                    if rng.random() < 0.7
                    else CARE_PROGRAM_FALLBACK
                )
                goal = _PROGRAM_GOALS.get(
                    program, "Coordinate care across providers and close identified gaps"
                )

            lo = max(ctx.window_start, member["coverage_effective_date"])
            hi = ctx.today - timedelta(days=14)
            start = random_date(rng, min(lo, hi), hi)
            target_end = start + timedelta(days=rng.choice((90, 120, 180)))
            status = pick_weighted(rng, _STATUS)
            if status == "completed":
                if start > ctx.today - timedelta(days=60):
                    status = "active"  # too new to have finished
                else:
                    target_end = min(target_end, ctx.today - timedelta(days=1))
            plans.append(
                {
                    "plan_id": plan_id,
                    "member_id": member["member_id"],
                    "program": program,
                    "status": status,
                    "risk_tier": _tier(float(member["risk_score"])),
                    "start_date": start,
                    "target_end_date": target_end,
                    "care_manager": rng.choice(CARE_MANAGERS),
                    "primary_goal": goal,
                }
            )
            manager = plans[-1]["care_manager"]
            last_day = min(ctx.today - timedelta(days=1), target_end)
            last_day = max(last_day, start)

            # Notes: first contact is always outreach, the rest vary.
            for j in range(rng.randint(2, 5)):
                kind = "Outreach call" if j == 0 else rng.choice(_NOTE_TYPES)
                note_date = start if j == 0 else random_date(rng, start, last_day)
                notes.append(
                    {
                        "plan_id": plan_id,
                        "member_id": member["member_id"],
                        "note_date": note_date,
                        "note_type": kind,
                        "author": manager,
                        "text": rng.choice(NOTE_TEMPLATES[kind]),
                    }
                )

            # Timeline: enrolment, milestones, plus the member's own auth/claim activity.
            def event(when: date, kind: str, ref: str | None = None, *, _plan: str = plan_id,
                      _member: str = member["member_id"]) -> None:
                events.append(
                    {
                        "plan_id": _plan,
                        "member_id": _member,
                        "event_date": when,
                        "event_type": kind,
                        "summary": TIMELINE_ENTRIES[kind],
                        "reference_id": ref,
                    }
                )

            event(start, "enrolled")
            event(min(start + timedelta(days=rng.randint(1, 7)), last_day), "assessment_completed")
            event(random_date(rng, start, last_day), "care_plan_review")
            if status == "completed":
                event(last_day, "goal_milestone")
            for a in [a for a in auths[member["member_id"]] if a["decision_date"]
                      and start <= a["decision_date"] <= ctx.today][:2]:
                event(a["decision_date"], "authorization_decision", a["auth_id"])
            for c in [c for c in claims[member["member_id"]] if c["adjudication_date"]
                      and start <= c["adjudication_date"] <= ctx.today][:2]:
                event(c["adjudication_date"], "claim_received", c["claim_id"])

        events.sort(key=lambda e: (e["event_date"], e["plan_id"], e["event_type"]))
        notes.sort(key=lambda r: (r["note_date"], r["plan_id"]))
        return {
            "care_plan": plans,
            "care_note": [{"note_id": f"SYN-N{i:06d}", **r} for i, r in enumerate(notes, 1)],
            "timeline_event": [{"event_id": f"SYN-E{i:06d}", **r} for i, r in enumerate(events, 1)],
        }
