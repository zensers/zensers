"""Test: P1-2 Token分块策略优化 — _truncate_by_tokens + _count_tokens
"""
import pytest
from src.core.agents.generic_agent import GenericAgent


@pytest.fixture
def agent():
    spec = type("Spec", (), {
        "name": "test_agent",
        "role": "analyst",
        "skills": [],
        "context": {},
        "max_retries": 1,
        "timeout": 30,
    })()
    return GenericAgent(spec)


class TestCountTokens:
    def test_ascii_text(self, agent):
        tokens = agent._count_tokens("Hello world this is a test")
        assert tokens > 0
        assert tokens < 20

    def test_chinese_text(self, agent):
        tokens = agent._count_tokens("这是一段中文测试文本")
        assert tokens > 0

    def test_empty_string(self, agent):
        assert agent._count_tokens("") == 1

    def test_mixed_text(self, agent):
        tokens = agent._count_tokens("Hello 你好 world 世界")
        assert tokens > 0

    def test_fallback_no_tiktoken(self, agent):
        import unittest.mock
        with unittest.mock.patch.dict("sys.modules", {"tiktoken": None}):
            tokens = agent._count_tokens("Hello world")
            assert tokens > 0


class TestTruncateByTokens:
    def test_short_text_unchanged(self, agent):
        text = "Short text"
        result = agent._truncate_by_tokens(text, max_tokens=1000)
        assert result == text

    def test_long_text_truncated(self, agent):
        text = "这是一段很长的文本。" * 500
        result = agent._truncate_by_tokens(text, max_tokens=100)
        assert len(result) < len(text)
        assert "截断" in result

    def test_empty_text(self, agent):
        assert agent._truncate_by_tokens("", max_tokens=100) == ""

    def test_preserve_tables_keeps_tables(self, agent):
        text = (
            "Some introductory text about the company.\n\n"
            "| 指标 | 2023 | 2022 |\n"
            "|------|------|------|\n"
            "| 营业收入 | 100 | 80 |\n"
            "| 净利润 | 20 | 15 |\n\n"
            + "后续分析文本。" * 200
        )
        result = agent._truncate_by_tokens(text, max_tokens=200, preserve_tables=True)
        assert "营业收入" in result
        assert "净利润" in result

    def test_preserve_tables_false(self, agent):
        text = (
            "Some introductory text about the company.\n\n"
            "| 指标 | 2023 | 2022 |\n"
            "|------|------|------|\n"
            "| 营业收入 | 100 | 80 |\n\n"
            + "后续分析文本。" * 200
        )
        result = agent._truncate_by_tokens(text, max_tokens=200, preserve_tables=False)
        assert "截断" in result

    def test_no_tables_text_only(self, agent):
        text = "段落一\n\n段落二\n\n" + "段落三内容" * 300
        result = agent._truncate_by_tokens(text, max_tokens=100)
        assert "截断" in result

    def test_table_only_preserve(self, agent):
        text = (
            "| 指标 | 2023 | 2022 |\n"
            "|------|------|------|\n"
            "| 营业收入 | 100 | 80 |\n"
            "| 净利润 | 20 | 15 |\n"
        )
        result = agent._truncate_by_tokens(text, max_tokens=500, preserve_tables=True)
        assert "营业收入" in result

    def test_multiple_tables_preserved(self, agent):
        text = (
            "公司简介文本\n\n"
            "| 指标 | 2023 |\n|------|------|\n| 营业收入 | 100 |\n\n"
            "中间文本\n\n"
            "| 资产 | 金额 |\n|------|------|\n| 总资产 | 500 |\n\n"
            + "尾部文本" * 200
        )
        result = agent._truncate_by_tokens(text, max_tokens=200, preserve_tables=True)
        assert "营业收入" in result
        assert "总资产" in result


class TestTruncateByParagraphStillWorks:
    def test_basic_truncation(self, agent):
        text = "段落一\n\n段落二\n\n" + "段落三" * 3000
        result = agent._truncate_by_paragraph(text, max_chars=500)
        assert len(result) < len(text)
        assert "截断" in result

    def test_short_text_unchanged(self, agent):
        text = "短文本"
        assert agent._truncate_by_paragraph(text, max_chars=500) == text
