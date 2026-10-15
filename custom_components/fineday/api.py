"""Tiny client for the Fine Day api. No HA imports so I can poke it from a script."""

from __future__ import annotations

from typing import Any

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=20)


class FineDayError(Exception):
    pass


class FineDayAuthError(FineDayError):
    """bad / revoked key"""


class FineDayAddressError(FineDayError):
    """403 - key's locked to another address, or used from too many today"""


class FineDayLimitError(FineDayError):
    """out of requests for today (429), or server is over its budget (503)"""


class FineDayApi:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._key = api_key.strip()

    async def _get(self, path: str, params: dict[str, Any] | None = None, *, keyed: bool = True) -> dict[str, Any]:
        headers = {"X-API-Key": self._key} if keyed else {}
        try:
            async with self._session.get(f"{self._base}{path}", params=params, headers=headers, timeout=TIMEOUT) as resp:
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise FineDayError(f"weird reply from server (HTTP {resp.status})") from err
                if not isinstance(body, dict):
                    raise FineDayError(f"weird reply from server (HTTP {resp.status})")

                msg = body.get("message") or body.get("error") or f"HTTP {resp.status}"
                if resp.status == 401:
                    raise FineDayAuthError(msg)
                if resp.status == 403:
                    raise FineDayAddressError(msg)
                if resp.status in (429, 503):
                    raise FineDayLimitError(msg)
                if resp.status != 200 or not body.get("success"):
                    raise FineDayError(msg)
                return body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FineDayError(f"can't reach the Fine Day server: {err}") from err

    async def health(self) -> bool:
        await self._get("/v1/health", keyed=False)  # doesn't need a key
        return True

    async def search(self, query: str) -> list[dict[str, Any]]:
        body = await self._get("/v1/search", {"q": query})
        return list(body.get("results", []))

    async def nearest(self, lat: float, lon: float) -> list[dict[str, Any]]:
        # closest places to a point, nearest first. only ever send it rounded (~1km)
        body = await self._get("/v1/search", {"lat": f"{lat:.2f}", "lon": f"{lon:.2f}"})
        return list(body.get("results", []))

    async def forecast(self, lat: float, lon: float, name: str | None, daylight_only: bool = True) -> dict[str, Any]:
        params = {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "daylight": "1" if daylight_only else "0"}
        if name:
            params["name"] = name
        body = await self._get("/v1/forecast", params)
        return {"forecast": body["forecast"], "meta": body.get("meta", {})}
