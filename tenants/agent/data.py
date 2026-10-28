"""Read-only lookups against one tenant's payer tables."""

import os
import time
from datetime import date, datetime
from decimal import Decimal

import pymssql


def _cell(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _rows(cursor):
    columns = [col[0] for col in cursor.description]
    return [{key: _cell(value) for key, value in zip(columns, row)} for row in cursor.fetchall()]


def connect():
    last = None
    for _ in range(4):
        try:
            return pymssql.connect(
                server=os.environ["SQL_SERVER"],
                user=os.environ.get("SQL_ADMIN_LOGIN", "sqladmin"),
                password=os.environ["SQL_ADMIN_PASSWORD"],
                database=os.environ.get("SQL_DATABASE", "sqldb-tenant"),
                port=1433,
                tds_version="7.4",
                login_timeout=30,
                timeout=30,
            )
        except Exception as exc:
            last = exc
            if "login failed" in str(exc).lower():
                raise
            time.sleep(5)
    raise RuntimeError("Tenant database is not available") from last


def query(sql: str, params: tuple = ()):
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        return _rows(cursor)
    finally:
        connection.close()


def find_members(name: str = "", member_number: str = "") -> dict:
    name = name.strip()
    member_number = member_number.strip()
    like_name = f"%{name}%"
    like_number = f"%{member_number}%"
    rows = query(
        """
        SELECT TOP 15 m.member_id, m.member_number, m.first_name, m.last_name, m.date_of_birth,
               m.city, m.state, m.gender, p.plan_name, p.plan_type
        FROM dbo.[MEMBER] m
        JOIN dbo.[PLAN] p ON p.plan_id = m.plan_id
        WHERE (%s = N'' OR m.first_name + N' ' + m.last_name LIKE %s OR m.last_name LIKE %s)
          AND (%s = N'' OR m.member_number LIKE %s)
        ORDER BY m.last_name, m.first_name
        """,
        (name, like_name, like_name, member_number, like_number),
    )
    return {"members": rows}


def member_claims(member_id: str = "", name: str = "", status: str = "") -> dict:
    member_id = member_id.strip()
    name = name.strip()
    status = status.strip()
    if len(member_id) < 2 and len(name) < 2:
        return {"error": "Provide a member id or a member name."}
    like_name = f"%{name}%"
    rows = query(
        """
        SELECT TOP 25 c.claim_id, c.claim_number, c.service_date, c.claim_status, c.billed_amount,
               c.allowed_amount, c.paid_amount, c.diagnosis_code, d.description AS diagnosis,
               c.procedure_code, pr.description AS procedure_name, c.place_of_service,
               pv.provider_name, m.member_id, m.first_name, m.last_name, m.member_number
        FROM dbo.CLAIMS c
        JOIN dbo.[MEMBER] m ON m.member_id = c.member_id
        JOIN dbo.PROVIDER pv ON pv.provider_id = c.provider_id
        JOIN dbo.DIAGNOSIS_CODE d ON d.diagnosis_code = c.diagnosis_code
        JOIN dbo.PROCEDURE_CODE pr ON pr.procedure_code = c.procedure_code
        WHERE ((%s <> N'' AND c.member_id = %s)
            OR (%s <> N'' AND (m.last_name LIKE %s OR m.first_name + N' ' + m.last_name LIKE %s)))
          AND (%s = N'' OR c.claim_status = %s)
        ORDER BY c.service_date DESC
        """,
        (member_id, member_id, name, like_name, like_name, status, status),
    )
    return {"claims": rows}


def member_authorizations(member_id: str, status: str = "") -> dict:
    rows = query(
        """
        SELECT TOP 20 a.authorization_id, a.authorization_number, a.service_type, a.status,
               a.request_date, a.approval_date, a.start_date, a.end_date, a.authorized_units,
               a.diagnosis_code, a.procedure_code, pv.provider_name
        FROM dbo.[AUTHORIZATION] a
        JOIN dbo.PROVIDER pv ON pv.provider_id = a.provider_id
        WHERE a.member_id = %s AND (%s = N'' OR a.status = %s)
        ORDER BY a.request_date DESC
        """,
        (member_id, status, status),
    )
    return {"authorizations": rows}


def member_care(member_id: str) -> dict:
    rows = query(
        """
        SELECT TOP 20 care_management_id, program_type, status, risk_level, enrollment_date,
               next_followup_date, outcome, notes, claim_id
        FROM dbo.CARE_MANAGEMENT
        WHERE member_id = %s
        ORDER BY enrollment_date DESC
        """,
        (member_id,),
    )
    return {"care": rows}


def portfolio() -> dict:
    members = query("SELECT COUNT(*) AS members FROM dbo.[MEMBER]")
    claims = query("SELECT claim_status, COUNT(*) AS claims FROM dbo.CLAIMS GROUP BY claim_status")
    authorizations = query("SELECT status, COUNT(*) AS authorizations FROM dbo.[AUTHORIZATION] GROUP BY status")
    care = query("SELECT program_type, COUNT(*) AS records FROM dbo.CARE_MANAGEMENT GROUP BY program_type")
    diagnoses = query(
        """
        SELECT TOP 8 c.diagnosis_code, d.description, COUNT(*) AS claims
        FROM dbo.CLAIMS c
        JOIN dbo.DIAGNOSIS_CODE d ON d.diagnosis_code = c.diagnosis_code
        GROUP BY c.diagnosis_code, d.description
        ORDER BY COUNT(*) DESC
        """
    )
    return {
        "members": members[0]["members"] if members else 0,
        "claims_by_status": claims,
        "authorizations_by_status": authorizations,
        "care_by_program": care,
        "top_diagnoses": diagnoses,
    }


def portal_summary() -> dict:
    return portfolio()


def portal_claims(q: str = "", status: str = "") -> dict:
    q = q.strip()[:80]
    status = status.strip()
    like = f"%{q}%"
    rows = query(
        """
        SELECT TOP 40 c.claim_id, c.claim_number, c.service_date, c.claim_status,
               c.billed_amount, c.allowed_amount, c.paid_amount,
               m.member_id, m.first_name, m.last_name, m.member_number, pv.provider_name
        FROM dbo.CLAIMS c
        JOIN dbo.[MEMBER] m ON m.member_id = c.member_id
        JOIN dbo.PROVIDER pv ON pv.provider_id = c.provider_id
        WHERE (%s = N'' OR c.claim_number LIKE %s OR c.claim_id LIKE %s
               OR m.member_number LIKE %s OR m.last_name LIKE %s
               OR m.first_name + N' ' + m.last_name LIKE %s)
          AND (%s = N'' OR c.claim_status = %s)
        ORDER BY c.service_date DESC
        """,
        (q, like, like, like, like, like, status, status),
    )
    return {"claims": rows}


def portal_claim(claim_id: str) -> dict:
    rows = query(
        """
        SELECT c.claim_id, c.claim_number, c.service_date, c.claim_status, c.billed_amount,
               c.allowed_amount, c.paid_amount, c.place_of_service, c.created_at,
               c.diagnosis_code, d.description AS diagnosis, c.procedure_code,
               pr.description AS procedure_name, m.member_id, m.member_number, m.first_name,
               m.last_name, m.date_of_birth, m.city, m.state, p.plan_name, p.plan_type,
               pv.provider_name, pv.npi_number, pv.specialty, pv.provider_type,
               a.authorization_id, a.authorization_number, a.status AS authorization_status,
               a.service_type
        FROM dbo.CLAIMS c
        JOIN dbo.[MEMBER] m ON m.member_id = c.member_id
        JOIN dbo.[PLAN] p ON p.plan_id = m.plan_id
        JOIN dbo.DIAGNOSIS_CODE d ON d.diagnosis_code = c.diagnosis_code
        JOIN dbo.PROCEDURE_CODE pr ON pr.procedure_code = c.procedure_code
        JOIN dbo.PROVIDER pv ON pv.provider_id = c.provider_id
        LEFT JOIN dbo.[AUTHORIZATION] a ON a.authorization_id = c.authorization_id
        WHERE c.claim_id = %s
        """,
        (claim_id,),
    )
    if not rows:
        return {"error": "Claim was not found"}
    return {"claim": rows[0]}


def portal_authorizations(q: str = "", status: str = "") -> dict:
    q = q.strip()[:80]
    status = status.strip()
    like = f"%{q}%"
    rows = query(
        """
        SELECT TOP 40 a.authorization_id, a.authorization_number, a.service_type, a.status,
               a.request_date, a.start_date, a.end_date, a.authorized_units,
               m.member_id, m.first_name, m.last_name, m.member_number, pv.provider_name
        FROM dbo.[AUTHORIZATION] a
        JOIN dbo.[MEMBER] m ON m.member_id = a.member_id
        JOIN dbo.PROVIDER pv ON pv.provider_id = a.provider_id
        WHERE (%s = N'' OR a.authorization_number LIKE %s OR a.authorization_id LIKE %s
               OR m.member_number LIKE %s OR m.last_name LIKE %s
               OR m.first_name + N' ' + m.last_name LIKE %s)
          AND (%s = N'' OR a.status = %s)
        ORDER BY a.request_date DESC
        """,
        (q, like, like, like, like, like, status, status),
    )
    return {"authorizations": rows}


def portal_authorization(authorization_id: str) -> dict:
    rows = query(
        """
        SELECT a.authorization_id, a.authorization_number, a.service_type, a.status,
               a.request_date, a.approval_date, a.start_date, a.end_date, a.authorized_units,
               a.diagnosis_code, d.description AS diagnosis, a.procedure_code,
               pr.description AS procedure_name, m.member_id, m.member_number, m.first_name,
               m.last_name, m.date_of_birth, p.plan_name, pv.provider_name, pv.npi_number, pv.specialty
        FROM dbo.[AUTHORIZATION] a
        JOIN dbo.[MEMBER] m ON m.member_id = a.member_id
        JOIN dbo.[PLAN] p ON p.plan_id = m.plan_id
        JOIN dbo.DIAGNOSIS_CODE d ON d.diagnosis_code = a.diagnosis_code
        JOIN dbo.PROCEDURE_CODE pr ON pr.procedure_code = a.procedure_code
        JOIN dbo.PROVIDER pv ON pv.provider_id = a.provider_id
        WHERE a.authorization_id = %s
        """,
        (authorization_id,),
    )
    if not rows:
        return {"error": "Authorization was not found"}
    return {"authorization": rows[0]}


def portal_members(q: str = "") -> dict:
    q = q.strip()[:80]
    like = f"%{q}%"
    rows = query(
        """
        SELECT TOP 40 m.member_id, m.member_number, m.first_name, m.last_name, m.date_of_birth,
               m.city, m.state, m.gender, m.effective_date, m.termination_date,
               p.plan_name, p.plan_type
        FROM dbo.[MEMBER] m
        JOIN dbo.[PLAN] p ON p.plan_id = m.plan_id
        WHERE %s = N'' OR m.member_number LIKE %s OR m.last_name LIKE %s
           OR m.first_name + N' ' + m.last_name LIKE %s OR m.member_id LIKE %s
        ORDER BY m.last_name, m.first_name
        """,
        (q, like, like, like, like),
    )
    return {"members": rows}


def portal_member(member_id: str) -> dict:
    rows = query(
        """
        SELECT m.member_id, m.member_number, m.first_name, m.last_name, m.date_of_birth, m.gender,
               m.city, m.state, m.effective_date, m.termination_date, p.plan_name, p.plan_type
        FROM dbo.[MEMBER] m
        JOIN dbo.[PLAN] p ON p.plan_id = m.plan_id
        WHERE m.member_id = %s
        """,
        (member_id,),
    )
    if not rows:
        return {"error": "Member was not found"}
    return {
        "member": rows[0],
        "claims": member_claims(member_id=member_id).get("claims", []),
        "authorizations": member_authorizations(member_id).get("authorizations", []),
        "care": member_care(member_id).get("care", []),
    }


def portal_care(q: str = "") -> dict:
    q = q.strip()[:80]
    like = f"%{q}%"
    rows = query(
        """
        SELECT TOP 40 c.care_management_id, c.program_type, c.status, c.risk_level,
               c.enrollment_date, c.next_followup_date, c.outcome, c.notes,
               m.member_id, m.first_name, m.last_name, m.member_number
        FROM dbo.CARE_MANAGEMENT c
        JOIN dbo.[MEMBER] m ON m.member_id = c.member_id
        WHERE %s = N'' OR c.program_type LIKE %s OR m.last_name LIKE %s
           OR m.member_number LIKE %s OR m.first_name + N' ' + m.last_name LIKE %s
        ORDER BY c.enrollment_date DESC
        """,
        (q, like, like, like, like),
    )
    return {"care": rows}


TOOLS = {
    "find_members": find_members,
    "member_claims": member_claims,
    "member_authorizations": member_authorizations,
    "member_care": member_care,
    "portfolio": portfolio,
}


def run_tool(name: str, arguments: dict) -> dict:
    function = TOOLS.get(name)
    if function is None:
        return {"error": "Unknown tool"}
    try:
        return function(**{key: value for key, value in arguments.items() if value is not None})
    except TypeError:
        return {"error": "Tool arguments were not valid"}
    except Exception:
        return {"error": "The demo database could not be read"}
