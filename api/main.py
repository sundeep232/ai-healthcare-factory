import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import execute, query

app = FastAPI(title="Demo Factory API")
TOKEN_TTL_SECONDS = 12 * 60 * 60


def _auth_secret() -> str:
    return os.environ.get("PORTAL_AUTH_SECRET", "").strip()


def _issue_token(username: str) -> str:
    expires = str(int(time.time()) + TOKEN_TTL_SECONDS)
    payload = f"{username}.{expires}"
    signature = hmac.new(_auth_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _valid_token(token: str) -> bool:
    secret = _auth_secret()
    if not secret or token.count(".") != 2:
        return False
    username, expires, signature = token.split(".", 2)
    payload = f"{username}.{expires}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        return int(expires) > int(time.time())
    except ValueError:
        return False


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path == "/api/login" or not request.url.path.startswith("/api"):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    if not _valid_token(token):
        return JSONResponse(status_code=401, content={"detail": "Sign in required"})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://witty-cliff-0ab32ba10.3.azurestaticapps.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _id(value: Any) -> str:
    return str(value)


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login):
    username = os.environ.get("PORTAL_USERNAME", "").strip()
    password = os.environ.get("PORTAL_PASSWORD", "")
    if not username or not password or not _auth_secret():
        raise HTTPException(status_code=503, detail="Sign-in is not configured")
    username_ok = len(body.username.strip()) == len(username) and hmac.compare_digest(body.username.strip(), username)
    password_ok = len(body.password) == len(password) and hmac.compare_digest(body.password, password)
    if not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="User ID or password is incorrect")
    return {"token": _issue_token(username)}


@app.get("/api/health")
def health():
    query("SELECT 1 AS ok")
    return {"status": "ok"}


@app.get("/api/customers")
def customers():
    rows = query(
        """
        SELECT c.CustomerId, c.Name, c.TenantId, c.Status, c.CreatedAt,
               b.PortalName, b.PrimaryColor, b.SecondaryColor
        FROM dbo.Customer c
        LEFT JOIN dbo.BrandingConfig b ON b.CustomerId = c.CustomerId
        ORDER BY c.Name
        """
    )
    return [
        {
            "id": _id(row["CustomerId"]),
            "name": row["Name"],
            "tenantId": row["TenantId"],
            "status": row["Status"],
            "createdAt": _iso(row["CreatedAt"]),
            "portalName": row["PortalName"],
            "primaryColor": row["PrimaryColor"],
            "secondaryColor": row["SecondaryColor"],
        }
        for row in rows
    ]


@app.get("/api/templates")
def templates():
    rows = query(
        """
        SELECT t.TemplateId, t.Name, t.Status, t.DefinitionJson, t.CreatedAt,
               u.DisplayName AS CreatedBy
        FROM dbo.Template t
        LEFT JOIN dbo.AppUser u ON u.UserId = t.CreatedByUserId
        ORDER BY t.CreatedAt DESC
        """
    )
    result = []
    for row in rows:
        definition = row["DefinitionJson"]
        if isinstance(definition, str):
            definition = json.loads(definition)
        result.append(
            {
                "id": _id(row["TemplateId"]),
                "name": row["Name"],
                "status": row["Status"],
                "definition": definition,
                "createdAt": _iso(row["CreatedAt"]),
                "createdBy": row["CreatedBy"],
            }
        )
    return result


@app.get("/api/environments")
def environments():
    rows = query(
        """
        SELECT e.EnvironmentId, e.Name, e.Status, e.ExpiresAt, e.CreatedAt,
               c.CustomerId, c.Name AS CustomerName, c.TenantId,
               b.PortalName, b.PrimaryColor,
               t.TemplateId, t.Name AS TemplateName
        FROM dbo.Environment e
        JOIN dbo.Customer c ON c.CustomerId = e.CustomerId
        LEFT JOIN dbo.BrandingConfig b ON b.CustomerId = c.CustomerId
        LEFT JOIN dbo.Template t ON t.TemplateId = e.TemplateId
        ORDER BY e.CreatedAt DESC
        """
    )
    return [_environment_summary(row) for row in rows]


def _environment_summary(row: dict) -> dict:
    return {
        "id": _id(row["EnvironmentId"]),
        "name": row["Name"],
        "status": row["Status"],
        "expiresAt": _iso(row["ExpiresAt"]),
        "createdAt": _iso(row["CreatedAt"]),
        "customerId": _id(row["CustomerId"]),
        "customerName": row["CustomerName"],
        "tenantId": row["TenantId"],
        "portalName": row["PortalName"],
        "primaryColor": row["PrimaryColor"],
        "templateId": _id(row["TemplateId"]) if row["TemplateId"] else None,
        "templateName": row["TemplateName"],
    }


