import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    ChapterWriter, DATAPOINT_FIELDS,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteInput, ChapterWriteOutput, DataPoint, ChapterIssue, ChapterReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "chapter_write.tmpl").write_text("${topic} ${section_name} ${base_content}", encoding="utf-8")
    (tmp_path / "chapter_rewrite.tmpl").write_text("${original_content} ${review_feedback}", encoding="utf-8")
    (tmp_path / "chapter_patch_data.tmpl").write_text("${chapter_content} ${patch_instructions}", encoding="utf-8")
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def writer(mock_llm, mock_prompts):
    return ChapterWriter(llm_skill=mock_llm, prompt_manager=mock_prompts)


def make_input(**overrides):
    defaults = dict(
        framework_config={"name": "行业研究"},
        task_structure={"topic": "新能源汽车"},
        chapter_spec={"section_id": "ch1", "section_name": "市场规模", "section_role": "analysis"},
        chapter_data={"市场规模": "2000亿"},
        preceding_summary="前文摘要",
        used_metrics_summary="暂无已使用的数据指标。",
    )
    defaults.update(overrides)
    return ChapterWriteInput(**defaults)


class TestChapterWriterWrite:
    @pytest.mark.asyncio
    async def test_write_returns_chapter_output(self, writer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"title": "市场规模", "content": "正文", "data_points_used": [{"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "iimedia.cn"}], "key_conclusions": ["市场规模达2000亿"], "self_check_passed": true, "self_check_issues": []}\n```',
        }
        result = await writer.write(make_input())
        assert isinstance(result, ChapterWriteOutput)
        assert result.title == "市场规模"
        assert result.content == "正文"
        assert len(result.data_points_used) == 1
        assert result.self_check_passed is True

    @pytest.mark.asyncio
    async def test_write_passes_base_content(self, writer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"title": "市场规模", "content": "正文", "data_points_used": [], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```',
        }
        inp = make_input(base_content="分析Agent的精炼内容")
        await writer.write(inp)
        call_args = mock_llm.execute.call_args
        prompt_text = call_args[1]["prompt"]
        assert "分析Agent的精炼内容" in prompt_text

    @pytest.mark.asyncio
    async def test_write_llm_failure_raises(self, writer, mock_llm):
        mock_llm.execute.return_value = {"success": False}
        with pytest.raises(RuntimeError):
            await writer.write(make_input())


class TestChapterWriterRewrite:
    @pytest.mark.asyncio
    async def test_rewrite_with_review_feedback(self, writer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"title": "市场规模", "content": "重写正文", "data_points_used": [], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```',
        }
        original = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="旧正文")
        review = ChapterReviewOutput(
            passed=False, score=40,
            issues=[ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="无数据", suggestion="补充数据")],
        )
        result = await writer.rewrite(original, review, {"name": "行业研究"}, {"section_id": "ch1", "section_name": "市场规模"}, "前文")
        assert result.content == "重写正文"


class TestChapterWriterPatchData:
    @pytest.mark.asyncio
    async def test_patch_data(self, writer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"title": "市场规模", "content": "修补后正文", "data_points_used": [], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```',
        }
        chapter = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="旧正文")
        result = await writer.patch_data(chapter, ["补充数据：市场规模=2000亿元"], {"name": "行业研究"})
        assert result.content == "修补后正文"


class TestChapterWriterParseOutput:
    def test_parse_valid_json(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "GDP", "value": "120", "unit": "万亿元", "source": "gov.cn"}], "key_conclusions": ["结论1"], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.title == "测试"
        assert len(result.data_points_used) == 1

    def test_parse_filters_extra_fields(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "GDP", "value": "120", "unit": "万亿元", "source": "gov.cn", "year": 2025}], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        dp = result.data_points_used[0]
        assert isinstance(dp, DataPoint)
        assert not hasattr(dp, "year")

    def test_parse_invalid_json_fallback(self, writer):
        raw = "这不是JSON格式的内容"
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.self_check_passed is False
        assert "JSON解析失败" in result.self_check_issues[0]
        assert result.content == raw

    def test_parse_missing_json_block_fallback(self, writer):
        raw = '{"title": "测试", "content": "正文"}'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.self_check_passed is False


class TestChapterWriterExtractConclusions:
    def test_extract_conclusion_lines(self, writer):
        text = "- **核心结论1**：市场规模达2000亿\n- **核心结论2**：增速15%\n普通段落"
        conclusions = writer._extract_conclusions(text)
        assert len(conclusions) == 2

    def test_extract_conclusions_max_five(self, writer):
        lines = [f"- **核心结论{i}**：内容{i}" for i in range(10)]
        text = "\n".join(lines)
        conclusions = writer._extract_conclusions(text)
        assert len(conclusions) == 5

    def test_extract_conclusions_no_match(self, writer):
        text = "普通段落\n没有结论"
        conclusions = writer._extract_conclusions(text)
        assert len(conclusions) == 0


class TestDataPointFields:
    def test_datapoint_fields_constant(self):
        assert "metric" in DATAPOINT_FIELDS
        assert "value" in DATAPOINT_FIELDS
        assert "unit" in DATAPOINT_FIELDS
        assert "source" in DATAPOINT_FIELDS
        assert "chapter_id" in DATAPOINT_FIELDS
        assert "confidence" in DATAPOINT_FIELDS
        assert "year" not in DATAPOINT_FIELDS


class TestDataPointCoercion:
    def test_float_value_coerced_to_str(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "营收", "value": 1502.25, "unit": "亿元", "source": "财报", "confidence": 0.9}], "key_conclusions": ["营收下降"], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        dp = result.data_points_used[0]
        assert isinstance(dp.value, str)
        assert dp.value == "1502.25"

    def test_int_value_coerced_to_str(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "销量", "value": 38, "unit": "万辆", "source": "公告"}], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        dp = result.data_points_used[0]
        assert isinstance(dp.value, str)
        assert dp.value == "38"

    def test_numeric_key_conclusions_coerced_to_str(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [], "key_conclusions": [3.5, "正常结论"], "self_check_passed": true, "self_check_issues": [1]}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert all(isinstance(c, str) for c in result.key_conclusions)
        assert result.key_conclusions[0] == "3.5"
        assert all(isinstance(i, str) for i in result.self_check_issues)
