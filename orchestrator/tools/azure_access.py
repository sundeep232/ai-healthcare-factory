"""Azure control/data-plane access needed by M3b to load a live demo.

* Key Vault: read the generated PostgreSQL admin password (never stored by the factory).
* ARM: fetch the Cosmos DB key, and open/close a PostgreSQL firewall rule for the machine
  running the factory. The rule exists only while data loads, then is deleted.

Auth uses ``DefaultAzureCredential`` (your ``az login``). Secrets live only in memory.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

ARM = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
PG_API = "2024-08-01"
COSMOS_API = "2024-05-15"
IP_LOOKUP_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com")
PG_ADMIN_SECRET = "pg-admin-password"


class AzureAccessError(RuntimeError):
    """Raised when an Azure call needed for data loading fails."""


class _Credential(Protocol):
    def get_token(self, *scopes: str) -> Any: ...


class _SecretClient(Protocol):
    def get_secret(self, name: str) -> Any: ...


def _default_credential() -> _Credential:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _default_secret_client(credential: _Credential) -> Callable[[str], _SecretClient]:
    from azure.keyvault.secrets import SecretClient

    return lambda vault: SecretClient(f"https://{vault}.vault.azure.net", credential)  # type: ignore[arg-type,return-value]


class AzureAccess:
    def __init__(
        self,
        subscription_id: str,
        *,
        credential: _Credential | None = None,
        http: httpx.Client | None = None,
        secret_client: Callable[[str], _SecretClient] | None = None,
        client_ip: str = "",
        sleep: Callable[[float], None] = time.sleep,
        poll_timeout: float = 240.0,
    ) -> None:
        self._sub = subscription_id  # validated on use so the API can start without it
        self._credential = credential
        self._http = http or httpx.Client(timeout=30.0)
        self._secret_client = secret_client
        self._client_ip = client_ip.strip()
        self._sleep = sleep
        self._poll_timeout = poll_timeout
        self.warnings: list[str] = []

    # -- secrets -----------------------------------------------------------

    def get_secret(self, vault_name: str, secret_name: str) -> str:
        try:
            factory = self._secret_client or _default_secret_client(self._cred())
            value = factory(vault_name).get_secret(secret_name).value
        except Exception as exc:  # noqa: BLE001 - SDK raises many distinct types
            raise AzureAccessError(
                f"could not read secret '{secret_name}' from Key Vault '{vault_name}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if not value:
            raise AzureAccessError(f"secret '{secret_name}' in Key Vault '{vault_name}' is empty")
        return str(value)

    def cosmos_primary_key(self, resource_group: str, account_name: str) -> str:
        self._need_subscription()
        url = (
            f"{ARM}/subscriptions/{self._sub}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.DocumentDB/databaseAccounts/{account_name}/listKeys?api-version={COSMOS_API}"
        )
        resp = self._arm("POST", url)
        key = resp.json().get("primaryMasterKey")
        if not key:
            raise AzureAccessError(f"Cosmos account '{account_name}' returned no primary key")
        return str(key)

    # -- firewall ----------------------------------------------------------

    def public_ip(self) -> str:
        """IPv4 address that Azure sees for this machine (configurable override first)."""
        if self._client_ip:
            return _ipv4(self._client_ip)
        errors: list[str] = []
        for url in IP_LOOKUP_URLS:
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                return _ipv4(resp.text.strip())
            except (httpx.HTTPError, AzureAccessError) as exc:
                errors.append(f"{url}: {exc}")
        raise AzureAccessError(
            "could not determine this machine's public IPv4 address "
            f"(set LOADER_CLIENT_IP to override): {'; '.join(errors)}"
        )

    @contextmanager
    def postgres_firewall_rule(
        self, resource_group: str, server_name: str, client_ip: str
    ) -> Iterator[str]:
        """Allow ``client_ip`` to reach the server for the duration of the block."""
        self._need_subscription()
        ip = _ipv4(client_ip)
        rule = f"factory-loader-{ip.replace('.', '-')}"
        url = (
            f"{ARM}/subscriptions/{self._sub}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.DBforPostgreSQL/flexibleServers/{server_name}/firewallRules/{rule}"
            f"?api-version={PG_API}"
        )
        self._wait(
            self._arm(
                "PUT", url, json={"properties": {"startIpAddress": ip, "endIpAddress": ip}}
            ),
            "open firewall rule",
        )
        try:
            yield rule
        finally:
            try:
                self._wait(self._arm("DELETE", url, ok=(200, 202, 204)), "close firewall rule")
            except AzureAccessError as exc:
                # Never mask the loader's own error; surface the leftover rule instead.
                message = (
                    f"firewall rule '{rule}' on '{server_name}' could not be removed ({exc}); "
                    "delete it manually"
                )
                logger.error(message)
                self.warnings.append(message)

    # -- internals ---------------------------------------------------------

    def _need_subscription(self) -> None:
        if not self._sub:
            raise AzureAccessError("AZURE_SUBSCRIPTION_ID is not set")

    def _cred(self) -> _Credential:
        if self._credential is None:
            self._credential = _default_credential()
        return self._credential

    def _arm(
        self, method: str, url: str, *, json: Any = None, ok: tuple[int, ...] = (200, 201, 202)
    ) -> httpx.Response:
        try:
            token = self._cred().get_token(ARM_SCOPE).token
            resp = self._http.request(
                method, url, json=json, headers={"Authorization": f"Bearer {token}"}
            )
        except Exception as exc:  # noqa: BLE001
            raise AzureAccessError(f"{method} {_redact(url)} failed: {type(exc).__name__}: {exc}") from exc
        if resp.status_code not in ok:
            raise AzureAccessError(
                f"{method} {_redact(url)} -> HTTP {resp.status_code}: {_error_text(resp)}"
            )
        return resp

    def _wait(self, resp: httpx.Response, what: str) -> None:
        """Follow an ARM long-running operation (202) to completion."""
        if resp.status_code != 202:
            return
        poll = resp.headers.get("Azure-AsyncOperation") or resp.headers.get("Location")
        if not poll:
            return
        deadline = time.monotonic() + self._poll_timeout
        delay = float(resp.headers.get("Retry-After", "2") or 2)
        while time.monotonic() < deadline:
            self._sleep(min(delay, 10.0))
            check = self._arm("GET", poll, ok=(200, 202, 204))
            if check.status_code == 204:
                return
            if check.status_code == 200:
                body = check.json() if check.content else {}
                state = str(body.get("status", "Succeeded"))
                if state == "Succeeded":
                    return
                if state in {"Failed", "Canceled"}:
                    raise AzureAccessError(f"{what} {state.lower()}: {body.get('error', '')}")
        raise AzureAccessError(f"timed out waiting to {what}")


def _ipv4(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value))
    except ValueError as exc:
        raise AzureAccessError(f"not a valid IPv4 address: {value!r}") from exc


def _redact(url: str) -> str:
    return url.split("?")[0]


def _error_text(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return f"{err.get('code', '')}: {err.get('message', '')}".strip(": ") or resp.text[:300]
    except ValueError:
        return resp.text[:300]
