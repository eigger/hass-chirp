"""Async client for the Chirp server's read API (``/api/v1``)."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

SUPPORTED_API_VERSION = 1
REQUEST_TIMEOUT = ClientTimeout(total=15)
# Host names and IPv4 addresses: letters, digits, dots, hyphens and underscores.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?$")


class ChirpError(Exception):
    """Base error for Chirp API failures."""


class ChirpAuthError(ChirpError):
    """The API key was rejected by the Chirp server."""


class ChirpConnectionError(ChirpError):
    """Chirp could not be reached or returned an unusable response."""


class ChirpInstanceMismatchError(ChirpError):
    """A different Chirp instance answered at the configured address."""


def _ipv6(value: str) -> str:
    try:
        address = ipaddress.IPv6Address(value)
    except ValueError:
        raise ValueError("Invalid IPv6 address") from None
    if address.scope_id:
        # Zone IDs (fe80::1%eth0) cannot be used in an HTTP URL host.
        raise ValueError("IPv6 zone IDs are not supported")
    return str(address)


def normalize_host(host: str) -> str:
    """Validate a bare host name or IP address and return it URL-ready.

    Raises ``ValueError`` for anything that is not a plain host (schemes,
    paths, queries, credentials or whitespace are rejected).
    """
    value = host.strip()
    if not value:
        raise ValueError("Host is required")
    if value.startswith("[") and value.endswith("]"):
        return f"[{_ipv6(value[1:-1])}]"
    if any(c in value for c in "/\\?#@[] \t\r\n"):
        raise ValueError("Host must not contain a scheme, path or credentials")
    if value.count(":") > 1:  # bare IPv6 literal
        return f"[{_ipv6(value)}]"
    if ":" in value:
        raise ValueError("Enter the port in the port field")
    if not _HOSTNAME_RE.match(value) or ".." in value:
        raise ValueError("Invalid host name")
    return value


def build_base_url(host: str, port: int, use_ssl: bool) -> str:
    """Return the dashboard/API base URL for a normalized host."""
    scheme = "https" if use_ssl else "http"
    default_port = 443 if use_ssl else 80
    suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{host}{suffix}"


class ChirpApi:
    """Thin wrapper around ``GET /api/v1/status`` and ``POST /api/v1/refresh``."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        api_key: str,
        use_ssl: bool = False,
    ) -> None:
        self._session = session
        self._base_url = build_base_url(normalize_host(host), int(port), use_ssl)
        self._headers = {"Authorization": f"Bearer {api_key.strip()}"}
        self._warned_version = False

    @property
    def base_url(self) -> str:
        """Return the server base URL."""
        return self._base_url

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch the latest status snapshot."""
        payload = await self._request("get", "/api/v1/status")
        self._validate_status(payload)
        return payload

    async def async_refresh(self) -> bool:
        """Ask the server to re-read SMART data.

        Returns ``True`` when the request was queued (202) and ``False`` when
        the server is in its cooldown window (429).
        """
        status = await self._request("post", "/api/v1/refresh", expect_json=False)
        return status != 429

    async def _request(
        self, method: str, path: str, *, expect_json: bool = True
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise ChirpAuthError("Chirp rejected the API key")
                if response.status == 429 and method == "post":
                    return 429
                response.raise_for_status()
                if not expect_json:
                    return response.status
                return await response.json()
        except ChirpError:
            raise
        except (ClientError, ValueError, TimeoutError) as err:
            # aiohttp exceptions can embed the URL or headers; report only a type.
            detail = (
                "timed out" if isinstance(err, TimeoutError) else type(err).__name__
            )
            raise ChirpConnectionError(f"Chirp request failed: {detail}") from None

    def _validate_status(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ChirpConnectionError("Chirp returned an invalid status response")
        api_version = payload.get("apiVersion")
        instance = payload.get("instance")
        if (
            not isinstance(api_version, int)
            or isinstance(api_version, bool)
            or not isinstance(instance, dict)
            or not instance.get("id")
            or not isinstance(payload.get("disks"), list)
        ):
            raise ChirpConnectionError("Chirp returned an invalid status response")
        if api_version > SUPPORTED_API_VERSION and not self._warned_version:
            self._warned_version = True
            _LOGGER.warning(
                "Chirp reports API version %s but this integration supports %s; "
                "some data may be missing. Update the Chirp integration",
                api_version,
                SUPPORTED_API_VERSION,
            )
        # Entities are keyed by the disk id, so drop disks without a usable one.
        payload["disks"] = [
            d
            for d in payload["disks"]
            if isinstance(d, dict) and isinstance(d.get("id"), str) and d["id"]
        ]
