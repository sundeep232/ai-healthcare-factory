import json
import os
import re
import urllib.error
import urllib.request

WORKFLOW_FILE = "deploy-tenant.yml"
_SECRET = re.compile(
    r"(?i)(password|client_secret|access_token|authorization\s*[:=]\s*bearer)\s*[:=]?\s*\S+"
)


class GitHubError(RuntimeError):
    pass


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "sundeep232/ai-healthcare-factory").strip()


def _token() -> str:
    token = os.environ.get("GH_WORKFLOW_TOKEN", "").strip()
    if not token:
        raise GitHubError("GitHub Actions is not configured on the API")
    return token


def _request(method: str, path: str, body: dict | None = None, accept: str = "application/vnd.github+json"):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{_repo()}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ahf-control-plane",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            if not raw:
                return None
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(raw)
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = ""
        try:
            message = json.loads(detail).get("message", "")
        except json.JSONDecodeError:
            message = ""
        raise GitHubError(f"GitHub returned {exc.code}. {message}".strip()) from None


def dispatch_workflow(
    slug: str,
    display_name: str,
    environment_id: str,
    action: str,
    resources: list[str],
    synthetic_members: int,
) -> None:
    if action not in ("apply", "destroy"):
        raise GitHubError("Unsupported workflow action")
    _request(
        "POST",
        f"/actions/workflows/{WORKFLOW_FILE}/dispatches",
        {
            "ref": "main",
            "inputs": {
                "slug": slug,
                "display_name": display_name,
                "environment_id": environment_id,
                "action": action,
                "resources": json.dumps(resources, separators=(",", ":")),
                "synthetic_members": str(synthetic_members),
            },
        },
    )


def dispatch_deploy(
    slug: str,
    display_name: str,
    environment_id: str,
    resources: list[str],
    synthetic_members: int,
) -> None:
    dispatch_workflow(slug, display_name, environment_id, "apply", resources, synthetic_members)


def dispatch_destroy(
    slug: str,
    display_name: str,
    environment_id: str,
    resources: list[str],
    synthetic_members: int,
) -> None:
    dispatch_workflow(slug, display_name, environment_id, "destroy", resources, synthetic_members)


def find_run(environment_id: str, verb: str = "Deploy") -> int | None:
    payload = _request(
        "GET",
        f"/actions/workflows/{WORKFLOW_FILE}/runs?event=workflow_dispatch&per_page=20",
    )
    title = f"{verb} {environment_id}"
    for run in (payload or {}).get("workflow_runs", []):
        if run.get("display_title") == title:
            return int(run["id"])
    return None


def get_run(run_id: int) -> dict:
    payload = _request("GET", f"/actions/runs/{run_id}")
    return payload or {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _job_log(job_id: int) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{_repo()}/actions/jobs/{job_id}/logs",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ahf-control-plane",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=45) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            location = exc.headers.get("Location")
            if not location:
                return ""
            with urllib.request.urlopen(location, timeout=60) as downloaded:
                return downloaded.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            return ""
        raise GitHubError(f"GitHub returned {exc.code} for the job log") from None


def fetch_log(run_id: int) -> str:
    payload = _request("GET", f"/actions/runs/{run_id}/jobs")
    jobs = payload.get("jobs", []) if payload else []
    if not jobs:
        return "Workflow is queued. The log will appear when the job starts."
    parts = []
    for job in jobs:
        text = _job_log(int(job["id"]))
        if text.strip():
            parts.append(text)
    if not parts:
        return "Workflow is queued. The log will appear when the job starts."
    redacted = _SECRET.sub(r"\1=(redacted)", "\n".join(parts)).replace("\r\n", "\n")
    limit = 80000
    if len(redacted) <= limit:
        return redacted
    return "…earlier log omitted…\n" + redacted[-limit:]
