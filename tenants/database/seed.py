"""Create the payer tables and load synthetic rows into the tenant database."""

import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")

PLANS = [
    ("plan-hmo-01", "Synthetic HMO", "HMO"),
    ("plan-ppo-01", "Synthetic PPO", "PPO"),
    ("plan-epo-01", "Synthetic EPO", "EPO"),
    ("plan-pos-01", "Synthetic POS", "POS"),
]
DIAGNOSES = [
    ("E11.9", "Type 2 diabetes mellitus without complications", "ICD-10"),
    ("I10", "Essential hypertension", "ICD-10"),
    ("J45.909", "Unspecified asthma, uncomplicated", "ICD-10"),
    ("M54.5", "Low back pain", "ICD-10"),
    ("E78.5", "Hyperlipidemia, unspecified", "ICD-10"),
    ("J06.9", "Acute upper respiratory infection", "ICD-10"),
    ("N39.0", "Urinary tract infection", "ICD-10"),
    ("K21.0", "Gastro-esophageal reflux with esophagitis", "ICD-10"),
    ("F41.1", "Generalized anxiety disorder", "ICD-10"),
    ("M17.11", "Unilateral primary osteoarthritis, right knee", "ICD-10"),
    ("Z00.00", "General adult medical exam", "ICD-10"),
    ("R07.9", "Chest pain, unspecified", "ICD-10"),
]
PROCEDURES = [
    ("99213", "Office visit, established patient, low complexity", "CPT"),
    ("99214", "Office visit, established patient, moderate complexity", "CPT"),
    ("99203", "Office visit, new patient, low complexity", "CPT"),
    ("80053", "Comprehensive metabolic panel", "CPT"),
    ("85025", "Complete blood count", "CPT"),
    ("93000", "Electrocardiogram", "CPT"),
    ("71046", "Chest x-ray, two views", "CPT"),
    ("36415", "Routine venipuncture", "CPT"),
    ("90471", "Immunization administration", "CPT"),
    ("73721", "MRI, any joint of lower extremity", "CPT"),
    ("43239", "Upper GI endoscopy with biopsy", "CPT"),
    ("27447", "Total knee arthroplasty", "CPT"),
]
SPECIALTIES = [
    ("spec-pcp", "Family Medicine"),
    ("spec-im", "Internal Medicine"),
    ("spec-card", "Cardiology"),
    ("spec-endo", "Endocrinology"),
    ("spec-ortho", "Orthopedics"),
    ("spec-pul", "Pulmonology"),
    ("spec-gi", "Gastroenterology"),
    ("spec-bh", "Behavioral Health"),
]
PROGRAMS = [
    ("prog-dm", "Diabetes management"),
    ("prog-chf", "Heart failure"),
    ("prog-asthma", "Asthma"),
    ("prog-msk", "Musculoskeletal"),
]
FIRST_NAMES = ["Avery", "Blake", "Casey", "Drew", "Eden", "Finley", "Gray", "Harper", "Indigo", "Jordan", "Kai", "Logan", "Morgan", "Noah", "Parker", "Quinn", "Riley", "Sage", "Taylor", "Winter"]
LAST_NAMES = ["Adler", "Brooks", "Chen", "Diaz", "Ellis", "Foster", "Garcia", "Hughes", "Ibarra", "Johnson", "Khan", "Lopez", "Murphy", "Nguyen", "Owens", "Patel", "Reed", "Shah", "Torres", "Walsh"]
CITIES = [("Austin", "TX", "78701"), ("Dallas", "TX", "75201"), ("Phoenix", "AZ", "85001"), ("Columbus", "OH", "43215"), ("Denver", "CO", "80202"), ("Atlanta", "GA", "30303")]
PLACES = ["11 Office", "21 Inpatient", "22 Outpatient", "23 Emergency"]
SERVICE_TYPES = ["Office visit", "Imaging", "Outpatient surgery", "Specialty consult", "Therapy"]
PROVIDER_TYPES = ["Physician", "Nurse practitioner", "Physician assistant", "Facility"]
TAXONOMIES = ["207Q00000X", "207R00000X", "207RC0000X", "207RE0101X", "207X00000X", "207RP1001X", "207RG0100X", "2084P0800X"]


