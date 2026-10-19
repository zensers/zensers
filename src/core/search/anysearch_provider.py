"""AnySearch HTTP provider.

This module is only an adapter.  Routing, retries, caching, and local
fallbacks remain the responsibility of :mod:`src.core.search.gateway`.
"""

from __future__ import annotations

from typing import Any

import httpx
import time

from .gateway import SearchRequest
from .config import get_search_config


class SearchProviderError(RuntimeError):
    def __init__(self, message: str, *, category: str = "provider_error", status_code: int | None = None):
        # Never include response bodies: they may contain credentials or
        # provider-internal data.
        super().__init__(message[:300])
        self.category = category
        self.status_code = status_code


class AnySearchProvider:
    """Call AnySearch's public REST API with optional user/service auth."""

    name = "anysearch"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        client: Any | None = None,
        client_version: str = "1.0",
    ) -> None:
        config = get_search_config()
        self.api_key = api_key if api_key is not None else config.api_key
        self.base_url = (base_url or config.base_url).rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("AnySearch base URL must be an absolute HTTP(S) URL")
        self.timeout = max(1.0, float(timeout))
        self.client = client
        self.client_version = client_version

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Anysearch-Client": f"market-report/{self.client_version}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def search(self, request: SearchRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": request.normalized_query,
            "max_results": max(1, min(int(request.max_results), 10)),
        }
        if request.region:
            payload["zone"] = "cn" if request.region.startswith("cn") else "intl"
        # AnySearch's documented REST contract does not define generic
        # time_range/allowed_domains fields.  Do not send guessed fields;
        # vertical filters will be added through tag/params when supported.

        response = await self._post("/v1/search", payload)
        envelope = self._decode(response)
        data = envelope.get("data") or {}
        values = data.get("results") or []
        if not isinstance(values, list):
            raise SearchProviderError("AnySearch returned invalid results", category="provider_contract_error")
        results = []
        for item in values:
            if not isinstance(item, dict):
                continue
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet") or item.get("content") or "",
                "source": "anysearch",
                "published_at": item.get("published_at") or item.get("date"),
                "quality_score": float(item.get("quality_score", item.get("score", 60))),
            })
        return {"success": True, "results": results, "metadata": data.get("metadata") or {}}

    async def health_check(self) -> dict[str, Any]:
        """Return safe provider status; never return credentials or response bodies."""
        started = time.monotonic()
        try:
            if self.client is not None:
                response = await self.client.get(f"{self.base_url}/health", headers=self._headers(), timeout=self.timeout)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.base_url}/health", headers=self._headers())
            status = getattr(response, "status_code", 200)
            if status >= 400:
                category = "rate_limited" if status == 429 else "auth_error" if status in (401, 403) else "provider_error"
                return {"healthy": False, "provider": self.name, "error_class": category,
                        "latency_ms": round((time.monotonic() - started) * 1000, 2)}
            return {"healthy": True, "provider": self.name,
                    "latency_ms": round((time.monotonic() - started) * 1000, 2)}
        except httpx.TimeoutException:
            return {"healthy": False, "provider": self.name, "error_class": "transient_transport_error"}
        except httpx.HTTPError:
            return {"healthy": False, "provider": self.name, "error_class": "transient_transport_error"}

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            if self.client is not None:
                return await self.client.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise SearchProviderError("AnySearch request timed out", category="transient_transport_error") from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError("AnySearch transport failed", category="transient_transport_error") from exc

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        status = getattr(response, "status_code", 200)
        try:
            body = response.json()
        except Exception as exc:
            raise SearchProviderError("AnySearch returned invalid JSON", category="provider_contract_error", status_code=status) from exc
        if not isinstance(body, dict):
            raise SearchProviderError("AnySearch response must be an object", category="provider_contract_error", status_code=status)
        if status == 429 or body.get("code") == 429:
            raise SearchProviderError("AnySearch quota or rate limit reached", category="rate_limited", status_code=status)
        if status in (401, 403) or body.get("code") in (401, 403):
            raise SearchProviderError("AnySearch authentication or policy rejected the request", category="auth_error", status_code=status)
        if status >= 500:
            raise SearchProviderError("AnySearch service unavailable", category="transient_transport_error", status_code=status)
        if status >= 400 or body.get("code", 0) != 0:
            raise SearchProviderError("AnySearch rejected the request", category="provider_error", status_code=status)
        return body
