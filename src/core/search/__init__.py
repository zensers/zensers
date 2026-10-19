# -*- coding: utf-8 -*-
"""
搜索相关组件模块

包含：
- DomainRoleInferrer: 领域角色推断器
"""

from .domain_role_inferrer import DomainRoleInferrer
from .anysearch_provider import AnySearchProvider, SearchProviderError
from .config import SearchConfig, get_search_config
from .gateway import (
    GatewaySearchSkillAdapter,
    LegacySkillProvider,
    LocalSkillProvider,
    SearchGateway,
    SearchRequest,
    SearchResponse,
    SearchResult,
    BudgetState,
)

__all__ = [
    "DomainRoleInferrer",
    "AnySearchProvider",
    "SearchProviderError",
    "GatewaySearchSkillAdapter",
    "LegacySkillProvider",
    "LocalSkillProvider",
    "SearchGateway",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "BudgetState",
    "SearchConfig",
    "get_search_config",
]
