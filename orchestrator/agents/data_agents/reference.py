"""Curated reference data for the synthetic generators.

Codes are real, public ICD-10-CM / CPT / HCPCS identifiers (so demos look like payer
data); every person, provider and organisation built from them is fictional.
"""

from __future__ import annotations

from dataclasses import dataclass

FIRST_NAMES_F = (
    "Olivia", "Emma", "Sophia", "Ava", "Isabella", "Mia", "Amelia", "Harper", "Evelyn", "Abigail",
    "Ella", "Scarlett", "Grace", "Chloe", "Camila", "Penelope", "Layla", "Riley", "Zoey", "Nora",
    "Lily", "Eleanor", "Hannah", "Lillian", "Addison", "Aubrey", "Stella", "Natalie", "Leah", "Maya",
    "Priya", "Fatima", "Mei", "Aaliyah", "Rosa", "Imani", "Sofia", "Yuki", "Nadia", "Carmen",
)
FIRST_NAMES_M = (
    "Liam", "Noah", "Oliver", "James", "Elijah", "William", "Henry", "Lucas", "Benjamin", "Theodore",
    "Mateo", "Levi", "Sebastian", "Daniel", "Jack", "Michael", "Alexander", "Owen", "Samuel", "Ethan",
    "Jacob", "Asher", "Wyatt", "Hudson", "Grayson", "Luke", "Gabriel", "Carter", "Isaac", "Jayden",
    "Arjun", "Omar", "Wei", "Malik", "Diego", "Kofi", "Andre", "Hiro", "Tariq", "Mateus",
)
LAST_NAMES = (
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez",
    "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore",
    "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
    "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Patel", "Kim", "Chen", "Singh", "Khan", "Okafor", "Silva", "Novak",
)
STREETS = (
    "Maple St", "Oak Ave", "Pine Rd", "Cedar Ln", "Elm St", "Washington Blvd", "Lakeview Dr",
    "Hillcrest Rd", "Sunset Ave", "River Rd", "Park Ave", "Meadow Ln", "Highland Ave", "Church St",
    "Spring St", "Walnut St", "Willow Way", "Prairie Rd", "Franklin St", "Jefferson Ave",
)
# city, state, ZIP prefix (the last two digits are random, so no real address is implied)
CITIES = (
    ("Kansas City", "MO", "641"), ("Omaha", "NE", "681"), ("Des Moines", "IA", "503"),
    ("Wichita", "KS", "672"), ("Minneapolis", "MN", "554"), ("St. Louis", "MO", "631"),
    ("Tulsa", "OK", "741"), ("Oklahoma City", "OK", "731"), ("Little Rock", "AR", "722"),
    ("Dallas", "TX", "752"), ("Austin", "TX", "787"), ("Denver", "CO", "802"),
    ("Chicago", "IL", "606"), ("Madison", "WI", "537"), ("Indianapolis", "IN", "462"),
    ("Columbus", "OH", "432"), ("Nashville", "TN", "372"), ("Memphis", "TN", "381"),
)
ORG_PREFIXES = (
    "Heartland", "Lakeside", "Prairie", "Riverbend", "Summit", "Cornerstone", "Unity", "Pinnacle",
    "Meridian", "Evergreen", "Crossroads", "Bluestem", "Northgate", "Fairview", "Ridgeway",
)

PLAN_TYPES = (("HMO", 30), ("PPO", 35), ("Medicare Advantage", 20), ("Medicaid Managed Care", 10), ("EPO", 5))


@dataclass(frozen=True)
class Procedure:
    code: str
    description: str
    category: str  # authorization service category
    allowed: float  # typical allowed amount (USD)
    place_of_service: str
    needs_auth: bool


@dataclass(frozen=True)
class Condition:
    code: str
    description: str
    specialties: tuple[str, ...]
    procedures: tuple[str, ...]  # Procedure codes commonly billed with this diagnosis
    sex: str | None = None  # "F" or "M" if restricted
    min_age: int = 0
    max_age: int = 120
    chronic: bool = False
    weight: int = 1