def _statements() -> list[str]:
    text = SCHEMA.read_text(encoding="utf-8")
    return [part.strip() for part in text.split("\nGO\n") if part.strip()]


def build(member_count: int, rng: random.Random) -> dict[str, list[tuple]]:
    created = datetime(2026, 1, 15, 12, 0, 0)
    provider_count = min(80, max(12, member_count // 20))
    plans = [(*plan, created) for plan in PLANS]
    diagnoses = list(DIAGNOSES)
    procedures = list(PROCEDURES)
    specialties = list(SPECIALTIES)
    programs = list(PROGRAMS)
    providers = []
    for index in range(provider_count):
        specialty = specialties[index % len(specialties)][1]
        city, state, zip_code = CITIES[index % len(CITIES)]
        providers.append((
            f"PRV{index + 1:05d}",
            f"9{index + 1:09d}",
            f"Synthetic {specialty} Group {index + 1}",
            PROVIDER_TYPES[index % len(PROVIDER_TYPES)],
            specialty,
            f"555-010-{index % 10000:04d}",
            f"{100 + index} Demo Street",
            None,
            city,
            state,
            zip_code,
            TAXONOMIES[index % len(TAXONOMIES)],
            created,
        ))
    members = []
    for index in range(member_count):
        city, state, zip_code = CITIES[index % len(CITIES)]
        birth = date(1948, 1, 1) + timedelta(days=rng.randrange(0, 20000))
        effective = date(2025, 1, 1) + timedelta(days=rng.randrange(0, 300))
        terminated = rng.random() < 0.05
        members.append((
            f"MBR{index + 1:06d}",
            f"SYN{100000 + index}",
            FIRST_NAMES[index % len(FIRST_NAMES)],
            LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)],
            birth,
            rng.choice(["F", "M", "X"]),
            f"{200 + (index % 800)} Sample Ave",
            f"Apt {index % 40}" if index % 4 == 0 else None,
            city,
            state,
            zip_code,
            f"555-200-{index % 10000:04d}",
            f"member{index + 1}@example.test",
            plans[index % len(plans)][0],
            effective,
            effective + timedelta(days=180) if terminated else None,
            created,
        ))
    authorizations = []
    auth_for_member: dict[str, list[str]] = {}
    auth_index = 0
    for member in members:
        if rng.random() > 0.4:
            continue
        provider = providers[rng.randrange(len(providers))]
        request = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 200))
        status = rng.choice(["Approved", "Approved", "Pending", "Denied"])
        approval = request + timedelta(days=rng.randrange(1, 8)) if status == "Approved" else None
        auth_id = f"AUT{auth_index + 1:06d}"
        auth_index += 1
        authorizations.append((
            auth_id,
            member[0],
            provider[0],
            f"PA{auth_index:07d}",
            rng.choice(SERVICE_TYPES),
            status,
            request,
            approval,
            request + timedelta(days=3),
            request + timedelta(days=90),
            rng.choice(diagnoses)[0],
            rng.choice(procedures)[0],
            rng.randrange(1, 12),
            created,
        ))
        auth_for_member.setdefault(member[0], []).append(auth_id)
    claims = []
    claim_index = 0
    for member in members:
        for _ in range(rng.choice([1, 2, 2, 3])):
            provider = providers[rng.randrange(len(providers))]
            service = date(2026, 2, 1) + timedelta(days=rng.randrange(0, 180))
            billed = Decimal(rng.randrange(80, 4500))
            allowed = (billed * Decimal(rng.choice(["0.55", "0.70", "0.85"]))).quantize(Decimal("0.01"))
            status = rng.choice(["Paid", "Paid", "Pending", "Denied", "Adjusted"])
            paid = allowed if status == "Paid" else (allowed * Decimal("0.80")).quantize(Decimal("0.01")) if status == "Adjusted" else Decimal("0.00")
            linked = auth_for_member.get(member[0], [])
            authorization_id = linked[0] if linked and rng.random() < 0.5 else None
            claims.append((
                f"CLM{claim_index + 1:07d}",
                member[0],
                provider[0],
                authorization_id,
                f"C{claim_index + 1:08d}",
                service,
                billed,
                allowed,
                paid,
                status,
                rng.choice(diagnoses)[0],
                rng.choice(procedures)[0],
                rng.choice(PLACES),
                created,
            ))
            claim_index += 1
    care = []
    care_index = 0
    for claim in claims:
        if rng.random() > 0.2:
            continue
        enrolled = claim[5]
        care.append((
            f"CM{care_index + 1:06d}",
            claim[1],
            claim[2],
            claim[0],
            programs[care_index % len(programs)][1],
            f"CMGR{(care_index % 12) + 1:03d}",
            enrolled,
            rng.choice(["Active", "Active", "Closed"]),
            rng.choice(["Low", "Medium", "High"]),
            "Synthetic follow-up for a demo claim.",
            enrolled + timedelta(days=30),
            rng.choice(["Improved", "Stable", "Ongoing"]),
            created,
        ))
        care_index += 1
    return {
        "plans": plans,
        "diagnoses": diagnoses,
        "procedures": procedures,
        "specialties": specialties,
        "programs": programs,
        "providers": providers,
        "members": members,
        "authorizations": authorizations,
        "claims": claims,
        "care": care,
    }


