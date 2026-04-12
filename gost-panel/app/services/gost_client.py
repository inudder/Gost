from __future__ import annotations

from typing import Any

import httpx


class GostApiError(RuntimeError):
    """Raised when the GOST API cannot be reached or parsed."""


class GostApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _build_url(self, suffix: str = "") -> str:
        if self.base_url.endswith("/config"):
            return f"{self.base_url}{suffix}"
        return f"{self.base_url}/config{suffix}"

    def _build_auth(self) -> httpx.BasicAuth | None:
        if self.username:
            return httpx.BasicAuth(self.username, self.password or "")
        return None

    async def _get_json(self, suffix: str = "") -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(self._build_url(suffix), auth=self._build_auth())
            response.raise_for_status()
            return response.json()

    async def ping(self) -> dict[str, Any]:
        try:
            payload = await self._get_json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GostApiError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise GostApiError("Unexpected /config response.")
        return payload

    async def fetch_config(self) -> dict[str, Any]:
        return await self.ping()

    async def fetch_services(self) -> list[dict[str, Any]]:
        try:
            payload = await self._get_json("/services")
        except (httpx.HTTPError, ValueError) as exc:
            raise GostApiError(str(exc)) from exc

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            services = payload.get("services")
            if isinstance(services, list):
                return [item for item in services if isinstance(item, dict)]
            data = payload.get("data")
            if isinstance(data, dict):
                nested_services = data.get("services")
                if isinstance(nested_services, list):
                    return [item for item in nested_services if isinstance(item, dict)]
                items = data.get("list")
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        raise GostApiError("Unexpected /config/services response.")