PROCEDURES: dict[str, Procedure] = {
    p.code: p
    for p in (
        Procedure("99213", "Office visit, established patient, low complexity", "Evaluation & Management", 92.0, "Office", False),
        Procedure("99214", "Office visit, established patient, moderate complexity", "Evaluation & Management", 135.0, "Office", False),
        Procedure("99203", "Office visit, new patient, low complexity", "Evaluation & Management", 118.0, "Office", False),
        Procedure("99285", "Emergency department visit, high severity", "Emergency", 610.0, "Emergency Room", False),
        Procedure("99223", "Initial hospital care, high complexity", "Inpatient Admission", 285.0, "Inpatient Hospital", True),
        Procedure("93000", "Electrocardiogram, 12-lead with interpretation", "Cardiology", 24.0, "Office", False),
        Procedure("93306", "Echocardiography, complete with Doppler", "Cardiology", 235.0, "Outpatient Hospital", True),
        Procedure("93458", "Left heart catheterization with coronary angiography", "Cardiology", 1850.0, "Outpatient Hospital", True),
        Procedure("78452", "Myocardial perfusion imaging, SPECT", "Advanced Imaging", 890.0, "Outpatient Hospital", True),
        Procedure("70553", "MRI brain with and without contrast", "Advanced Imaging", 780.0, "Outpatient Hospital", True),
        Procedure("72148", "MRI lumbar spine without contrast", "Advanced Imaging", 540.0, "Outpatient Hospital", True),
        Procedure("73721", "MRI lower extremity joint without contrast", "Advanced Imaging", 520.0, "Outpatient Hospital", True),
        Procedure("74177", "CT abdomen and pelvis with contrast", "Advanced Imaging", 610.0, "Outpatient Hospital", True),
        Procedure("71046", "Chest X-ray, 2 views", "Imaging", 38.0, "Outpatient Hospital", False),
        Procedure("77067", "Screening mammography, bilateral", "Imaging", 142.0, "Outpatient Hospital", False),
        Procedure("45378", "Colonoscopy, diagnostic", "Gastroenterology", 780.0, "Ambulatory Surgical Center", False),
        Procedure("43239", "Upper GI endoscopy with biopsy", "Gastroenterology", 690.0, "Ambulatory Surgical Center", False),
        Procedure("27447", "Total knee arthroplasty", "Surgery", 11200.0, "Inpatient Hospital", True),
        Procedure("27130", "Total hip arthroplasty", "Surgery", 11800.0, "Inpatient Hospital", True),
        Procedure("63030", "Lumbar laminotomy with disc excision", "Surgery", 6200.0, "Outpatient Hospital", True),
        Procedure("29881", "Knee arthroscopy with meniscectomy", "Surgery", 3100.0, "Ambulatory Surgical Center", True),
        Procedure("59400", "Routine obstetric care, vaginal delivery", "Maternity", 3400.0, "Inpatient Hospital", False),
        Procedure("59510", "Routine obstetric care, cesarean delivery", "Maternity", 4200.0, "Inpatient Hospital", True),
        Procedure("97110", "Therapeutic exercise, each 15 minutes", "Physical Therapy", 38.0, "Office", True),
        Procedure("97162", "Physical therapy evaluation, moderate complexity", "Physical Therapy", 95.0, "Office", False),
        Procedure("90837", "Psychotherapy, 60 minutes", "Behavioral Health", 142.0, "Office", False),
        Procedure("90853", "Group psychotherapy", "Behavioral Health", 36.0, "Office", False),
        Procedure("83036", "Hemoglobin A1c", "Laboratory", 14.0, "Independent Lab", False),
        Procedure("80053", "Comprehensive metabolic panel", "Laboratory", 11.0, "Independent Lab", False),
        Procedure("85025", "Complete blood count with differential", "Laboratory", 9.0, "Independent Lab", False),
        Procedure("94010", "Spirometry", "Pulmonology", 48.0, "Office", False),
        Procedure("E0601", "Continuous positive airway pressure (CPAP) device", "Durable Medical Equipment", 780.0, "Home", True),
        Procedure("E1390", "Oxygen concentrator", "Durable Medical Equipment", 190.0, "Home", True),
        Procedure("J1745", "Infliximab injection, 10 mg", "Specialty Drug", 1250.0, "Office", True),
        Procedure("J9035", "Bevacizumab injection, 10 mg", "Specialty Drug", 980.0, "Outpatient Hospital", True),
        Procedure("96413", "Chemotherapy infusion, up to 1 hour", "Oncology", 310.0, "Outpatient Hospital", True),
        Procedure("90471", "Immunization administration", "Preventive", 28.0, "Office", False),
        Procedure("G0439", "Annual wellness visit, subsequent", "Preventive", 118.0, "Office", False),
    )
}

