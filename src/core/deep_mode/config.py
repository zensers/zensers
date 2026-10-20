from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class DeepModeConfig:
    enabled: bool = True
    shadow: bool = False
    max_searches: int = 60
    min_queries_per_section: int = 5
    max_queries_per_section: int = 8
    max_companies: int = 12
    max_bom_systems: int = 10
    max_records_per_type: int = 30

    def __post_init__(self) -> None:
        if self.min_queries_per_section < 1:
            raise ValueError("min_queries_per_section must be positive")
        if self.max_queries_per_section < self.min_queries_per_section:
            raise ValueError("max_queries_per_section must be >= min_queries_per_section")
        if self.max_searches < self.min_queries_per_section:
            raise ValueError("max_searches must be >= min_queries_per_section")
        if self.max_companies < 1 or self.max_bom_systems < 1:
            raise ValueError("company and BOM limits must be positive")

    @classmethod
    def from_env(cls) -> DeepModeConfig:
        return cls(
            enabled=_env_bool("ZENSERS_DEEP_MODE_ENABLED", True),
            shadow=_env_bool("ZENSERS_DEEP_MODE_SHADOW", False),
            max_searches=_env_int("ZENSERS_DEEP_MODE_MAX_SEARCHES", 60),
            min_queries_per_section=_env_int(
                "ZENSERS_DEEP_MODE_MIN_QUERIES_PER_SECTION", 5
            ),
            max_queries_per_section=_env_int(
                "ZENSERS_DEEP_MODE_MAX_QUERIES_PER_SECTION", 8
            ),
        )