@app.get("/api/environments/{environment_id}")
def environment_detail(environment_id: str):
    rows = query(
        """
        SELECT e.EnvironmentId, e.Name, e.Status, e.ExpiresAt, e.CreatedAt,
               c.CustomerId, c.Name AS CustomerName, c.TenantId,
               b.PortalName, b.PrimaryColor, b.SecondaryColor,
               t.TemplateId, t.Name AS TemplateName
        FROM dbo.Environment e
        JOIN dbo.Customer c ON c.CustomerId = e.CustomerId
        LEFT JOIN dbo.BrandingConfig b ON b.CustomerId = c.CustomerId
        LEFT JOIN dbo.Template t ON t.TemplateId = e.TemplateId
        WHERE e.EnvironmentId = %s
        """,
        (environment_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Environment not found")
    item = _environment_summary(rows[0])
    item["secondaryColor"] = rows[0]["SecondaryColor"]
    item["deployments"] = [
        {
            "id": _id(row["DeploymentLogId"]),
            "action": row["Action"],
            "status": row["Status"],
            "message": row["Message"],
            "startedAt": _iso(row["StartedAt"]),
            "finishedAt": _iso(row["FinishedAt"]),
        }
        for row in query(
            """
            SELECT DeploymentLogId, Action, Status, Message, StartedAt, FinishedAt
            FROM dbo.DeploymentLog
            WHERE EnvironmentId = %s
            ORDER BY StartedAt DESC
            """,
            (environment_id,),
        )
    ]
    item["conversations"] = [
        {
            "id": _id(row["ConversationLogId"]),
            "channel": row["Channel"],
            "transcript": row["Transcript"],
            "createdAt": _iso(row["CreatedAt"]),
        }
        for row in query(
            """
            SELECT ConversationLogId, Channel, Transcript, CreatedAt
            FROM dbo.ConversationLog
            WHERE EnvironmentId = %s
            ORDER BY CreatedAt DESC
            """,
            (environment_id,),
        )
    ]
    item["usage"] = [
        {
            "id": _id(row["UsageCostId"]),
            "meter": row["Meter"],
            "quantity": float(row["Quantity"]),
            "cost": float(row["Cost"]),
            "recordedAt": _iso(row["RecordedAt"]),
        }
        for row in query(
            """
            SELECT UsageCostId, Meter, Quantity, Cost, RecordedAt
            FROM dbo.UsageCost
            WHERE EnvironmentId = %s
            ORDER BY RecordedAt DESC
            """,
            (environment_id,),
        )
    ]
    return item


class NewEnvironment(BaseModel):
    customerId: str
    templateId: str
    name: str = Field(min_length=1, max_length=200)


@app.post("/api/environments", status_code=201)
def create_environment(body: NewEnvironment):
    customer = query("SELECT CustomerId FROM dbo.Customer WHERE CustomerId = %s", (body.customerId,))
    template = query("SELECT TemplateId FROM dbo.Template WHERE TemplateId = %s", (body.templateId,))
    if not customer or not template:
        raise HTTPException(status_code=400, detail="Customer or template was not found")

    environment_id = str(uuid.uuid4())
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    execute(
        """
        INSERT INTO dbo.Environment
            (EnvironmentId, CustomerId, TemplateId, Name, Status, ExpiresAt, CreatedAt)
        VALUES (%s, %s, %s, %s, N'Deploying', DATEADD(day, 30, SYSUTCDATETIME()), %s)
        """,
        (environment_id, body.customerId, body.templateId, body.name.strip(), now),
    )
    execute(
        """
        INSERT INTO dbo.DeploymentLog
            (DeploymentLogId, EnvironmentId, Action, Status, Message, StartedAt, FinishedAt)
        VALUES (%s, %s, N'Deploy', N'Running',
                N'Environment registered. Tenant resource group is created later from the portal.',
                %s, NULL)
        """,
        (log_id, environment_id, now),
    )
    return environment_detail(environment_id)


@app.delete("/api/environments/{environment_id}", status_code=204)
def delete_environment(environment_id: str):
    found = query("SELECT EnvironmentId FROM dbo.Environment WHERE EnvironmentId = %s", (environment_id,))
    if not found:
        raise HTTPException(status_code=404, detail="Environment not found")
    execute("DELETE FROM dbo.UsageCost WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.ConversationLog WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.DeploymentLog WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.Environment WHERE EnvironmentId = %s", (environment_id,))


@app.get("/api/analytics")
def analytics():
    rows = query(
        """
        SELECT e.EnvironmentId, e.Name AS EnvironmentName, c.Name AS CustomerName,
               u.Meter, u.Quantity, u.Cost, u.RecordedAt
        FROM dbo.UsageCost u
        JOIN dbo.Environment e ON e.EnvironmentId = u.EnvironmentId
        JOIN dbo.Customer c ON c.CustomerId = e.CustomerId
        ORDER BY u.RecordedAt DESC
        """
    )
    items = [
        {
            "environmentId": _id(row["EnvironmentId"]),
            "environmentName": row["EnvironmentName"],
            "customerName": row["CustomerName"],
            "meter": row["Meter"],
            "quantity": float(row["Quantity"]),
            "cost": float(row["Cost"]),
            "recordedAt": _iso(row["RecordedAt"]),
        }
        for row in rows
    ]
    return {
        "totalCost": round(sum(item["cost"] for item in items), 2),
        "rows": items,
    }
