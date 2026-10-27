import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from db import execute, query
from github_actions import GitHubError, dispatch_deploy, dispatch_destroy, fetch_log, find_run, get_run

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
    pending = query(
        """
        SELECT EnvironmentId
        FROM dbo.Environment
        WHERE Slug IS NOT NULL AND Status IN (%s, %s)
        """,
        ("Deploying", "Destroying"),
    )
    for item in pending:
        try:
            _sync_workflow(str(item["EnvironmentId"]), include_log=False)
        except GitHubError:
            pass
    rows = query(
        """
        SELECT e.EnvironmentId, e.Name, e.Slug, e.Status, e.ExpiresAt, e.CreatedAt,
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
        "slug": row["Slug"],
        "templateId": _id(row["TemplateId"]) if row["TemplateId"] else None,
        "templateName": row["TemplateName"],
    }


def _slug(name: str, environment_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "demo"
    return f"{base}-{environment_id.replace('-', '')[:4]}"


def _sync_workflow(environment_id: str, include_log: bool = True) -> None:
    envs = query(
        "SELECT Slug, Status FROM dbo.Environment WHERE EnvironmentId = %s",
        (environment_id,),
    )
    if not envs or not envs[0]["Slug"] or envs[0]["Status"] not in ("Deploying", "Destroying"):
        return
    destroying = envs[0]["Status"] == "Destroying"
    verb = "Destroy" if destroying else "Deploy"
    rows = query(
        """
        SELECT DeploymentLogId, Status, WorkflowRunId, LogText
        FROM dbo.DeploymentLog
        WHERE EnvironmentId = %s AND Action = %s
        ORDER BY StartedAt DESC
        """,
        (environment_id, verb),
    )
    if not rows or rows[0]["Status"] not in ("Running", "Queued"):
        return
    row = rows[0]
    log_id = str(row["DeploymentLogId"])
    run_id = row["WorkflowRunId"]
    running_message = "Terraform is destroying the resource group." if destroying else "Terraform is running."
    try:
        if not run_id:
            run_id = find_run(environment_id, verb)
            if not run_id:
                waiting = "Waiting for GitHub Actions to start."
                execute(
                    """
                    UPDATE dbo.DeploymentLog
                    SET Message = %s, LogText = %s
                    WHERE DeploymentLogId = %s
                    """,
                    (waiting, waiting, log_id),
                )
                return
            execute(
                """
                UPDATE dbo.DeploymentLog
                SET WorkflowRunId = %s, Message = %s
                WHERE DeploymentLogId = %s
                """,
                (run_id, running_message, log_id),
            )
        run = get_run(int(run_id))
        completed = run.get("status") == "completed"
        log_text = row["LogText"] or ""
        if include_log or completed:
            try:
                downloaded = fetch_log(int(run_id))
                if downloaded:
                    log_text = downloaded
            except GitHubError:
                pass
        if completed:
            ok = run.get("conclusion") == "success"
            if destroying:
                finished = "Terraform destroy finished." if ok else f"Terraform destroy {run.get('conclusion') or 'failed'}."
                environment_status = "Destroyed" if ok else "Failed"
            else:
                finished = "Terraform apply finished." if ok else f"Terraform apply {run.get('conclusion') or 'failed'}."
                environment_status = "Active" if ok else "Failed"
            execute(
                """
                UPDATE dbo.DeploymentLog
                SET Status = %s, Message = %s, LogText = %s, FinishedAt = SYSUTCDATETIME()
                WHERE DeploymentLogId = %s
                """,
                ("Succeeded" if ok else "Failed", finished, log_text, log_id),
            )
            execute(
                "UPDATE dbo.Environment SET Status = %s WHERE EnvironmentId = %s",
                (environment_status, environment_id),
            )
            return
        if log_text != (row["LogText"] or ""):
            execute(
                """
                UPDATE dbo.DeploymentLog
                SET Status = N'Running', Message = %s, LogText = %s
                WHERE DeploymentLogId = %s
                """,
                (running_message, log_text, log_id),
            )
    except GitHubError as exc:
        execute(
            "UPDATE dbo.DeploymentLog SET Message = %s WHERE DeploymentLogId = %s",
            (str(exc)[:900], log_id),
        )


@app.get("/api/environments/{environment_id}")
def environment_detail(environment_id: str):
    _sync_workflow(environment_id)
    rows = query(
        """
        SELECT e.EnvironmentId, e.Name, e.Slug, e.Status, e.ExpiresAt, e.CreatedAt,
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
    item["slug"] = rows[0]["Slug"]
    item["secondaryColor"] = rows[0]["SecondaryColor"]
    item["deployments"] = [
        {
            "id": _id(row["DeploymentLogId"]),
            "action": row["Action"],
            "status": row["Status"],
            "message": row["Message"],
            "log": row["LogText"] or "",
            "startedAt": _iso(row["StartedAt"]),
            "finishedAt": _iso(row["FinishedAt"]),
        }
        for row in query(
            """
            SELECT DeploymentLogId, Action, Status, Message, LogText, StartedAt, FinishedAt
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
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    slug = _slug(name, environment_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    execute(
        """
        INSERT INTO dbo.Environment
            (EnvironmentId, CustomerId, TemplateId, Name, Slug, Status, ExpiresAt, CreatedAt)
        VALUES (%s, %s, %s, %s, %s, N'Deploying', DATEADD(day, 30, SYSUTCDATETIME()), %s)
        """,
        (environment_id, body.customerId, body.templateId, name, slug, now),
    )
    try:
        dispatch_deploy(slug, name, environment_id)
        status = "Running"
        message = "GitHub Actions workflow queued."
        environment_status = "Deploying"
    except GitHubError as exc:
        status = "Failed"
        message = str(exc)[:900]
        environment_status = "Failed"
    execute(
        """
        INSERT INTO dbo.DeploymentLog
            (DeploymentLogId, EnvironmentId, Action, Status, Message, LogText, StartedAt, FinishedAt)
        VALUES (%s, %s, N'Deploy', %s, %s, %s, %s, CASE WHEN %s = N'Failed' THEN %s ELSE NULL END)
        """,
        (log_id, environment_id, status, message, message, now, status, now),
    )
    if environment_status == "Failed":
        execute(
            "UPDATE dbo.Environment SET Status = N'Failed' WHERE EnvironmentId = %s",
            (environment_id,),
        )
    return environment_detail(environment_id)


def _purge_environment(environment_id: str) -> None:
    execute("DELETE FROM dbo.UsageCost WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.ConversationLog WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.DeploymentLog WHERE EnvironmentId = %s", (environment_id,))
    execute("DELETE FROM dbo.Environment WHERE EnvironmentId = %s", (environment_id,))


@app.delete("/api/environments/{environment_id}")
def delete_environment(environment_id: str):
    found = query(
        "SELECT Name, Slug, Status FROM dbo.Environment WHERE EnvironmentId = %s",
        (environment_id,),
    )
    if not found:
        raise HTTPException(status_code=404, detail="Environment not found")
    row = found[0]
    if row["Status"] == "Destroying":
        raise HTTPException(status_code=409, detail="Destroy is already running")
    if not row["Slug"] or row["Status"] == "Destroyed":
        _purge_environment(environment_id)
        return Response(status_code=204)

    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        dispatch_destroy(row["Slug"], row["Name"], environment_id)
        status = "Running"
        message = "GitHub Actions destroy queued."
        environment_status = "Destroying"
    except GitHubError as exc:
        status = "Failed"
        message = str(exc)[:900]
        environment_status = "Failed"
    execute(
        "UPDATE dbo.Environment SET Status = %s WHERE EnvironmentId = %s",
        (environment_status, environment_id),
    )
    execute(
        """
        INSERT INTO dbo.DeploymentLog
            (DeploymentLogId, EnvironmentId, Action, Status, Message, LogText, StartedAt, FinishedAt)
        VALUES (%s, %s, N'Destroy', %s, %s, %s, %s, CASE WHEN %s = N'Failed' THEN %s ELSE NULL END)
        """,
        (log_id, environment_id, status, message, message, now, status, now),
    )
    return environment_detail(environment_id)


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
