"""Natural-language access to one payer demo database."""

import json
import os
import urllib.request
from urllib.error import HTTPError

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data import run_tool

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
            "description": "Find members by name or member number. Use this before asking about a person's claims.",
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
            "description": "List a member's claims. Status is Paid, Denied, Pending, or Adjusted.",
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
        "max_completion_tokens": 700,
    }).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"api-key": os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(status_code=502, detail=f"The language model returned {exc.code}. {detail}") from None


def answer(question: str, spoken: bool) -> str:
    demo = os.environ.get("DEMO_NAME", "this payer demo")
    style = "Answer in one or two short spoken sentences." if spoken else "Answer in a short paragraph a provider service agent can read."
    messages = [
        {
            "role": "system",
            "content": (
                f"You answer questions about synthetic payer data for {demo}. "
                "Use the tools. Do not invent members, claims, amounts, or statuses. "
                "If a tool returns no rows, say that. "
                f"{style}"
            ),
        },
        {"role": "user", "content": question},
    ]
    for _ in range(4):
        payload = _complete(messages)
        message = payload["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            return (message.get("content") or "").strip() or "I could not find that in the demo data."
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


class Question(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {
        "ok": True,
        "speech": bool(os.environ.get("SPEECH_KEY", "").strip()),
        "name": os.environ.get("DEMO_NAME", "Payer demo"),
    }


@app.post("/chat")
def chat(body: Question):
    return {"answer": answer(body.message.strip(), spoken=False)}


@app.post("/voice")
def voice(body: Question):
    return {"answer": answer(body.message.strip(), spoken=True)}


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
