"""Application settings, loaded from the project-root .env (and process env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = parent of the orchestrator/ package.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH: Path = PROJECT_ROOT / "capability-catalog" / "capabilities.json"

# Terraform layout. Instances live two levels below terraform/, so generated code
# can reference modules as "../../modules/<type>".
TERRAFORM_DIR: Path = PROJECT_ROOT / "terraform"
MODULES_DIR: Path = TERRAFORM_DIR / "modules"
TEMPLATES_DIR: Path = TERRAFORM_DIR / "templates"
INSTANCES_DIR: Path = TERRAFORM_DIR / "instances"
# Shared provider download cache so repeated `terraform init` runs are fast.
TF_PLUGIN_CACHE_DIR: Path = PROJECT_ROOT / ".terraform-cache"


class Settings(BaseSettings):
    """Typed view of the environment. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds Azure/Terraform values we don't model here
    )

    claude_api_key: SecretStr = Field(..., description="Anthropic API key.")
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = Field(4096, ge=256, le=64_000)

    # Region of the shared bootstrap resources (state, Key Vault, ACR, Cosmos).
    azure_location: str = "eastus2"
    # Default region for demo instances. Separate because services can be restricted per
    # region per subscription: here PostgreSQL Flexible Server is blocked in eastus2/eastus/
    # westus2/westeurope but works in centralus, which also supports Static Web Apps.
    demo_location: str = "centralus"
    # Needed by M4 (Compose). Filled from bootstrap outputs by scripts/sync-env-from-bootstrap.ps1.
    azure_subscription_id: str = ""
    tfstate_storage_account: str = ""
    tfstate_container: str = "tfstate"
    tfstate_resource_group: str = "rg-factory-shared"
    # M3b: public IPv4 of this machine, if auto-detection (api.ipify.org) is blocked.
    loader_client_ip: str = ""
    # Where the API keeps demo records (JSON files). Git-ignored.
    data_dir: Path = PROJECT_ROOT / ".factory-data"
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance (reads .env once)."""
    return Settings()  # type: ignore[call-arg]  # required fields come from env
