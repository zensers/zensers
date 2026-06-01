"""
DataCollector — cross-batch data event aggregator (B-FIX-5)

Listens to MessageBus data events and aggregates canonical data
for downstream batch injection.

Usage:
    collector = DataCollector()
    await message_bus.subscribe("data.canonical.updated", collector.on_canonical_updated)
    await message_bus.subscribe("data.conflict.detected", collector.on_conflict_detected)
    ...
    canonical = collector.get_canonical_data()
"""

from typing import Any, Dict, List
from src.core.communication import Event


class DataCollector:
    """Cross-batch data event aggregator"""

    def __init__(self):
        self._canonical_data: Dict[str, Any] = {}
        self._conflicts: List[Dict] = []

    async def on_canonical_updated(self, event: Event) -> None:
        """Handle canonical data update event"""
        data = event.data
        if not isinstance(data, dict):
            return
        key = data.get("metric", "")
        if not key:
            return
        version = data.get("version", 0)
        existing = self._canonical_data.get(key, {})
        if isinstance(existing, dict) and version >= existing.get("version", -1):
            self._canonical_data[key] = data

    async def on_conflict_detected(self, event: Event) -> None:
        """Handle data conflict event"""
        if isinstance(event.data, dict):
            self._conflicts.append(event.data)

    def get_canonical_data(self) -> Dict[str, Any]:
        """Get aggregated canonical data"""
        return dict(self._canonical_data)

    def get_conflicts(self) -> List[Dict]:
        """Get conflict event data list (event.data as dict)"""
        return list(self._conflicts)
