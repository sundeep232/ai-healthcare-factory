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
