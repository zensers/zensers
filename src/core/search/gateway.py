"""Task-scoped search gateway.

The gateway owns request normalization, result normalization, quality gating,
bounded retries, provider fallback, and task-local single-flight caching.
Provider implementations only need an async ``search(request)`` method.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchRequest:
    query: str
    objective: str | None = None
    region: str = "cn-cn"
    time_range: str | None = None
    depth: str = "auto"
    max_results: int = 8
    livecrawl: str = "fallback"
    allowed_domains: list[str] | None = None
    query_revision: int = 0
    provider_capability_version: str | None = None
    # Search is independent from the configured LLM and its billing.
    source_mode: str = "provider_pool"

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split())

    def normalized_domains(self) -> tuple[str, ...] | None:
        if self.allowed_domains is None:
            return None
        domains = {domain.strip().lower().rstrip(".") for domain in self.allowed_domains if domain.strip()}
        return tuple(sorted(domains))

    def cache_key(self, provider: str | None = None, routing_policy_version: str = "v1") -> tuple[Any, ...]:
        return (
            self.normalized_query,
            self.objective,
            self.region,
            self.time_range,
            self.normalized_domains(),
            self.depth,
            self.max_results,
            self.livecrawl,
            self.query_revision,
            provider,
            self.provider_capability_version,
            routing_policy_version,
            self.source_mode,
        )


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    published_at: str | None = None
    quality_score: float = 0.0
    # Evidence identity is created at the gateway boundary so downstream
    # report code never has to infer provenance from a display title.
    evidence_id: str = ""
    provenance_id: str = ""
    excerpt: str = ""
    locator: str = ""
    task_id: str = ""
    request_id: str = ""
    retrieved_at: str | None = None


@dataclass
class SearchResponse:
    schema_version: str
    request_id: str
    task_id: str
    intent_id: str | None
    success: bool
    results: list[SearchResult]
    provider: str
    provider_status: dict[str, Any]
    quality_score: float
    source_count: int
    high_quality_count: int
    retries: int
    cache_hit: bool
    estimated_cost: float | None
    fetched_at: datetime
    warning: str | None = None
    stop_reason: str | None = None
    fallback_attempted: bool = False

    @property
    def error_class(self) -> str | None:
        return self.provider_status.get("error_class")

    @property
    def message(self) -> str | None:
        return self.provider_status.get("message")


class SearchProvider(Protocol):
    async def search(self, request: SearchRequest) -> Any: ...


class LocalSkillProvider:
    """Adapt an existing ``search_skill`` to the Gateway provider contract."""

    def __init__(self, skill: Any, name: str = "legacy") -> None:
        self.skill = skill
        self.name = name

    async def search(self, request: SearchRequest) -> Any:
        kwargs = {
            "query": request.normalized_query,
            "max_results": request.max_results,
            "region": request.region,
            "time_range": request.time_range,
            "enable_quality_filter": True,
            "min_quality_score": 0,
        }
        if request.allowed_domains:
            kwargs["site"] = request.allowed_domains[0]
        return await self.skill.execute(**kwargs)


# Backward-compatible import for existing callers during migration.
LegacySkillProvider = LocalSkillProvider


class GatewaySearchSkillAdapter:
    """Expose a Gateway as the legacy dict-returning skill interface."""

    def __init__(
        self,
        gateway: "SearchGateway",
        intent_id: str | None = None,
        scope: str = "default",
    ) -> None:
        self.gateway = gateway
        self.intent_id = intent_id
        self.scope = scope

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        request = SearchRequest(
            query=str(kwargs.get("query", "")),
            objective=kwargs.get("objective"),
            region=kwargs.get("region", "cn-cn"),
            time_range=kwargs.get("time_range"),
            depth=kwargs.get("depth", "auto"),
            max_results=int(kwargs.get("max_results", 8)),
            livecrawl=kwargs.get("livecrawl", "fallback"),
            allowed_domains=kwargs.get("allowed_domains"),
            query_revision=int(kwargs.get("query_revision", 0)),
            provider_capability_version=kwargs.get("provider_capability_version"),
            source_mode=kwargs.get("source_mode", "provider_pool"),
        )
        response = await self.gateway.search(
            request,
            scope=str(kwargs.get("scope", self.scope)),
            intent_id=self.intent_id,
        )
        data = asdict(response)
        data["results"] = [asdict(result) for result in response.results]
        data["total"] = len(response.results)
        data["query"] = request.normalized_query
        data["message"] = response.warning or ("Search completed" if response.success else "Search failed")
        data["error_class"] = response.error_class
        data["provider"] = response.provider
        return data


@dataclass
class _CacheEntry:
    created_at: float
    response: SearchResponse


@dataclass
class BudgetState:
    """Mutable task budget counters; the lock is owned by SearchGateway."""

    task_id: str
    task_max_searches: int | None
    task_used_searches: int = 0
    scope_used_searches: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    anysearch_calls: int = 0
    fallback_calls: int = 0
    provider_attempts: int = 0
    provider_retries: int = 0
    stop_reason: str | None = None


class SearchGateway:
    """A single task's shared gateway and bounded provider router."""

    SCHEMA_VERSION = "1.0"
    # ``research`` and ``repair`` are retained for older direct callers and
    # tests; all production entry points use the named scopes below.
    KNOWN_SCOPES = frozenset({
        "default", "research", "repair", "conversation.web_search",
        "conversation.news_search", "generic_agent", "execution_engine",
        "report_repair", "conflict_resolver", "ppt_supplement",
        "data_collection", "report_generation", "report_revision",
    })

    def __init__(
        self,
        *,
        task_id: str,
        providers: Mapping[str, SearchProvider],
        primary_provider: str,
        fallback_providers: list[str] | None = None,
        task_max_searches: int | None = None,
        default_scope_max_searches: int | None = None,
        scope_max_searches: Mapping[str, int] | None = None,
        quality_threshold: float | None = None,
        cache_ttl_seconds: float = 900,
        min_quality_score: float | None = None,
        max_provider_retries: int = 2,
        max_provider_switches: int = 2,
        routing_policy_version: str = "v1",
    ) -> None:
        if primary_provider not in providers:
            raise ValueError(f"unknown primary provider: {primary_provider}")
        self.task_id = task_id
        self.providers = dict(providers)
        self.primary_provider = primary_provider
        self.fallback_providers = list(fallback_providers or [])
        if task_max_searches is not None and int(task_max_searches) < 0:
            raise ValueError("task_max_searches must be non-negative")
        if default_scope_max_searches is not None and int(default_scope_max_searches) < 0:
            raise ValueError("default_scope_max_searches must be non-negative")
        self.default_scope_max_searches = (
            int(default_scope_max_searches)
            if default_scope_max_searches is not None else None
        )
        self.scope_max_searches = {
            str(scope): int(limit)
            for scope, limit in (scope_max_searches or {}).items()
        }
        if any(limit < 0 for limit in self.scope_max_searches.values()):
            raise ValueError("scope_max_searches values must be non-negative")
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        # Keep the old name as a migration alias. New callers must use
        # quality_threshold; both values describe the same 0-100 scale here.
        if quality_threshold is not None and min_quality_score is not None:
            if float(quality_threshold) != float(min_quality_score):
                raise ValueError("quality_threshold and min_quality_score disagree")
        self.quality_threshold = float(
            quality_threshold if quality_threshold is not None
            else (min_quality_score if min_quality_score is not None else 70)
        )
        self.min_quality_score = self.quality_threshold
        self.max_provider_retries = max(0, int(max_provider_retries))
        self.max_provider_switches = max(0, int(max_provider_switches))
        self.routing_policy_version = routing_policy_version
        self._cache: dict[tuple[Any, ...], _CacheEntry] = {}
        self._locks: dict[tuple[Any, ...], asyncio.Lock] = {}
        self._lock_guard = asyncio.Lock()
        self._budget_lock = asyncio.Lock()
        self.budget = BudgetState(task_id=task_id, task_max_searches=task_max_searches)
        self._request_counter = 0

    async def _lock_for(self, key: tuple[Any, ...]) -> asyncio.Lock:
        async with self._lock_guard:
            return self._locks.setdefault(key, asyncio.Lock())

    def _request_id(self) -> str:
        self._request_counter += 1
        return f"{self.task_id}:search:{self._request_counter}"

    def _cache_key(self, request: SearchRequest, provider: str) -> tuple[Any, ...]:
        return request.cache_key(provider, self.routing_policy_version)

    def _cached(self, key: tuple[Any, ...]) -> SearchResponse | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if self.cache_ttl_seconds <= 0 or time.monotonic() - entry.created_at >= self.cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        response = copy.deepcopy(entry.response)
        response.cache_hit = True
        return response

    def _scope_limit(self, scope: str) -> int | None:
        if not scope or not isinstance(scope, str):
            raise ValueError("scope is required")
        if scope not in self.KNOWN_SCOPES and scope not in self.scope_max_searches:
            raise ValueError(f"unknown search scope: {scope}")
        if scope in self.scope_max_searches:
            return self.scope_max_searches[scope]
        return self.default_scope_max_searches

    async def _reserve(self, scope: str) -> SearchResponse | None:
        limit = self._scope_limit(scope)
        async with self._budget_lock:
            if self.budget.task_max_searches is not None and self.budget.task_used_searches >= self.budget.task_max_searches:
                self.budget.stop_reason = "max_searches_reached"
                return self._response(
                    None, None, self.primary_provider, False, [], 0,
                    {"error_class": "budget_exhausted", "message": "task search budget exhausted"},
                    stop_reason="max_searches_reached",
                )
            used = self.budget.scope_used_searches.get(scope, 0)
            if limit is not None and used >= limit:
                self.budget.stop_reason = "max_searches_reached"
                return self._response(
                    None, None, self.primary_provider, False, [], 0,
                    {"error_class": "budget_exhausted", "message": f"scope search budget exhausted: {scope}"},
                    stop_reason="max_searches_reached",
                )
            self.budget.task_used_searches += 1
            self.budget.scope_used_searches[scope] = used + 1
            return None

    async def search(
        self,
        request: SearchRequest,
        *,
        scope: str = "default",
        intent_id: str | None = None,
    ) -> SearchResponse:
        if not isinstance(request, SearchRequest):
            raise TypeError("request must be a SearchRequest")
        query_error = self._validate_query(request.query)
        if query_error:
            return self._response(
                request, intent_id, self.primary_provider, False, [], 0,
                {"error_class": "provider_contract_error", "message": query_error},
                stop_reason="invalid_query",
            )
        try:
            self._scope_limit(scope)
        except ValueError as exc:
            return self._response(
                request, intent_id, self.primary_provider, False, [], 0,
                {"error_class": "provider_contract_error", "message": str(exc)},
                stop_reason="invalid_scope",
            )
        provider_names = [self.primary_provider] + [name for name in self.fallback_providers if name != self.primary_provider]
        provider_names = [name for name in provider_names if name in self.providers]
        if not provider_names:
            raise ValueError("no configured search provider")

        # Provider is part of the cache key. The first healthy provider is
        # checked in order, while single-flight is shared across that request.
        lock_key = request.cache_key(None, self.routing_policy_version)
        lock = await self._lock_for(lock_key)
        async with lock:
            for provider_name in provider_names:
                cached = self._cached(self._cache_key(request, provider_name))
                if cached:
                    self.budget.cache_hits += 1
                    cached.request_id = self._request_id()
                    cached.task_id = self.task_id
                    cached.intent_id = intent_id
                    return cached

            budget_error = await self._reserve(scope)
            if budget_error is not None:
                budget_error.request_id = self._request_id()
                budget_error.task_id = self.task_id
                budget_error.intent_id = intent_id
                return budget_error

            retries = 0
            last_error: tuple[str, str] | None = None
            provider_switches = 0
            for provider_index, provider_name in enumerate(provider_names):
                if provider_index > 0:
                    provider_switches += 1
                    if provider_switches > self.max_provider_switches:
                        break
                attempts = 0
                while True:
                    try:
                        self.budget.provider_attempts += 1
                        if provider_name == self.primary_provider:
                            self.budget.anysearch_calls += 1
                        else:
                            self.budget.fallback_calls += 1
                        logger.info(
                            "SEARCH_PROVIDER_ATTEMPT task_id=%s provider=%s "
                            "primary=%s scope=%s query=%s",
                            self.task_id,
                            provider_name,
                            provider_name == self.primary_provider,
                            scope,
                            request.normalized_query[:160],
                        )
                        raw = self.providers[provider_name].search(request)
                        raw = await raw if inspect.isawaitable(raw) else raw
                        results = self._normalize_results(raw, provider_name)
                        # Enforce the caller's requested upper bound at the
                        # gateway boundary, including local fallback results.
                        results = results[:max(1, int(request.max_results))]
                        filtered = [result for result in results if result.quality_score >= self.min_quality_score]
                        quality = self._quality_score(filtered)
                        if not results:
                            last_error = ("no_results", f"{provider_name} returned no results")
                            logger.warning(
                                "SEARCH_PROVIDER_EMPTY task_id=%s provider=%s scope=%s",
                                self.task_id, provider_name, scope,
                            )
                            break
                        if not filtered or quality < self.min_quality_score:
                            last_error = ("quality_insufficient", "search quality is below configured threshold")
                            break
                        response = self._response(
                            request, intent_id, provider_name, True, filtered, retries,
                            None,
                            warning=(self._fallback_message(provider_names[provider_index - 1], last_error)
                                     if provider_index > 0 and last_error else None),
                            stop_reason="quality_reached",
                            fallback_attempted=provider_index > 0,
                        )
                        self._cache[self._cache_key(request, provider_name)] = _CacheEntry(time.monotonic(), copy.deepcopy(response))
                        return response
                    except Exception as exc:  # provider failures are isolated
                        error_class = self._classify_error(exc)
                        last_error = (error_class, str(exc))
                        logger.warning(
                            "SEARCH_PROVIDER_FAILED task_id=%s provider=%s "
                            "class=%s scope=%s",
                            self.task_id, provider_name, error_class, scope,
                        )
                        if error_class in {"auth_error", "rate_limited", "policy_or_region_block", "provider_contract_error"}:
                            break
                        if attempts >= self.max_provider_retries:
                            break
                        attempts += 1
                        retries += 1
                        self.budget.provider_retries += 1

            error_class, message = last_error or ("provider_error", "all providers failed")
            return self._response(
                request,
                intent_id,
                provider_names[-1],
                False,
                [],
                retries,
                {"error_class": error_class, "message": message},
                stop_reason="provider_failed",
                fallback_attempted=provider_switches > 0,
            )

    @staticmethod
    def _validate_query(query: str) -> str | None:
        """Reject prompt-like payloads before they reach a search provider."""
        normalized = " ".join(str(query or "").split())
        if not normalized:
            return "search query is empty"
        # Search queries should be concise. Long payloads are usually an LLM
        # analysis/prompt accidentally passed as a query and can trigger a
        # large, irrelevant crawl.
        if len(normalized) > 160:
            return "search query is too long or contains analysis content"
        prompt_markers = (
            "请判断", "请分析", "未提供", "需要判断", "数据缺口",
            "以下内容", "must determine", "please analyze", "internal prompt",
        )
        lowered = normalized.casefold()
        if any(marker.casefold() in lowered for marker in prompt_markers):
            return "search query contains prompt-like analysis content"
        return None

    async def health_check(self) -> dict[str, Any]:
        """Check configured providers without exposing provider secrets."""
        statuses = {}
        for name, provider in self.providers.items():
            checker = getattr(provider, "health_check", None)
            if checker is None:
                statuses[name] = {"healthy": True, "provider": name, "mode": "configured"}
                continue
            try:
                result = checker()
                statuses[name] = await result if inspect.isawaitable(result) else result
            except Exception:
                statuses[name] = {"healthy": False, "provider": name, "error_class": "provider_error"}
        return {"healthy": any(item.get("healthy") for item in statuses.values()), "providers": statuses}

    @staticmethod
    def _fallback_message(previous_provider: str, previous_error: tuple[str, str] | None) -> str:
        error_class = previous_error[0] if previous_error else "provider_error"
        labels = {
            "rate_limited": "quota exhausted or rate limited",
            "auth_error": "authentication rejected",
            "transient_transport_error": "network request failed",
            "provider_contract_error": "returned an invalid response",
            "no_results": "returned no results",
        }
        return f"{previous_provider} {labels.get(error_class, 'failed')}; switched to local search"

    def _response(
        self,
        request,
        intent_id,
        provider,
        success,
        results,
        retries,
        error,
        warning=None,
        stop_reason=None,
        fallback_attempted=False,
    ):
        request_id = self._request_id()
        if results and request is not None:
            results = self._attach_evidence_identity(
                results, request=request, provider=provider, request_id=request_id,
            )
        quality = self._quality_score(results)
        return SearchResponse(
            schema_version=self.SCHEMA_VERSION,
            request_id=request_id,
            task_id=self.task_id,
            intent_id=intent_id,
            success=success,
            results=copy.deepcopy(results),
            provider=provider,
            provider_status={"error_class": error["error_class"] if error else None, "message": error["message"] if error else None},
            quality_score=quality,
            source_count=len({result.url for result in results}),
            high_quality_count=sum(result.quality_score >= self.min_quality_score for result in results),
            retries=retries,
            cache_hit=False,
            estimated_cost=None,
            fetched_at=datetime.now(timezone.utc),
            warning=warning or (error["message"] if error else None),
            stop_reason=stop_reason,
            fallback_attempted=fallback_attempted,
        )

    def get_stats(self) -> dict[str, Any]:
        """Return a safe copy of task search statistics."""
        return {
            "task_id": self.task_id,
            "task_max_searches": self.budget.task_max_searches,
            "task_used_searches": self.budget.task_used_searches,
            "scope_used_searches": dict(self.budget.scope_used_searches),
            "cache_hits": self.budget.cache_hits,
            "anysearch_calls": self.budget.anysearch_calls,
            "fallback_calls": self.budget.fallback_calls,
            "provider_attempts": self.budget.provider_attempts,
            "provider_retries": self.budget.provider_retries,
            "stop_reason": self.budget.stop_reason,
        }

    @staticmethod
    def _normalize_results(raw: Any, provider: str) -> list[SearchResult]:
        values = raw if isinstance(raw, list) else (raw or {}).get("results", [])
        if not isinstance(values, list):
            raise ValueError("provider response results must be a list")
        normalized = []
        for item in values:
            if isinstance(item, SearchResult):
                normalized.append(copy.deepcopy(item))
                continue
            if not isinstance(item, Mapping):
                raise ValueError("provider result must be an object")
            url = str(item.get("url") or item.get("href") or "")
            parsed_url = urlparse(url)
            if not url or parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.netloc:
                continue
            normalized.append(SearchResult(
                title=str(item.get("title") or ""),
                url=url,
                snippet=str(item.get("snippet") or item.get("body") or ""),
                source=str(item.get("source") or provider),
                published_at=item.get("published_at") or item.get("date") or item.get("published"),
                quality_score=float(item.get("quality_score", 0)),
                evidence_id=str(item.get("evidence_id") or ""),
                provenance_id=str(item.get("provenance_id") or ""),
                excerpt=str(item.get("excerpt") or item.get("evidence_excerpt") or item.get("snippet") or item.get("body") or ""),
                locator=str(item.get("locator") or item.get("url") or item.get("href") or ""),
                task_id=str(item.get("task_id") or ""),
                request_id=str(item.get("request_id") or ""),
                retrieved_at=item.get("retrieved_at"),
            ))
        return normalized

    def _attach_evidence_identity(
        self,
        results: list[SearchResult],
        *,
        request: SearchRequest,
        provider: str,
        request_id: str,
    ) -> list[SearchResult]:
        """Normalize search results into auditable, task-scoped evidence."""
        retrieved_at = datetime.now(timezone.utc).isoformat()
        enriched = []
        for result in results:
            result = copy.deepcopy(result)
            excerpt = str(result.excerpt or result.snippet or "").strip()
            evidence_material = "|".join((provider, result.url, result.title, excerpt))
            evidence_id = result.evidence_id or (
                "ev_" + hashlib.sha256(evidence_material.encode("utf-8")).hexdigest()[:16]
            )
            provenance_material = "|".join((self.task_id, request_id, provider, evidence_id))
            provenance_id = result.provenance_id or (
                "prov_" + hashlib.sha256(provenance_material.encode("utf-8")).hexdigest()[:16]
            )
            result.evidence_id = evidence_id
            result.provenance_id = provenance_id
            result.excerpt = excerpt
            result.locator = result.locator or result.url
            result.task_id = result.task_id or self.task_id
            result.request_id = result.request_id or request_id
            result.retrieved_at = result.retrieved_at or retrieved_at
            enriched.append(result)
        return enriched

    @staticmethod
    def _quality_score(results: list[SearchResult]) -> float:
        if not results:
            return 0.0
        return round(sum(result.quality_score for result in results) / len(results), 2)

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        provider_category = getattr(exc, "category", None)
        if provider_category in {
            "auth_error",
            "rate_limited",
            "policy_or_region_block",
            "provider_contract_error",
            "transient_transport_error",
            "provider_error",
            "no_results",
        }:
            return provider_category
        if isinstance(exc, PermissionError):
            return "auth_error"
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return "transient_transport_error"
        if isinstance(exc, ValueError):
            return "provider_contract_error"
        return "provider_error"
