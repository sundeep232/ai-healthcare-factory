"""Natural-language access to one payer demo database."""

import json
import os
import re
import time
import urllib.request
from typing import Literal
from urllib.error import HTTPError

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from data import (
    portal_authorization,
    portal_authorizations,
    portal_care,
    portal_claim,
    portal_claims,
    portal_member,
    portal_members,
    portal_summary,
    run_tool,
)

app = FastAPI(title="Payer demo agent")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.azurestaticapps\.net",
    allow_methods=["*"],
    allow_headers=["*"],
)

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "find_members",
            "description": "Find members by name or member number. Leave both empty to list a sample of members.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "member_number": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "member_claims",
            "description": "List claims for a member id or for everyone matching a name. Status is Paid, Denied, Pending, or Adjusted. Use the name when the user asks to summarize claims for a last name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "member_authorizations",
            "description": "List a member's authorizations. Status is Approved, Pending, or Denied.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "member_care",
            "description": "List care-management enrollments for a member.",
            "parameters": {
                "type": "object",
                "properties": {"member_id": {"type": "string"}},
                "required": ["member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio",
            "description": "Counts for the whole demo: members, claim statuses, authorization statuses, care programs, and top diagnoses.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _complete(messages: list[dict]) -> dict:
    endpoint = os.environ["OPENAI_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("OPENAI_DEPLOYMENT", "chat")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=2024-10-21"
    body = json.dumps({
        "messages": messages,
        "tools": TOOL_SCHEMA,
        "max_completion_tokens": 4000,
    }).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"api-key": os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            exc.read()
            if exc.code == 429 and attempt < 3:
                time.sleep(8)
                continue
            if exc.code == 429:
                raise HTTPException(status_code=429, detail="The language model is busy. Ask again in a moment.") from None
            raise HTTPException(status_code=502, detail="The language model could not answer.") from None
    raise HTTPException(status_code=429, detail="The language model is busy. Ask again in a moment.") from None


def _text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""


def answer(question: str, spoken: bool, history: list[dict] | None = None, context: str = "") -> str:
    demo = os.environ.get("DEMO_NAME", "this payer demo")
    style = "Answer in one or two short spoken sentences." if spoken else "Answer in a short paragraph a provider service agent can read."
    messages = [
        {
            "role": "system",
            "content": (
                f"You answer questions about synthetic payer data for {demo}. "
                "Use the tools. Do not invent members, claims, amounts, or statuses. "
                "If a tool returns no rows, say that. "
                "When this conversation already identified a member, use that member_id. "
                "If the user asks for claims, authorizations, or care, call that tool now. "
                "Do not ask for the name or member number again. "
                "To list members with no name, call find_members with an empty name. "
                "To summarize claims for a last name, call member_claims with that name. "
                f"{style}"
            ),
        },
    ]
    if context.strip():
        messages.append({
            "role": "system",
            "content": "The provider has this record open. Use the tools and do not invent fields that are not here. " + context.strip(),
        })
    for turn in history or []:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    for _ in range(4):
        payload = _complete(messages)
        message = payload["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            text = _text(message)
            if text:
                return text
            return "I could not finish that question. Ask again."
        messages.append(message)
        for call in calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(run_tool(name, arguments)),
            })
    return "I could not finish that question from the demo data."


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class Question(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=8)
    context: str = Field(default="", max_length=2000)


@app.get("/health")
def health():
    return {
        "ok": True,
        "speech": bool(os.environ.get("SPEECH_KEY", "").strip()),
        "name": os.environ.get("DEMO_NAME", "Payer demo"),
    }


def _history(body: Question) -> list[dict]:
    return [{"role": turn.role, "content": turn.content.strip()} for turn in body.history]


_RECORD_ID = re.compile(r"^[A-Za-z0-9]{3,40}$")
_CLAIM_STATUS = {"", "Paid", "Denied", "Pending", "Adjusted"}
_AUTH_STATUS = {"", "Approved", "Pending", "Denied"}


def _record_id(value: str) -> str:
    if not _RECORD_ID.fullmatch(value or ""):
        raise HTTPException(status_code=400, detail="Record id is not valid")
    return value


def _portal_body(result: dict):
    error = result.get("error")
    if error:
        status = 404 if error.endswith("not found") else 400
        raise HTTPException(status_code=status, detail=error)
    return result


@app.get("/portal/summary")
def summary():
    return portal_summary()


@app.get("/portal/claims")
def claims(q: str = "", status: str = ""):
    if status not in _CLAIM_STATUS:
        raise HTTPException(status_code=400, detail="Unknown claim status")
    return portal_claims(q, status)


@app.get("/portal/claims/{claim_id}")
def claim(claim_id: str):
    return _portal_body(portal_claim(_record_id(claim_id)))


@app.get("/portal/authorizations")
def authorizations(q: str = "", status: str = ""):
    if status not in _AUTH_STATUS:
        raise HTTPException(status_code=400, detail="Unknown authorization status")
    return portal_authorizations(q, status)


@app.get("/portal/authorizations/{authorization_id}")
def authorization(authorization_id: str):
    return _portal_body(portal_authorization(_record_id(authorization_id)))


@app.get("/portal/members")
def members(q: str = ""):
    return portal_members(q)


@app.get("/portal/members/{member_id}")
def member(member_id: str):
    return _portal_body(portal_member(_record_id(member_id)))


@app.get("/portal/care")
def care(q: str = ""):
    return portal_care(q)


@app.post("/chat")
def chat(body: Question):
    return {"answer": answer(body.message.strip(), spoken=False, history=_history(body), context=body.context)}


@app.post("/voice")
def voice(body: Question):
    return {"answer": answer(body.message.strip(), spoken=True, history=_history(body), context=body.context)}


@app.post("/speech/token")
def speech_token():
    key = os.environ.get("SPEECH_KEY", "").strip()
    region = os.environ.get("SPEECH_REGION", "").strip()
    if not key or not region:
        raise HTTPException(status_code=404, detail="Voice is not enabled for this demo")
    request = urllib.request.Request(
        f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
        data=b"",
        headers={"Ocp-Apim-Subscription-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            token = response.read().decode()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Speech token failed with {exc.code}") from None
    return {"token": token, "region": region}