_A = ("Family Medicine", "Internal Medicine")
CONDITIONS: tuple[Condition, ...] = (
    Condition("E11.9", "Type 2 diabetes mellitus without complications", _A + ("Endocrinology",), ("99214", "83036", "80053", "99213"), min_age=30, chronic=True, weight=6),
    Condition("E11.65", "Type 2 diabetes mellitus with hyperglycemia", ("Endocrinology",) + _A, ("99214", "83036", "J1745"), min_age=35, chronic=True, weight=2),
    Condition("I10", "Essential (primary) hypertension", _A + ("Cardiology",), ("99213", "93000", "80053"), min_age=30, chronic=True, weight=8),
    Condition("I25.10", "Atherosclerotic heart disease of native coronary artery", ("Cardiology",), ("99214", "93306", "78452", "93458"), min_age=45, chronic=True, weight=3),
    Condition("I50.9", "Heart failure, unspecified", ("Cardiology",) + _A, ("99214", "93306", "99223", "99285"), min_age=50, chronic=True, weight=2),
    Condition("J44.9", "Chronic obstructive pulmonary disease, unspecified", ("Pulmonology",) + _A, ("99214", "94010", "E1390", "71046"), min_age=45, chronic=True, weight=3),
    Condition("J45.909", "Unspecified asthma, uncomplicated", ("Pulmonology",) + _A, ("99213", "94010"), chronic=True, weight=3),
    Condition("G47.33", "Obstructive sleep apnea", ("Pulmonology",) + _A, ("99213", "E0601"), min_age=25, chronic=True, weight=2),
    Condition("M54.5", "Low back pain", ("Orthopedics", "Physical Medicine") + _A, ("99213", "72148", "97110", "97162", "63030"), min_age=20, weight=7),
    Condition("M17.11", "Unilateral primary osteoarthritis, right knee", ("Orthopedics",), ("99214", "73721", "29881", "27447", "97110"), min_age=45, weight=3),
    Condition("M16.11", "Unilateral primary osteoarthritis, right hip", ("Orthopedics",), ("99214", "27130", "97110"), min_age=50, weight=2),
    Condition("F32.1", "Major depressive disorder, single episode, moderate", ("Behavioral Health",) + _A, ("90837", "99214", "90853"), min_age=12, chronic=True, weight=4),
    Condition("F41.1", "Generalized anxiety disorder", ("Behavioral Health",) + _A, ("90837", "99213"), min_age=12, chronic=True, weight=4),
    Condition("K21.9", "Gastro-esophageal reflux disease without esophagitis", ("Gastroenterology",) + _A, ("99213", "43239"), min_age=20, weight=3),
    Condition("Z12.11", "Encounter for screening for malignant neoplasm of colon", ("Gastroenterology",), ("45378",), min_age=45, max_age=80, weight=2),
    Condition("Z12.31", "Encounter for screening mammogram for malignant neoplasm of breast", ("Obstetrics & Gynecology",) + _A, ("77067",), sex="F", min_age=40, max_age=75, weight=3),
    Condition("C50.911", "Malignant neoplasm of unspecified site of right female breast", ("Oncology",), ("99214", "96413", "J9035", "70553"), sex="F", min_age=35, chronic=True, weight=1),
    Condition("C18.9", "Malignant neoplasm of colon, unspecified", ("Oncology",), ("99214", "96413", "74177", "J9035"), min_age=40, chronic=True, weight=1),
    Condition("Z34.90", "Supervision of normal pregnancy, unspecified trimester", ("Obstetrics & Gynecology",), ("99213", "59400", "59510"), sex="F", min_age=18, max_age=44, weight=2),
    Condition("G43.909", "Migraine, unspecified, not intractable", ("Neurology",) + _A, ("99214", "70553"), min_age=15, weight=2),
    Condition("K50.90", "Crohn's disease, unspecified, without complications", ("Gastroenterology",), ("99214", "J1745", "45378"), min_age=18, chronic=True, weight=1),
    Condition("R07.9", "Chest pain, unspecified", ("Emergency Medicine", "Cardiology"), ("99285", "93000", "71046", "93306"), min_age=30, weight=3),
    Condition("Z00.00", "Encounter for general adult medical examination", _A, ("G0439", "90471", "85025", "99203"), min_age=18, weight=6),
)

