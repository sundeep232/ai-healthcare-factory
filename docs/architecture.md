# Architecture

## 1. High-Level Architecture

```
 Business User ──► React UI ──► FastAPI Orchestrator ──► Claude Sonnet 5.5
                                     │                    (+ capability catalog)
                                     ├──► Terraform (azurerm v4) ──► Azure
                                     ├──► Data Agents (5 domains) ──► Instance DBs
                                     └──► Blueprint / manifest storage
```

The orchestrator turns business intent into a versioned blueprint, has Claude
generate Terraform from it, applies it, loads synthetic data, validates the
result, and publishes a shareable demo link.

## 2. Component Inventory

### Shared (deployed once via `bootstrap/`)

| Component | Purpose |
|---|---|
| Resource group `rg-factory-shared` | Container for shared resources |
| Storage account + `tfstate` container | Remote Terraform state |
| Key Vault | Secrets (API keys, credentials) |
| Azure Container Registry | Images for orchestrator / demo apps |
| Cosmos DB | Blueprint, run, and manifest metadata |

### Per-instance (created per demo, `terraform/instances/<id>/`)

| Component | Purpose |
|---|---|
| Resource group | Isolation and one-step teardown |
| Application hosting | Demo app runtime |
| Databases | Synthetic healthcare data |
| Networking / identity | As required by the blueprint |

## 3. Data Flow: The 7 M-Stages

| Stage | Name | Input | Output |
|---|---|---|---|
| M1 | Interpret | Natural-language intent | Requirements JSON |
| M2 | Plan | Requirements JSON | Versioned Blueprint JSON |
| M3 | Generate | Blueprint | Terraform instance dir (Claude composes vetted modules) |
| M4 | Compose | HCL | Live Azure resources (`terraform apply`) |
| M3b | Data | Blueprint + live databases | Synthetic data for 5 domains |
| M5 | Certify | Live instance | Validation results + evidence |
| M6 | Publish | Evidence + resources | Final manifest + shareable link |
| M7 | Regenerate | Blueprint delta | Updated instance |

```
Intent → M1 → M2 → M3 → M4 → M3b → M5 → M6
                ▲                         │
                └────────── M7 ◄──────────┘ (blueprint delta)
```

**M3 design.** Claude never writes raw `resource` blocks. Each catalog capability has a reviewed module in `terraform/modules/<type>/`. Claude writes only `main.tf` (one `module` block per blueprint resource) and `outputs.tf`. Providers, backend, variables, naming suffix and tags come from `terraform/templates/`. Output is accepted only if it passes (1) composition rules (`orchestrator/tools/terraform_files.py`: one module per resource, correct source, dependencies visible, no GUIDs, no secret outputs) and (2) `terraform init -backend=false` + `terraform validate`. Failures go back to Claude as feedback (3 attempts). M3 never touches Azure; the state key is `instances/<slug>-<id8>-v<version>.tfstate`, with backend details supplied at `init` time by M4.

**M3b design (data agents).** Five domain generators in `orchestrator/agents/data_agents/` (Member, Provider, Claims, Authorization, Care Management) produce deterministic, referentially intact synthetic data. They are plain seeded Python, with no LLM calls, so runs are free and reproducible, and no real PHI can appear (`SYN-` ids, invalid `9XXXXXXXXX` NPIs, `@example.invalid` emails, `555-01XX` phones). Each domain has its own RNG stream (`"{seed}:{domain}"`), so enabling or disabling a domain never changes the others. `schema.py` is the single source of truth for Postgres DDL, Cosmos container mapping and tests.

Delivery is done by `SeederAgent` using connection details from the deterministic `factory_connections` output (rendered into every instance as `connections.tf`; Claude may not redefine it). Postgres admin password is read from the instance Key Vault and Cosmos keys via ARM, both with the orchestrator's `DefaultAzureCredential`. A temporary firewall rule `factory-loader-<ip>` is added for the load and always removed afterwards. Postgres loads run in one transaction (drop/create/`COPY`/index) so a failed reseed leaves previous data intact; Cosmos loads are idempotent upserts. Reference throughput: ~330k rows (250k claims) generate in ~5s and load into Postgres in ~5s locally.

API: `POST /api/demos/{id}/data/preview` (in-memory dry run, samples and counts) and `POST /api/demos/{id}/seed` (202, background, status `SEEDING`).

**M5 design (certify).** `CertifierAgent` checks the *live* instance against the blueprint and the seed facts, not against what was generated. Every check is the same shape: count the violations, pass at zero. Categories: deployment (resources and outputs exist), data (row counts match the seed; foreign keys hold within Postgres and across stores, e.g. Cosmos care documents to Postgres members), business rules (paid ≤ allowed ≤ billed, no negative amounts, dates in chronological order), synthetic-data safety (`.invalid` emails, `555-01XX` phones, `9XXXXXXXXX` NPIs, `SYN-` ids), security (TLS on database connections, no secret-shaped outputs, temporary loader firewall rules removed) and endpoints (reachable). Each result carries a public-safe `summary` and `evidence` plus an owner-only `detail` (server error text, passwords redacted) that never leaves the orchestrator. Connection resolution and table placement are shared with the seeder, so both agents agree on where data lives.

**M6 design (publish).** `build_manifest` builds the public `Manifest` from a strict allow-list: resources, tables with counts, public endpoints and check summaries, with no connection strings, keys, `detail` text or internal ids. Publishing requires a deployed, certified, passing demo whose data seed matches the certification. The share token is random and unguessable; only its SHA-256 is stored (`FilePublicationStore`, atomic writes), so the store cannot be used to recover a working link. Any change to the instance (deploy, seed, destroy) revokes the publication and clears the certification. With `SHARE_ONLY=true` the app mounts only `GET /api/shared/{token}` and the built UI: no admin routes, no cloud credentials needed, so it can be hosted separately from the orchestrator.

**UI.** React 19 + TypeScript + Vite (`ui/`). `stages.ts` is a pure state machine mapping a demo's status to its primary and secondary actions, with confirmation required for billable or destructive ones; it is unit-tested. A polling hook refreshes while a stage is running (`deploying`, `seeding`, `certifying`, `destroying`). Pages: demo list and intent form, demo detail (stepper, blueprint, data preview, certification audit, share link management) and the public share view. The API serves `ui/dist` with a client-routing fallback; missing `/assets/*` files return 404 rather than `index.html`.

API: `POST /api/demos/{id}/certify`, `GET /api/demos/{id}/manifest`, `POST /api/demos/{id}/publish` / `unpublish`, and the public `GET /api/shared/{token}`.
## 4. Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Strong AI/Azure SDK support, async, typed |
| AI | Claude Sonnet 5.5 | Strong structured output and code generation |
| IaC | Terraform, azurerm v4 | Declarative, reviewable, diffable (enables M7) |
| Cloud | Azure | Target environment for payer demos |
| Validation | Pydantic v2 | Typed schemas for requirements and blueprints |
| Frontend | React (Vite) | Business-user-friendly UI |
| Grounding | Capability catalog (RAG source) | Keeps Claude within supported Azure patterns |