def validate(data: dict[str, list[tuple]]) -> None:
    plan_ids = {row[0] for row in data["plans"]}
    diagnosis_ids = {row[0] for row in data["diagnoses"]}
    procedure_ids = {row[0] for row in data["procedures"]}
    provider_ids = {row[0] for row in data["providers"]}
    member_ids = {row[0] for row in data["members"]}
    auth_ids = {row[0] for row in data["authorizations"]}
    claim_ids = {row[0] for row in data["claims"]}
    program_types = {row[1] for row in data["programs"]}
    for member in data["members"]:
        if member[13] not in plan_ids:
            raise RuntimeError("Member plan is missing")
    for auth in data["authorizations"]:
        if auth[1] not in member_ids or auth[2] not in provider_ids:
            raise RuntimeError("Authorization link is missing")
        if auth[10] not in diagnosis_ids or auth[11] not in procedure_ids:
            raise RuntimeError("Authorization code is missing")
    for claim in data["claims"]:
        if claim[1] not in member_ids or claim[2] not in provider_ids:
            raise RuntimeError("Claim link is missing")
        if claim[3] is not None and claim[3] not in auth_ids:
            raise RuntimeError("Claim authorization is missing")
        if claim[10] not in diagnosis_ids or claim[11] not in procedure_ids:
            raise RuntimeError("Claim code is missing")
        if claim[7] > claim[6] or claim[8] > claim[7]:
            raise RuntimeError("Claim amounts are out of order")
    for record in data["care"]:
        if record[1] not in member_ids or record[2] not in provider_ids or record[3] not in claim_ids:
            raise RuntimeError("Care management link is missing")
        if record[4] not in program_types:
            raise RuntimeError("Care program is missing")


def _connect():
    import pymssql

    last: Exception | None = None
    for attempt in range(12):
        try:
            return pymssql.connect(
                server=os.environ["SQL_SERVER"],
                user=os.environ.get("SQL_ADMIN_LOGIN", "sqladmin"),
                password=os.environ["SQL_ADMIN_PASSWORD"],
                database=os.environ.get("SQL_DATABASE", "sqldb-tenant"),
                port=1433,
                tds_version="7.4",
                login_timeout=60,
                timeout=120,
            )
        except Exception as exc:  # pymssql raises several types while serverless SQL is waking
            last = exc
            text = str(exc).lower()
            if "login failed" in text:
                raise
            print(f"Database not ready, retry {attempt + 1}", flush=True)
            time.sleep(15)
    raise RuntimeError("Tenant database did not become available") from last


