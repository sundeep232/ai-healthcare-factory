"""Synthetic data agents: determinism, integrity, safety and plausibility invariants."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from orchestrator.agents.data_agents import (
    TABLES,
    Dataset,
    GenerationContext,
    generate_dataset,
    tables_for,
)
from orchestrator.agents.data_agents.reference import CONDITIONS, PROCEDURES
from orchestrator.schemas.requirements import HealthcareDomain as D

TODAY = date(2026, 10, 24)
COUNTS = {D.MEMBER: 400, D.PROVIDER: 20, D.CLAIMS: 1500, D.AUTHORIZATION: 600, D.CARE_MANAGEMENT: 60}


def make_ctx(seed: int = 7, counts: dict[D, int] | None = None, months: int = 12) -> GenerationContext:
    return GenerationContext(seed=seed, today=TODAY, history_months=months, counts=counts or COUNTS)


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return generate_dataset(make_ctx())


def index(ds: Dataset, table: str) -> dict[str, dict]:
    return {r[TABLES[table].primary_key]: r for r in ds.rows(table)}


# -- shape -------------------------------------------------------------------


def test_row_counts_follow_the_plan(ds: Dataset) -> None:
    c = ds.counts()
    assert c["member"] == 400 and c["provider"] == 20
    assert c["claim"] == 1500 and c["authorization_request"] == 600 and c["care_plan"] == 60
    assert c["care_note"] >= 2 * 60 and c["timeline_event"] >= 3 * 60


def test_rows_match_table_specs(ds: Dataset) -> None:
    for name, spec in TABLES.items():
        assert ds.rows(name), name
        for row in ds.rows(name):
            assert set(row) == set(spec.column_names), name
            for col in spec.columns:
                if not col.nullable:
                    assert row[col.name] is not None, (name, col.name)


def test_primary_keys_unique(ds: Dataset) -> None:
    for name, spec in TABLES.items():
        keys = [r[spec.primary_key] for r in ds.rows(name)]
        assert len(keys) == len(set(keys)), name


def test_foreign_keys_resolve(ds: Dataset) -> None:
    for name, spec in TABLES.items():
        for col, parent in spec.references.items():
            valid = {r[TABLES[parent].primary_key] for r in ds.rows(parent)}
            assert {r[col] for r in ds.rows(name)} <= valid, f"{name}.{col}"


def test_every_table_has_a_domain_and_cosmos_container_where_needed() -> None:
    assert {t.domain for t in TABLES.values()} == set(D)
    for t in tables_for(D.CARE_MANAGEMENT):
        assert t.container


# -- determinism -------------------------------------------------------------


def test_same_seed_same_data(ds: Dataset) -> None:
    again = generate_dataset(make_ctx())
    assert again.tables == ds.tables


def test_different_seed_different_data(ds: Dataset) -> None:
    other = generate_dataset(make_ctx(seed=8))
    assert other.tables["member"] != ds.tables["member"]


def test_domains_are_independent_streams(ds: Dataset) -> None:
    # Dropping care management must not change anyone else's data.
    counts = {k: v for k, v in COUNTS.items() if k != D.CARE_MANAGEMENT}
    partial = generate_dataset(make_ctx(counts=counts))
    for table in ("member", "provider", "claim", "authorization_request"):
        assert partial.tables[table] == ds.tables[table]
    assert "care_plan" not in partial.tables


# -- safety: nothing may resemble a real person ------------------------------


def test_identifiers_are_obviously_synthetic(ds: Dataset) -> None:
    assert all(m["member_id"].startswith("SYN-M") for m in ds.rows("member"))
    assert all(m["email"].endswith("@example.invalid") for m in ds.rows("member"))
    assert all(re.fullmatch(r"\(\d{3}\) 555-01\d\d", m["phone"]) for m in ds.rows("member"))
    for p in ds.rows("provider"):
        assert re.fullmatch(r"9\d{9}", p["npi"])  # real NPIs never start with 9


def test_no_ssn_like_or_free_form_phi_columns() -> None:
    names = {c for t in TABLES.values() for c in t.column_names}
    assert not {n for n in names if "ssn" in n or "social" in n or "insurance_id" in n}


# -- plausibility ------------------------------------------------------------


def test_dates_are_consistent(ds: Dataset) -> None:
    members, window_start = index(ds, "member"), make_ctx().window_start
    for c in ds.rows("claim"):
        m = members[c["member_id"]]
        assert window_start <= c["service_date"] < TODAY
        assert c["service_date"] >= m["coverage_effective_date"]
        assert m["coverage_end_date"] is None or c["service_date"] <= m["coverage_end_date"]
        if c["adjudication_date"]:
            assert c["service_date"] < c["adjudication_date"] < TODAY
        else:
            assert c["status"] == "pending"
    for a in ds.rows("authorization_request"):
        m = members[a["member_id"]]
        assert window_start <= a["requested_date"] < TODAY
        assert a["requested_date"] >= m["coverage_effective_date"]
        assert m["coverage_end_date"] is None or a["requested_date"] <= m["coverage_end_date"]
        if a["decision_date"]:
            assert a["requested_date"] <= a["decision_date"] < TODAY
        assert (a["decision_date"] is not None) == (
            a["status"] in {"approved", "denied", "partially_approved"}
        )


def test_money_adds_up(ds: Dataset) -> None:
    for c in ds.rows("claim"):
        assert c["billed_amount"] >= c["allowed_amount"] >= Decimal(0)
        if c["status"] in {"denied", "pending"}:
            assert c["allowed_amount"] == c["paid_amount"] == c["member_responsibility"] == 0
        else:
            assert c["paid_amount"] + c["member_responsibility"] == c["allowed_amount"] > 0
        assert (c["denial_reason"] is not None) == (c["status"] == "denied")


def test_authorization_decisions_make_sense(ds: Dataset) -> None:
    for a in ds.rows("authorization_request"):
        assert PROCEDURES[a["procedure_code"]].needs_auth
        assert (a["denial_reason"] is not None) == (a["status"] == "denied")
        if a["status"] == "approved":
            assert a["units_approved"] == a["units_requested"]
        elif a["status"] == "denied":
            assert a["units_approved"] == 0 and a["reviewer_type"] == "medical director"
        elif a["status"] == "partially_approved":
            assert 0 < a["units_approved"] < a["units_requested"]
        else:
            assert a["units_approved"] is None


def test_clinical_coherence(ds: Dataset) -> None:
    members = index(ds, "member")
    by_code = {c.code: c for c in CONDITIONS}
    for row in ds.rows("claim") + ds.rows("authorization_request"):
        cond, m = by_code[row["diagnosis_code"]], members[row["member_id"]]
        when = row.get("service_date") or row["requested_date"]
        dob = m["date_of_birth"]
        age = when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))
        assert cond.min_age <= age <= cond.max_age, (cond.code, age)
        assert cond.sex in (None, m["gender"]), cond.code
        assert row["procedure_code"] in cond.procedures


def test_providers_match_the_diagnosis_specialty_when_available(ds: Dataset) -> None:
    providers, by_code = index(ds, "provider"), {c.code: c for c in CONDITIONS}
    present = {p["specialty"] for p in providers.values()}
    for c in ds.rows("claim"):
        cond = by_code[c["diagnosis_code"]]
        if present & set(cond.specialties):
            assert providers[c["provider_id"]]["specialty"] in cond.specialties


def test_care_management_ties_back_to_real_activity(ds: Dataset) -> None:
    plans, auths, claims = index(ds, "care_plan"), index(ds, "authorization_request"), index(ds, "claim")
    refs = [e for e in ds.rows("timeline_event") if e["reference_id"]]
    assert refs, "expected some events linked to auths or claims"
    for e in refs:
        target = auths if e["event_type"] == "authorization_decision" else claims
        assert target[e["reference_id"]]["member_id"] == e["member_id"]
    for p in plans.values():
        assert p["target_end_date"] >= p["start_date"]
    for e in ds.rows("timeline_event"):
        assert plans[e["plan_id"]]["start_date"] <= e["event_date"] <= TODAY
        assert plans[e["plan_id"]]["member_id"] == e["member_id"]
    for n in ds.rows("care_note"):
        assert plans[n["plan_id"]]["start_date"] <= n["note_date"] <= TODAY


def test_demographics_are_plausible(ds: Dataset) -> None:
    ages = []
    for m in ds.rows("member"):
        age = (TODAY - m["date_of_birth"]).days // 365
        ages.append(age)
        assert 0 <= age <= 93
        if m["plan_type"] == "Medicare Advantage":
            assert age >= 65
        else:
            assert age <= 64
    assert 25 <= sum(ages) / len(ages) <= 55
    assert {m["gender"] for m in ds.rows("member")} == {"F", "M"}


# -- edge cases --------------------------------------------------------------


def test_minimal_counts_work() -> None:
    counts = {D.MEMBER: 100, D.PROVIDER: 1, D.CLAIMS: 10, D.AUTHORIZATION: 10, D.CARE_MANAGEMENT: 5}
    small = generate_dataset(make_ctx(counts=counts, months=1))
    assert len(small.rows("claim")) == 10 and len(small.rows("provider")) == 1


def test_more_care_plans_than_members_is_allowed() -> None:
    counts = {D.MEMBER: 100, D.PROVIDER: 5, D.CARE_MANAGEMENT: 150}
    out = generate_dataset(make_ctx(counts=counts))
    assert len(out.rows("care_plan")) == 150
    assert len(index(out, "care_plan")) == 150


def test_subset_of_domains_only_generates_those() -> None:
    out = generate_dataset(make_ctx(counts={D.MEMBER: 100, D.PROVIDER: 10}))
    assert set(out.tables) == {"member", "provider"}


def test_claims_without_members_fails_clearly() -> None:
    with pytest.raises(ValueError, match="members and providers"):
        generate_dataset(make_ctx(counts={D.CLAIMS: 10}))


def test_history_window_is_respected_for_long_windows() -> None:
    out = generate_dataset(make_ctx(counts=COUNTS, months=36))
    earliest = min(c["service_date"] for c in out.rows("claim"))
    assert earliest < TODAY - timedelta(days=24 * 30)
