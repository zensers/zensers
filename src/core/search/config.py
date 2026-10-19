"""Validated, non-secret search configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency fallback
    load_dotenv = None


@dataclass(frozen=True)
class SearchConfig:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.anysearch.com"
    task_max_searches: int = 150
    default_scope_max_searches: int = 8

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def validate(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ANYSEARCH_API_BASE_URL must be an absolute HTTP(S) URL")


def get_search_config(*, environ: dict[str, str] | None = None) -> SearchConfig:
    # Search configuration is also consumed directly by the search gateway and
    # providers, so it must not depend on an unrelated settings module having
    # been imported first.  Explicit process environment values remain
    # authoritative; dotenv only fills missing values.
    if environ is None and load_dotenv is not None:
        load_dotenv(override=False)
    env = os.environ if environ is None else environ
    config = SearchConfig(
        api_key=(env.get("ANYSEARCH_API_KEY") or "").strip(),
        base_url=(env.get("ANYSEARCH_API_BASE_URL") or "https://api.anysearch.com").strip().rstrip("/"),
        task_max_searches=int(env.get("SEARCH_TASK_MAX_SEARCHES", "150")),
        default_scope_max_searches=int(env.get("SEARCH_DEFAULT_SCOPE_MAX_SEARCHES", "8")),
    )
    if config.task_max_searches < 0 or config.default_scope_max_searches < 0:
        raise ValueError("search budgets must be non-negative")
    config.validate()
    return config
