"""M6 Publish: turn a certified demo into a read-only, secret-free share page.

The manifest is built from an allow-list of fields. Nothing is copied wholesale from the
Demo record, so a field added there later can never leak onto the public page by accident.
Hostnames, resource-group names, credentials, row contents and certification ``detail``
text (owner diagnostics) are never published.
"""

from __future__ import annotations

import secrets

from orchestrator.agents.data_agents.schema import TABLES
from orchestrator.schemas.certification import (
    Manifest,
    ManifestCertification,
    ManifestCheck,
    ManifestEndpoint,
    ManifestResource,
    ManifestTable,
    Publication,
)
from orchestrator.schemas.demo import Demo, DemoStatus
from orchestrator.storage import InvalidTransitionError
from orchestrator.storage.publication_store import PublicationStore
from orchestrator.tools.outputs import public_endpoints


def check_publishable(demo: Demo) -> None:
    """Raise InvalidTransitionError (with an actionable message) unless the demo may be shared."""
    if demo.status != DemoStatus.DEPLOYED:
        raise InvalidTransitionError(f"demo is '{demo.status.value}'; only a deployed demo can be published")
    if demo.blueprint is None or demo.requirements is None:
        raise InvalidTransitionError("demo has no blueprint yet")
    cert = demo.certification
    if cert is None:
        raise InvalidTransitionError("demo is not certified; run certify first")
    if not cert.passed:
        raise InvalidTransitionError("certification did not pass; fix the failed checks and certify again")
    if demo.data is None or cert.data_seed != demo.data.seed:
        raise InvalidTransitionError("the data changed since certification; certify again")


def build_manifest(demo: Demo) -> Manifest:
    check_publishable(demo)
    assert demo.blueprint and demo.requirements and demo.certification
    req, bp, cert = demo.requirements, demo.blueprint, demo.certification

    order = {name: i for i, name in enumerate(TABLES)}
    tables = sorted(
        (ManifestTable(name=name, rows=rows) for t in (demo.data.targets if demo.data else []) for name, rows in t.tables.items()),
        key=lambda t: order.get(t.name, len(order)),
    )
    return Manifest(
        demo_id=demo.demo_id,
        demo_name=req.demo_name,
        summary=bp.summary,
        intent=demo.intent,
        target_audience=req.target_audience,
        business_goals=list(req.business_goals),
        region=req.azure_region,
        blueprint_version=bp.version,
        resources=[
            ManifestResource(id=r.id, type=r.type, name=r.name, purpose=r.purpose, sku=r.sku)
            for r in bp.resources
        ],
        endpoints=[ManifestEndpoint(name=k, url=v) for k, v in public_endpoints(demo.outputs).items()],
        data_as_of=demo.data.as_of if demo.data else None,
        data_seed=demo.data.seed if demo.data else None,
        domains=[d.value for d in req.domains],
        tables=tables,
        certification=ManifestCertification(
            passed=cert.passed,
            certified_at=cert.certified_at,
            summary=cert.summary,
            checks=[
                ManifestCheck(
                    id=c.id, category=c.category, title=c.title, status=c.status,
                    summary=c.summary, evidence=dict(c.evidence),
                )
                for c in cert.checks
            ],
        ),
    )


class Publisher:
    def __init__(self, store: PublicationStore, *, public_base_url: str = "") -> None:
        self._store = store
        self._base = public_base_url.rstrip("/")

    def preview(self, demo: Demo) -> Manifest:
        """The manifest that publishing would produce right now. Stores nothing."""
        return build_manifest(demo)

    def publish(self, demo: Demo) -> tuple[Publication, Manifest]:
        """Create the share link, or refresh the snapshot behind the existing one (same URL)."""
        manifest = build_manifest(demo)
        token = demo.publication.token if demo.publication else secrets.token_urlsafe(24)
        self._store.put(token, manifest)
        path = f"/share/{token}"
        return (
            Publication(
                token=token,
                published_at=manifest.published_at,
                share_path=path,
                share_url=f"{self._base}{path}" if self._base else path,
            ),
            manifest,
        )

    def read(self, token: str) -> Manifest | None:
        return self._store.get(token)

    def revoke(self, token: str) -> None:
        self._store.delete(token)
