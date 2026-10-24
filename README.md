# ?? AI-Driven Healthcare Platform Factory

> From business intent to live demo in 15 minutes

![Status](https://img.shields.io/badge/status-MVP%20%2F%20Phase%200-orange)
![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)
![Azure](https://img.shields.io/badge/cloud-Azure-0078D4?logo=microsoftazure&logoColor=white)
![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet%205.5-D97757)

AI platform that creates healthcare payer demo environments on Azure in minutes, not months.

## What it does

- **Understands plain English.** Product managers, sales engineers, and BAs describe the demo they want. No code or cloud knowledge needed.
- **Builds it on Azure automatically.** The platform plans, writes the infrastructure code, and deploys it.
- **Fills it with realistic data.** It loads synthetic (never real) payer data and hands back a shareable link.

## How it works

```
M1 Interpret ? M2 Plan ? M3 Generate ? M4 Compose ? M3b Data ? M5 Certify ? M6 Publish
                                                                                 �
                                                          M7 Regenerate ?--------+
```

| Stage | Name | What happens |
|---|---|---|
| M1 | Interpret | Natural language intent ? Requirements JSON |
| M2 | Plan | Requirements ? Versioned Blueprint JSON |
| M3 | Generate | Blueprint ? Terraform (Claude composes vetted modules; `python scripts/run_m3.py <blueprint.json>`) |
| M4 | Compose | `terraform apply` ? live Azure resources |
| M3b | Data | Synthetic data for 5 healthcare domains |
| M5 | Certify | Validation + evidence |
| M6 | Publish | Final manifest + shareable demo link |
| M7 | Regenerate | Blueprint delta ? updated instance |

## Healthcare domains

1. ?? Member
2. ?? Provider
3. ?? Claims
4. ? Authorization
5. ?? Care Management

## Architecture

```
+----------+   +----------------+   +-------------------+
� React UI �--?� FastAPI        �--?� Claude Sonnet 5.5 �
�          �   � Orchestrator   �   � + Capability Cat. �
+----------+   +----------------+   +-------------------+
                       �
        +--------------+---------------+
        ?              ?               ?
  +-----------+  +------------+  +-------------+
  � Terraform �  � Data Agents�  � Blueprint & �
  � (azurerm4)�  � (5 domains)�  � Manifest    �
  +-----------+  +------------+  � Storage     �
        ?              ?         +-------------+
   +--------------------------+
   � Azure: per-demo instance �
   +--------------------------+
```

See [docs/architecture.md](docs/architecture.md) for details.

## Repository structure

```
ai-healthcare-factory/
+-- .github/workflows/      # CI/CD
+-- bootstrap/              # Shared Azure Terraform (one-time)
+-- blueprints/             # Example blueprint JSONs
+-- capability-catalog/     # RAG source for Claude
+-- docs/                   # Architecture and design docs
+-- orchestrator/           # Python/FastAPI backend
�   +-- agents/
�   �   +-- data_agents/    # Member, Provider, Claims, Auth, Care Mgmt
�   +-- prompts/
�   +-- routes/
�   +-- schemas/
�   +-- storage/
�   +-- tests/
�   +-- tools/
+-- scripts/
+-- terraform/
�   +-- instances/          # Generated per-demo (git-ignored)
�   +-- modules/
�   +-- templates/
+-- ui/                     # React frontend
```

## 8-week MVP roadmap

| Week | Milestone | Status |
|---|---|---|
| 1 | Scaffolding + Claude integration | ? Done |
| 2 | Azure bootstrap (shared resources) | ? Done |
| 3 | M1 Interpret + M2 Plan | ? Done |
| 4 | M3 Generate (Terraform modules + composer) | ? Done |
| 5 | M4 Compose + FastAPI routes | ? Done (apply not yet run end to end) |
| 6 | M3b Data agents (5 domains) | ✅ Done (live Azure seed not yet run end to end)
| 7 | M5 Certify + M6 Publish + UI | ? Planned |
| 8 | M7 Regenerate + hardening + demo | ? Planned |

## Run the API

```powershell
uvicorn orchestrator.app:create_app --factory --host 127.0.0.1 --port 8000   # docs at /docs
```

Bind to `127.0.0.1` only: there is no authentication yet, and `deploy` creates billable Azure resources.

| Call | Stage | Effect |
|---|---|---|
| `POST /api/demos {"intent": "..."}` | M1 + M2 | Requirements + blueprint (token cost only) |
| `POST /api/demos/{id}/generate` | M3 | Validated Terraform on disk |
| `POST /api/demos/{id}/plan` | M4 dry run | `terraform plan`, creates nothing |
| `POST /api/demos/{id}/deploy {"confirm": true}` | M4 | `terraform apply` in the background (billable) |
| `POST /api/demos/{id}/destroy {"confirm": true}` | M4 | Tear everything down |
| `GET /api/demos/{id}` / `/logs` | | Status, outputs, Terraform log tail |

Demo records are stored as JSON in `.factory-data/` (git-ignored). Deploy refuses any plan that would delete resources.
## Tech stack

- **Backend:** Python 3.11, FastAPI, Pydantic v2
- **AI:** Claude Sonnet 5.5 (Anthropic API)
- **IaC:** Terraform (azurerm provider v4)
- **Cloud:** Microsoft Azure
- **Frontend:** React

## Getting started

?? Coming soon.

---

> *"Describe a demo. We build it."*
