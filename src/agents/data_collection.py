"""Data Collection Agent.

Responsibilities:
- Requirement validation
- Search query construction
- Data collection
- Data cleaning
- Quality validation
"""

import json
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.agents.base import BaseAgent, AgentState
from src.core.data_providers.base import DataProvider, DataCache, RetryHandler


class DataSourceRegistry:
    """Data Source Registry."""
    
    def __init__(self):
        """Initialize registry."""
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def register(
        self,
        name: str,
        provider: DataProvider,
        priority: int = 10,
        tags: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Register a data source.
        
        Args:
            name: Source name
            provider: Data provider instance
            priority: Priority (lower = higher)
            tags: Source tags
            config: Source configuration
        """
        with self._lock:
            self._sources[name] = {
                "provider": provider,
                "priority": priority,
                "tags": tags or [],
                "config": config or {},
            }
    
    def unregister(self, name: str) -> bool:
        """Unregister a data source."""
        with self._lock:
            if name in self._sources:
                del self._sources[name]
                return True
            return False
    
    def get_source(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a data source by name."""
        with self._lock:
            return self._sources.get(name)
    
    def get_sources_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """Get data sources by tag."""
        with self._lock:
            return [s for s in self._sources.values() if tag in s["tags"]]
    
    def get_all_sources(self) -> List[str]:
        """Get all registered source names."""
        with self._lock:
            return list(self._sources.keys())


class DataCollectionAgent(BaseAgent):
    """Data Collection Agent.
    
    Responsible for collecting data from various sources,
    including web search and database queries.
    """
    
    def __init__(
        self,
        agent_id: str,
        storage_path: Optional[str] = None,
    ):
        super().__init__(agent_id, storage_path=storage_path)
        self._source_registry = DataSourceRegistry()
        self._collected_data: Dict[str, Any] = {}
        
        self.logger.info(f"Initialized DataCollectionAgent: {agent_id}")
    
    def register_source(
        self,
        name: str,
        provider: DataProvider,
        priority: int = 10,
        tags: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Register a data source with the agent."""
        self._source_registry.register(name, provider, priority, tags, config)
    
    async def collect(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        max_results: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect data.
        
        Args:
            query: Search query
            sources: Source names (None = all)
            max_results: Maximum results per source
            filters: Filter criteria
            
        Returns:
            Collection results
        """
        results = {}
        errors = {}
        
        # Determine sources to use
        if sources:
            source_list = [self._source_registry.get_source(s) for s in sources]
            source_list = [s for s in source_list if s]
        else:
            all_names = self._source_registry.get_all_sources()
            source_list = [self._source_registry.get_source(n) for n in all_names]
            source_list = [s for s in source_list if s]
            # Sort by priority
            source_list.sort(key=lambda s: s["priority"])
        
        # Collect from each source
        for source in source_list:
            provider = source["provider"]
            name = f"{provider.__class__.__name__}_{id(provider)}"
            
            try:
                data = await provider.search(
                    query=query,
                    max_results=max_results,
                    filters=filters,
                )
                if data:
                    results[name] = data
            except Exception as e:
                errors[name] = str(e)
                self.logger.warning(f"Collection from {name} failed: {e}")
        
        return {
            "success": len(results) > 0,
            "results": results,
            "total_count": sum(len(r) if isinstance(r, list) else 1 for r in results.values()),
            "errors": errors,
            "query": query,
        }
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data collection task.
        
        Args:
            task_input: {
                "query": Search query,
                "sources": Source list (optional),
                "max_results": Max results (optional),
                "data_type": Type of data to collect,
            }
        """
        query = task_input.get("query", "")
        sources = task_input.get("sources")
        max_results = task_input.get("max_results", 10)
        filters = task_input.get("filters")
        
        if not query:
            return {
                "success": False,
                "error": "No query provided",
                "data": [],
            }
        
        result = await self.collect(query, sources, max_results, filters)
        
        return {
            "success": result["success"],
            "data": result.get("results", {}),
            "total_count": result.get("total_count", 0),
            "errors": result.get("errors", {}),
            "query": query,
        }
    
    def get_collected_data(self, key: Optional[str] = None) -> Any:
        """Get previously collected data."""
        if key:
            return self._collected_data.get(key)
        return self._collected_data
    
    def reset(self) -> None:
        """Reset agent state."""
        super().reset()
        self._collected_data.clear()