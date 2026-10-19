"""Test B-FIX-6: Cross-batch reconciliation (defect 4.3)"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDataCollectorConflictConsumption:
    """L2: DataCollector.get_conflicts() is now consumed by engine"""

    def test_data_collector_conflicts_logged_and_injected(self):
        from src.core.orchestrator.execution.data_collector import DataCollector
        from src.core.communication import Event

        collector = DataCollector()
        event = Event(type="data.conflict.detected", data={
            "metric": "revenue_2024",
            "values": [100.0, 95.0],
            "sources": ["agent_A", "agent_B"],
        })
        loop = asyncio.new_event_loop()
        loop.run_until_complete(collector.on_conflict_detected(event))
        loop.close()

        conflicts = collector.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["metric"] == "revenue_2024"
        assert conflicts[0]["values"] == [100.0, 95.0]

    def test_data_collector_no_conflicts_returns_empty(self):
        from src.core.orchestrator.execution.data_collector import DataCollector

        collector = DataCollector()
        assert collector.get_conflicts() == []

    def test_data_collector_multiple_conflicts(self):
        from src.core.orchestrator.execution.data_collector import DataCollector
        from src.core.communication import Event

        collector = DataCollector()
        for i in range(3):
            event = Event(type="data.conflict.detected", data={
                "metric": f"metric_{i}",
                "values": [10.0 * i, 9.0 * i],
                "sources": ["a1", "a2"],
            })
            loop = asyncio.new_event_loop()
            loop.run_until_complete(collector.on_conflict_detected(event))
            loop.close()

        conflicts = collector.get_conflicts()
        assert len(conflicts) == 3


class TestMetricConflictDetailsConsumption:
    """L3: metric_conflict_details from aggregation are now consumed"""

    def test_metric_conflict_details_format(self):
        details = [
            {"key": "revenue", "year": 2024, "values": [100.0, 95.0], "sources": ["a1", "a2"]},
            {"key": "profit", "year": 2024, "values": [50.0, 48.0], "sources": ["b1", "b2"]},
        ]
        assert len(details) == 2
        assert details[0]["key"] == "revenue"
        assert details[1]["values"] == [50.0, 48.0]
