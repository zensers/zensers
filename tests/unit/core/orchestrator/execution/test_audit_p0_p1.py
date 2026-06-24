# -*- coding: utf-8 -*-
"""
P0/P1 修复验证测试 — engine.py
"""
import pytest
from src.core.orchestrator.execution.engine import ExecutionEngine


class TestEP17FixHexIdParsing:
    """E-P1-7 修复: _get_section_id_from_agent_id 支持 hex ID"""

    def test_inject_hex_id_now_returns_aspect(self):
        """修复后: inject_市场规模_a1b2c3d4 → '市场规模' (hex ID 被识别为索引)"""
        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._get_section_id_from_agent_id("inject_市场规模_a1b2c3d4")
        assert result == "市场规模", f"修复后返回 '市场规模': '{result}'"

    def test_inject_pure_numeric_id_returns_aspect(self):
        """inject_市场规模_123 → '市场规模'"""
        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._get_section_id_from_agent_id("inject_市场规模_123")
        assert result == "市场规模"

    def test_replan_mixed_alphanumeric_returns_last(self):
        """replan_竞争格局_xyz789: xyz789 不是纯hex/数字，按旧逻辑返回最后一段"""
        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._get_section_id_from_agent_id("replan_竞争格局_xyz789")
        assert result == "竞争格局", f"修复后 replan 前缀返回中间段: '{result}'"

    def test_phase_agent_format_unchanged(self):
        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._get_section_id_from_agent_id("phase_2_agent_0")
        assert result == "phase_2_agent_0"

    def test_numeric_index_still_works(self):
        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._get_section_id_from_agent_id("research_市场规模_2")
        assert result == "市场规模"


class TestEP18FixConsistentParsing:
    """E-P1-8 修复: 两个方法现在返回一致结果"""

    def test_same_id_same_results(self):
        engine = ExecutionEngine.__new__(ExecutionEngine)
        agent_id = "inject_市场规模_a1b2c3d4"
        r1 = engine._get_section_id_from_agent_id(agent_id)
        r2 = engine._extract_aspect_from_agent_id(agent_id)
        assert r1 == r2, f"修复后应一致: _get_section_id='{r1}', _extract_aspect='{r2}'"
