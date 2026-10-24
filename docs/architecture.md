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
| M3 | Generate | Blueprint | Terraform HCL (written by Claude) |
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

**Data agents (M3b):** Member, Provider, Claims, Authorization, Care Management.

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