def _insert(cursor, sql: str, rows: list[tuple]) -> None:
    for start in range(0, len(rows), 200):
        cursor.executemany(sql, rows[start:start + 200])


def load(member_count: int) -> None:
    data = build(member_count, random.Random(os.environ.get("SQL_SERVER", "tenant")))
    validate(data)
    connection = _connect()
    try:
        cursor = connection.cursor()
        for statement in _statements():
            cursor.execute(statement)
        cursor.execute("SELECT COUNT(*) FROM dbo.[MEMBER]")
        existing = int(cursor.fetchone()[0])
        if existing:
            print(f"Tenant database already has {existing} members. Skipping synthetic load.")
            connection.commit()
            return
        _insert(cursor, "INSERT INTO dbo.[PLAN] (plan_id, plan_name, plan_type, created_at) VALUES (%s, %s, %s, %s)", data["plans"])
        _insert(cursor, "INSERT INTO dbo.DIAGNOSIS_CODE (diagnosis_code, description, code_type) VALUES (%s, %s, %s)", data["diagnoses"])
        _insert(cursor, "INSERT INTO dbo.PROCEDURE_CODE (procedure_code, description, code_type) VALUES (%s, %s, %s)", data["procedures"])
        _insert(cursor, "INSERT INTO dbo.PROVIDER_SPECIALTY (specialty_id, specialty_name) VALUES (%s, %s)", data["specialties"])
        _insert(cursor, "INSERT INTO dbo.CARE_PROGRAM (program_id, program_type) VALUES (%s, %s)", data["programs"])
        _insert(cursor, """
            INSERT INTO dbo.PROVIDER
                (provider_id, npi_number, provider_name, provider_type, specialty, phone_number,
                 address_line1, address_line2, city, state, zip_code, taxonomy_code, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, data["providers"])
        _insert(cursor, """
            INSERT INTO dbo.[MEMBER]
                (member_id, member_number, first_name, last_name, date_of_birth, gender,
                 address_line1, address_line2, city, state, zip_code, phone_number, email,
                 plan_id, effective_date, termination_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, data["members"])
        _insert(cursor, """
            INSERT INTO dbo.[AUTHORIZATION]
                (authorization_id, member_id, provider_id, authorization_number, service_type, status,
                 request_date, approval_date, start_date, end_date, diagnosis_code, procedure_code,
                 authorized_units, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, data["authorizations"])
        _insert(cursor, """
            INSERT INTO dbo.CLAIMS
                (claim_id, member_id, provider_id, authorization_id, claim_number, service_date,
                 billed_amount, allowed_amount, paid_amount, claim_status, diagnosis_code,
                 procedure_code, place_of_service, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, data["claims"])
        _insert(cursor, """
            INSERT INTO dbo.CARE_MANAGEMENT
                (care_management_id, member_id, provider_id, claim_id, program_type, care_manager_id,
                 enrollment_date, status, risk_level, notes, next_followup_date, outcome, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, data["care"])
        connection.commit()
    finally:
        connection.close()
    print(
        "Synthetic load finished. "
        f"members={len(data['members'])} providers={len(data['providers'])} "
        f"authorizations={len(data['authorizations'])} claims={len(data['claims'])} "
        f"care_management={len(data['care'])}"
    )


def main() -> None:
    count = int(os.environ.get("SYNTHETIC_MEMBERS", "250"))
    if "--check" in sys.argv:
        data = build(count, random.Random("check"))
        validate(data)
        statements = _statements()
        if len(statements) != 10:
            raise SystemExit(f"Expected 10 schema batches, found {len(statements)}")
        print(
            f"check_ok members={len(data['members'])} claims={len(data['claims'])} "
            f"authorizations={len(data['authorizations'])} care={len(data['care'])}"
        )
        return
    for name in ("SQL_SERVER", "SQL_ADMIN_PASSWORD"):
        if not os.environ.get(name, "").strip():
            raise SystemExit(f"{name} is not set")
    load(count)


if __name__ == "__main__":
    main()