SPECIALTIES = (
    "Family Medicine", "Internal Medicine", "Cardiology", "Endocrinology", "Pulmonology",
    "Orthopedics", "Physical Medicine", "Behavioral Health", "Gastroenterology",
    "Obstetrics & Gynecology", "Oncology", "Neurology", "Emergency Medicine",
)
# Relative share of providers per specialty.
SPECIALTY_WEIGHTS = (24, 18, 7, 4, 4, 7, 4, 8, 5, 6, 4, 4, 5)

ORG_SUFFIX_BY_SPECIALTY = {
    "Family Medicine": "Family Medicine", "Internal Medicine": "Internal Medicine Associates",
    "Cardiology": "Heart Institute", "Endocrinology": "Endocrine Center",
    "Pulmonology": "Pulmonary Group", "Orthopedics": "Orthopedic Specialists",
    "Physical Medicine": "Rehabilitation Clinic", "Behavioral Health": "Behavioral Health",
    "Gastroenterology": "Digestive Health", "Obstetrics & Gynecology": "Women's Health",
    "Oncology": "Cancer Center", "Neurology": "Neurology Associates",
    "Emergency Medicine": "Emergency Physicians",
}

CLAIM_DENIAL_REASONS = (
    "Service not covered under plan", "Missing or invalid prior authorization",
    "Duplicate claim", "Timely filing limit exceeded", "Out-of-network provider",
    "Medical necessity not established", "Coordination of benefits required",
)
AUTH_DENIAL_REASONS = (
    "Clinical criteria not met", "Lower level of care available", "Insufficient clinical documentation",
    "Out-of-network provider; in-network alternative available", "Experimental or investigational service",
    "Duplicate request", "Service not a covered benefit",
)

CARE_PROGRAMS = (
    ("Diabetes Management", ("E11.9", "E11.65"), "Improve HbA1c below 8.0% and complete annual eye and foot exams"),
    ("Heart Failure Management", ("I50.9", "I25.10"), "Reduce 30-day readmissions and maintain daily weight monitoring"),
    ("COPD Management", ("J44.9",), "Reduce exacerbations and complete pulmonary rehabilitation"),
    ("Hypertension Control", ("I10",), "Achieve blood pressure below 130/80 with medication adherence"),
    ("Behavioral Health Integration", ("F32.1", "F41.1"), "Complete a behavioral health follow-up within 7 days of discharge"),
    ("Maternity Program", ("Z34.90",), "Attend all prenatal visits and complete postpartum visit"),
    ("Transitions of Care", ("R07.9", "I50.9"), "Complete follow-up visit within 7 days of discharge"),
    ("Musculoskeletal Care", ("M54.5", "M17.11"), "Reduce pain score and avoid unnecessary imaging or surgery"),
)
CARE_PROGRAM_FALLBACK = "Complex Care Coordination"

CARE_MANAGERS = (
    "Jordan Ellis RN", "Priya Raman RN", "Marcus Webb LCSW", "Elena Petrova RN", "Tamika Brooks RN",
    "Daniel Okoye RN", "Sofia Marquez LCSW", "Hannah Fischer RN",
)

NOTE_TEMPLATES = {
    "Outreach call": (
        "Outbound call to member to introduce the care management program. Member agreed to participate.",
        "Attempted outreach by phone; no answer, left a voicemail with callback number.",
        "Reached member; reviewed upcoming appointments and transportation needs.",
    ),
    "Assessment": (
        "Completed initial health risk assessment. Identified medication adherence as a primary gap.",
        "Reviewed social needs screening; no urgent barriers reported.",
        "Reassessed goals with the member; progress is on track.",
    ),
    "Education": (
        "Provided education on self-management and warning signs that need urgent attention.",
        "Reviewed diet and activity recommendations and shared written materials.",
    ),
    "Care coordination": (
        "Coordinated follow-up appointment with the member's primary care provider.",
        "Contacted specialist office to confirm prior authorization status for the planned service.",
        "Arranged durable medical equipment delivery and confirmed receipt with the member.",
    ),
}

TIMELINE_ENTRIES = {
    "enrolled": "Member enrolled in the care management program",
    "outreach": "Care manager outreach completed",
    "assessment_completed": "Health risk assessment completed",
    "goal_milestone": "Member reached a care plan milestone",
    "authorization_decision": "Authorization decision recorded",
    "claim_received": "Related claim received",
    "care_plan_review": "Care plan reviewed with the member",
}
