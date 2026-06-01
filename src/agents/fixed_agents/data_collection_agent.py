"""
Data Collection Agent
=====================

Responsible for collecting research data from multiple data sources.

Responsibilities:
1. Search for relevant information based on research requirements
2. Scrape data from web pages, databases, and other sources
3. Organize and perform preliminary data cleaning
4. Annotate data sources and credibility

Input:
{
    "query": str,               # Search query
    "data_sources": list,       # Specified data sources (optional)
    "max_results": int,         # Maximum number of results (optional)
    "filters": dict,            # Filter conditions (optional)
}

Output:
{
    "success": bool,
    "data": list,               # List of collected data
    "sources": list,            # List of data sources
    "statistics": dict,         # Statistics information
    "errors": list,             # Error information (if any)
}
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from .base_fixed_agent import FixedAgent


class DataCollectionAgent(FixedAgent):
    """Data Collection Agent.
    
    Responsible for collecting research data from multiple data sources.
    Supports various data acquisition methods including web search and database queries.
    """
    
    agent_type = "data_collection"
    version = "1.0.0"
    capabilities = [
        "web_search",
        "data_scraping",
        "data_cleaning",
        "source_annotation",
        "credibility_assessment",
    ]
    
    # Default data source configuration
    DEFAULT_SOURCES = {
        "web_search": {
            "enabled": True,
            "priority": "high",
            "max_results": 10,
        },
        "industry_db": {
            "enabled": False,
            "priority": "medium",
            "description": "Industry Database",
        },
        "news_api": {
            "enabled": False,
            "priority": "medium",
            "description": "News API",
        },
    }
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        if "query" not in task_input:
            return False, "Missing required field 'query'"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data collection (async).
        
        Args:
            task_input: {
                "query": "Energy storage industry market size 2024",
                "data_sources": ["web_search", "industry_db"],
                "max_results": 10,
                "filters": {"date_range": "2024"},
            }
        """
        query = task_input["query"]
        data_sources = task_input.get("data_sources", ["web_search"])
        max_results = task_input.get("max_results", 10)
        filters = task_input.get("filters", {})
        
        # Publish start event
        await self.publish_event("collection_started", {"query": query})
        
        collected_data = []
        sources_info = []
        errors = []
        
        # Collect data from each data source
        for source in data_sources:
            try:
                if source == "web_search":
                    result = self._collect_from_web(query, max_results, filters)
                elif source == "industry_db":
                    result = self._collect_from_database(query, max_results, filters)
                elif source == "news_api":
                    result = self._collect_from_news(query, max_results, filters)
                else:
                    result = {
                        "success": False,
                        "error": f"Unknown data source: {source}",
                    }
                
                if result.get("success"):
                    collected_data.extend(result.get("data", []))
                    sources_info.append({
                        "source": source,
                        "count": len(result.get("data", [])),
                        "status": "success",
                    })
                else:
                    errors.append({
                        "source": source,
                        "error": result.get("error", "Unknown error"),
                    })
                    sources_info.append({
                        "source": source,
                        "count": 0,
                        "status": "failed",
                        "error": result.get("error"),
                    })
                    
            except Exception as e:
                errors.append({
                    "source": source,
                    "error": str(e),
                })
                sources_info.append({
                    "source": source,
                    "count": 0,
                    "status": "error",
                    "error": str(e),
                })
        
        # Filter by topic relevance (remove obviously irrelevant results)
        collected_data = self._filter_by_relevance(collected_data, query)
        
        # Deduplicate and sort data
        collected_data = self._deduplicate_data(collected_data)
        collected_data = self._sort_by_relevance(collected_data, query)
        
        # Limit result count
        collected_data = collected_data[:max_results]
        
        # Calculate statistics
        statistics = {
            "total_collected": len(collected_data),
            "sources_used": len([s for s in sources_info if s["status"] == "success"]),
            "sources_failed": len([s for s in sources_info if s["status"] != "success"]),
            "collection_time": datetime.now().isoformat(),
        }
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_collection", statistics)
        
        # Publish completion event
        await self.publish_event("collection_completed", statistics)
        
        return {
            "success": len(collected_data) > 0,
            "data": collected_data,
            "sources": sources_info,
            "statistics": statistics,
            "errors": errors,
        }
    
    def _collect_from_web(
        self, 
        query: str, 
        max_results: int, 
        filters: Dict
    ) -> Dict[str, Any]:
        """Collect data from web search.
        
        Actual implementation can integrate search engine APIs (e.g., Google, Bing, Baidu).
        This provides a simplified implementation.
        """
        # Simulated search results
        # Actual implementation should call search engine API
        
        # Generate richer mock data
        templates = [
            f"In-depth analysis report on {query}: Market size continues to grow, with an expected CAGR exceeding 15% over the next three years.",
            f"{query} industry competitive landscape analysis: Leading companies hold concentrated market share, with CR5 reaching 65%, showing clear industry consolidation trends.",
            f"{query} technology development trends: Intelligence, digitalization, and green technology are the main directions, with continuous R&D investment growth.",
            f"{query} policy environment analysis: Multiple support policies introduced, including financial subsidies and tax incentives.",
            f"{query} value chain analysis: Upstream supply is stable, midstream manufacturing capacity is improving, downstream application scenarios are expanding.",
        ]
        
        mock_data = [
            {
                "title": f"{query} - Research Report {i+1}",
                "url": f"https://example.com/result/{query}/{i+1}",
                "snippet": templates[i % len(templates)] + f" Detailed data shows that {query} related indicators show positive development trends." * 5,
                "content": templates[i % len(templates)] + f"\n\nDetailed Analysis:\n\n" + f"In-depth research on {query} indicates this field has broad development prospects." * 20,
                "source": "web_search",
                "relevance_score": 0.95 - i * 0.02,
                "collected_at": datetime.now().isoformat(),
                "data_points": {
                    "market_size": f"{100 + i * 50} Billion CNY",
                    "growth_rate": f"{15 + i * 2}%",
                }
            }
            for i in range(min(max_results, 20))  # Increased to 20 items
        ]
        
        return {
            "success": True,
            "data": mock_data,
            "source": "web_search",
        }
    
    def _collect_from_database(
        self, 
        query: str, 
        max_results: int, 
        filters: Dict
    ) -> Dict[str, Any]:
        """Collect data from database.
        
        Actual implementation should connect to industry database.
        """
        # Simulated database query results
        return {
            "success": True,
            "data": [],  # No data currently
            "source": "industry_db",
            "message": "Database connection not configured",
        }
    
    def _collect_from_news(
        self, 
        query: str, 
        max_results: int, 
        filters: Dict
    ) -> Dict[str, Any]:
        """Collect data from news API.
        
        Actual implementation can integrate news APIs (e.g., Toutiao, Sina Finance).
        """
        # Simulated news data
        return {
            "success": True,
            "data": [],  # No data currently
            "source": "news_api",
            "message": "News API not configured",
        }
    
    def _deduplicate_data(self, data: List[Dict]) -> List[Dict]:
        """Deduplicate data.
        
        Deduplication based on URL or title.
        """
        seen_urls = set()
        seen_titles = set()
        unique_data = []
        
        for item in data:
            url = item.get("url", "")
            title = item.get("title", "")
            
            # Use URL or title as unique identifier
            key = url if url else title
            
            if key and key not in seen_urls and title not in seen_titles:
                seen_urls.add(url)
                seen_titles.add(title)
                unique_data.append(item)
        
        return unique_data
    
    def _sort_by_relevance(self, data: List[Dict], query: str) -> List[Dict]:
        """Sort by relevance.
        
        Sort based on relevance score, with higher scores first.
        """
        return sorted(
            data, 
            key=lambda x: x.get("relevance_score", 0), 
            reverse=True
        )
    
    @staticmethod
    def _filter_by_relevance(data: List[Dict], query: str) -> List[Dict]:
        """Filter out results with low topic relevance.

        Uses keyword overlap between the search query and result content
        to remove clearly irrelevant results (e.g., unrelated topics that
        matched a search engine's broad index).

        Args:
            data: List of raw search result items
            query: Original search query

        Returns:
            Filtered list with low-relevance items removed
        """
        query_lower = query.lower()
        query_keywords = set(query_lower.split())
        if not query_keywords:
            return data

        filtered = []
        for item in data:
            title = (item.get("title", "") or "").lower()
            content = (item.get("snippet", "") or "").lower()
            body = (item.get("body", "") or "").lower()
            combined = f"{title} {content} {body}"

            # Count how many query keywords appear in the result
            keyword_matches = sum(1 for kw in query_keywords if kw in combined)
            match_ratio = keyword_matches / len(query_keywords)

            # Keep results with at least some keyword overlap or with sufficient content length
            has_content = len(body) > 100 or len(content) > 50
            if match_ratio >= 0.2 or (has_content and match_ratio >= 0.1):
                filtered.append(item)

        if not filtered:
            return data  # Fallback: never return empty
        import logging
        logging.getLogger(__name__).info(f"Relevance filtering: {len(data)} -> {len(filtered)} results")
        return filtered
    
    def assess_credibility(self, data_item: Dict) -> Dict[str, Any]:
        """Assess data credibility.
        
        Evaluate data credibility based on source, timeliness, consistency, and other factors.
        
        Args:
            data_item: Data item
            
        Returns:
            Credibility assessment result
        """
        credibility_score = 0.5  # Base score
        factors = []
        
        # Source credibility
        source = data_item.get("source", "")
        if source in ["government", "official"]:
            credibility_score += 0.3
            factors.append("Official source")
        elif source in ["industry_db", "research"]:
            credibility_score += 0.2
            factors.append("Industry research")
        elif source == "web_search":
            credibility_score += 0.1
            factors.append("Web search")
        
        # Timeliness
        collected_at = data_item.get("collected_at", "")
        if collected_at:
            # Check if recent data
            factors.append("Has explicit timestamp")
        
        # Content completeness
        if data_item.get("title") and data_item.get("snippet"):
            credibility_score += 0.1
            factors.append("Complete content")
        
        return {
            "score": min(1.0, credibility_score),
            "level": "high" if credibility_score >= 0.8 else "medium" if credibility_score >= 0.5 else "low",
            "factors": factors,
        }
