"""
MCP Tool Matcher

Matches research aspects to available MCP tools using keyword and semantic matching.
Integrates with IntelligentRoutingAdapter to assign MCP tools per agent.

Architecture:
- Keyword matching: fast path, uses pre-defined aspect→keyword mappings
- LLM semantic matching: accurate path, uses tool descriptions for novel aspects
- Static fallback: reliability, predefined aspect→tool map for common cases
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Static fallback mapping for reliability — covers common research aspects
ASPECT_MCP_FALLBACK: Dict[str, List[str]] = {
    "financial_analysis": ["wind.get_stock_data", "wind.get_financials"],
    "valuation_analysis": ["wind.get_valuation"],
    "technology_trends": ["github.repo_search", "arxiv.search_papers"],
    "competitive_landscape": ["wind.industry_company_list"],
    "market_size": ["wind.industry_data"],
    "industry_chain": ["wind.industry_data"],
    "risk_analysis": ["wind.get_financials"],
    "investment_analysis": ["wind.get_stock_data", "wind.get_financials"],
}


# Keyword mapping for fast matching (English aspect names → MCP tool keywords)
ASPECT_KEYWORDS: Dict[str, List[str]] = {
    "financial_analysis": ["stock", "financial", "revenue", "profit", "valuation"],
    "valuation_analysis": ["valuation", "pe", "pb", "market_cap", "equity"],
    "technology_trends": ["github", "arxiv", "repo", "paper", "research", "patent"],
    "competitive_landscape": ["competitor", "market_share", "industry", "company"],
    "market_size": ["market", "size", "growth", "tam", "sam"],
    "industry_chain": ["supply_chain", "industry", "vertical"],
    "risk_analysis": ["risk", "volatility", "debt", "default"],
    "investment_analysis": ["investment", "return", "dividend", "yield"],
}


class MCPToolMatcher:
    """
    Matches research aspects to available MCP tools.

    Uses a three-strategy approach:
    1. Keyword matching (fast) — maps aspect name keywords to tool descriptions
    2. LLM semantic matching (accurate) — for novel or complex aspects
    3. Static fallback (reliable) — predefined mapping for common aspects
    """

    def __init__(self, mcp_handler: Any, llm_client: Optional[Any] = None):
        """
        Args:
            mcp_handler: MCPProtocolHandler instance for listing available tools
            llm_client: Optional LLM client for semantic matching
        """
        self._mcp_handler = mcp_handler
        self._llm_client = llm_client
        self._cache: Dict[str, List[str]] = {}

    async def match(self, aspect: str, top_k: int = 3) -> List[str]:
        """
        Find relevant MCP tools for an aspect.

        Args:
            aspect: Research aspect name (e.g., "financial_analysis", "technology_trends")
            top_k: Maximum number of tools to return

        Returns:
            List of fully qualified tool names (e.g., ["wind.get_stock_data"])
        """
        # Check cache
        if aspect in self._cache:
            return self._cache[aspect][:top_k]

        # Get all available tools from MCP handler
        all_tools = self._mcp_handler.list_available_tools()
        if not all_tools:
            return []

        # Strategy 1: Keyword matching (fast)
        matched = self._keyword_match(aspect, all_tools)

        # Strategy 2: LLM semantic matching (accurate, if available)
        if self._llm_client and len(matched) < top_k:
            semantic_matches = await self._semantic_match(aspect, all_tools, top_k)
            matched.extend(semantic_matches)

        # Strategy 3: Static fallback (reliable)
        if not matched:
            matched = ASPECT_MCP_FALLBACK.get(aspect, [])

        # Deduplicate and respect top_k
        matched = list(dict.fromkeys(matched))[:top_k]

        # Cache for subsequent calls
        self._cache[aspect] = matched

        logger.info(f"MCPToolMatcher: aspect='{aspect}' → {matched}")
        return matched

    def _keyword_match(self, aspect: str, tools: List[Dict[str, Any]]) -> List[str]:
        """Match aspect keywords against tool descriptions"""
        keywords = ASPECT_KEYWORDS.get(aspect, [])
        if not keywords:
            # Fall back to extracting keywords from aspect name
            keywords = [aspect.lower().replace("_", " ")]

        matched = []
        for tool in tools:
            desc = tool.get("description", "").lower()
            name = tool.get("name", "").lower()

            for kw in keywords:
                if kw.lower() in desc or kw.lower() in name:
                    matched.append(tool["name"])
                    break

        return matched

    async def _semantic_match(
        self, aspect: str, tools: List[Dict[str, Any]], top_k: int
    ) -> List[str]:
        """Use LLM to semantically match aspect to tools"""
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in tools]
        )

        prompt = (
            f"Given a research aspect \"{aspect}\", select the most relevant tools.\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            f"Return only the tool names, one per line, up to {top_k} most relevant tools. "
            f"If no tools are relevant, return \"none\"."
        )

        try:
            response = await self._llm_client.generate(prompt)
            if "none" in response.lower():
                return []
            return [
                line.strip()
                for line in response.strip().split("\n")
                if line.strip()
            ]
        except Exception as e:
            logger.warning(f"LLM semantic matching failed for aspect '{aspect}': {e}")
            return []

    def invalidate_cache(self, aspect: Optional[str] = None) -> None:
        """Invalidate the match cache"""
        if aspect:
            self._cache.pop(aspect, None)
        else:
            self._cache.clear()
