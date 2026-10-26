import pytest
import json
from unittest.mock import AsyncMock, patch

from src.agents.fixed_agents.report_upgrade.chapter_writer import (
    ChapterWriter, DATAPOINT_FIELDS, DELIMITER_OUTPUT_CONTRACT,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteInput, ChapterWriteOutput, DataPoint, ChapterIssue, ChapterReviewOutput,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.core.llm_retry import (
    Classification, LLMBudgetExhausted, LLMErrorClass, RetryVariations,
)


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "chapter_write.tmpl").write_text("${topic} ${section_name} ${base_content} ${raw_data_location} 只有确认原始数据无法支持当前章节时，才执行补充搜索", encoding="utf-8")
    (tmp_path / "chapter_write_pptx.tmpl").write_text("PPTX ${topic} ${section_name}", encoding="utf-8")
    (tmp_path / "chapter_rewrite.tmpl").write_text("${original_content} ${review_feedback}", encoding="utf-8")
    (tmp_path / "chapter_patch_data.tmpl").write_text("${chapter_content} ${patch_instructions}", encoding="utf-8")
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def writer(mock_prompts):
    # Existing unit tests exercise the legacy response contract. The
    # production default is streaming; the dedicated streaming regression
    # below uses the default explicitly.
    return ChapterWriter(prompt_manager=mock_prompts, use_streaming=False)


_VALID_CHAPTER_JSON = json.dumps({
    "title": "市场规模",
    "content": "正文",
    "data_points_used": [{"metric": "市场规模", "value": "2000", "unit": "亿元", "source": "iimedia.cn"}],
    "key_conclusions": ["市场规模达2000亿"],
    "self_check_passed": True,
    "self_check_issues": [],
}, ensure_ascii=False)


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


_CALL_LLM_EX_PATH = "src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex"


class _EngineFake:
    """call_llm_ex side_effect: captures kwargs, optionally builds the prompt."""

    def __init__(self, raw_result, build_prompt=False):
        self.raw_result = raw_result
        self.build_prompt = build_prompt
        self.captured = {}
        self.prompt_text = None

    def __call__(self, prompt_builder, **kwargs):
        self.captured.update(kwargs)
        if self.build_prompt:
            self.prompt_text = prompt_builder(RetryVariations())
        return self.raw_result


def _engine_ex(raw_result, build_prompt=False):
    """Fake engine returning the usable value (engine contract)."""
    return _EngineFake(raw_result, build_prompt)


class TestChapterWriterWrite:
    @pytest.mark.asyncio
    async def test_write_forwards_streaming_flag_to_engine(self, writer):
        # The writer picks the transport mode; stream-timeout retry policy
        # itself now lives in the retry engine's transport (llm_client).
        fake = _engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```")
        streaming_writer = ChapterWriter(prompt_manager=writer._prompts)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake) as engine_call:
            result = await streaming_writer.write(make_input())

        assert result.content == "正文"
        engine_call.assert_awaited_once()
        assert fake.captured["stream"] is True

    @pytest.mark.asyncio
    async def test_non_streaming_writer_uses_non_stream_engine_transport(self, writer):
        fake = _engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```")
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake) as engine_call:
            result = await writer.write(make_input())

        assert result.content == "正文"
        engine_call.assert_awaited_once()
        assert fake.captured["stream"] is False

    @pytest.mark.asyncio
    async def test_write_returns_chapter_output(self, writer):
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock,
                   side_effect=_engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```")):
            result = await writer.write(make_input())
        assert isinstance(result, ChapterWriteOutput)
        assert result.title == "市场规模"
        assert result.content == "正文"
        assert len(result.data_points_used) == 1
        assert result.self_check_passed is True

    @pytest.mark.asyncio
    async def test_write_passes_base_content(self, writer):
        fake = _engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```", build_prompt=True)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake):
            inp = make_input(base_content="分析Agent的精炼内容")
            await writer.write(inp)
        assert "分析Agent的精炼内容" in fake.prompt_text

    @pytest.mark.asyncio
    async def test_write_tells_llm_raw_data_location_and_priority(self, writer):
        fake = _engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```", build_prompt=True)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake):
            await writer.write(make_input(raw_data_location="E:/task/research_result_cache.json"))
        assert "E:/task/research_result_cache.json" in fake.prompt_text
        assert "只有确认原始数据无法支持当前章节时，才执行补充搜索" in fake.prompt_text

    @pytest.mark.asyncio
    async def test_write_uses_pptx_prompt_when_requested(self, writer):
        fake = _engine_ex(f"```json\n{_VALID_CHAPTER_JSON}\n```", build_prompt=True)
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake):
            await writer.write(make_input(output_format="pptx"))
        assert fake.prompt_text.startswith("PPTX ")

    @pytest.mark.asyncio
    async def test_write_llm_budget_exhaustion_returns_failed_chapter(self, writer):
        # LLM failure is no longer raised out of write(): the engine budget
        # exhaustion surfaces as an explicit failed chapter carrying the
        # budget_exhausted class for the downstream defense rescue loop.
        exhausted = LLMBudgetExhausted(
            Classification(LLMErrorClass.DEGENERATE, detail="155c"),
            attempts=4, elapsed=600.0,
        )
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock) as engine_call:
            engine_call.side_effect = exhausted
            result = await writer.write(make_input())
        engine_call.assert_awaited_once()
        assert result.status == "failed"
        assert "budget_exhausted:degenerate" in result.error


class TestChapterWriterRewrite:
    @pytest.mark.asyncio
    async def test_rewrite_with_review_feedback(self, writer):
        # Engine seam: the fake returns the usable value the retry engine
        # would hand back (parse hook's chapter value).
        fake = _engine_ex('```json\n{"title": "市场规模", "content": "重写正文", "data_points_used": [], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```')
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake) as engine_call:
            original = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="旧正文")
            review = ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="无数据", suggestion="补充数据")],
            )
            result = await writer.rewrite(original, review, {"name": "行业研究"}, {"section_id": "ch1", "section_name": "市场规模"}, "前文")
        engine_call.assert_awaited_once()
        assert fake.captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert fake.captured["task_tag"] == "rewrite:ch1"
        assert result.content == "重写正文"


class TestChapterWriterPatchData:
    @pytest.mark.asyncio
    async def test_patch_data(self, writer):
        fake = _engine_ex('```json\n{"title": "市场规模", "content": "修补后正文", "data_points_used": [], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```')
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake) as engine_call:
            chapter = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="旧正文")
            result = await writer.patch_data(chapter, ["补充数据：市场规模=2000亿元"], {"name": "行业研究"})
        engine_call.assert_awaited_once()
        assert fake.captured["output_contract"] == DELIMITER_OUTPUT_CONTRACT
        assert fake.captured["task_tag"] == "patch:ch1"
        assert result.content == "修补后正文"

    @pytest.mark.asyncio
    async def test_patch_data_preserves_omitted_evidence_identity(self, writer):
        fake = _engine_ex(
            '```json\n{"title": "市场规模", "content": "修补后正文", '
            '"data_points_used": [{"metric": "市场规模", "value": "2000", '
            '"unit": "亿元", "source": "来源"}], "key_conclusions": [], '
            '"self_check_passed": true, "self_check_issues": []}\n```'
        )
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=fake):
            chapter = ChapterWriteOutput(
                chapter_id="ch1", title="市场规模", content="旧正文",
                data_points_used=[DataPoint(
                    metric="市场规模", value="2000", unit="亿元", source="来源",
                    chapter_id="ch1", source_url="https://example.test/market",
                    evidence_id="ev-1", provenance_id="prov-1",
                    evidence_status="verified",
                )],
            )
            result = await writer.patch_data(chapter, ["删除无据数字"], {"name": "行业研究"})
        assert result.data_points_used[0].source_url == "https://example.test/market"
        assert result.data_points_used[0].evidence_id == "ev-1"
        assert result.data_points_used[0].provenance_id == "prov-1"
        assert result.data_points_used[0].evidence_status == "verified"


class TestChapterWriterParseOutput:
    def test_parse_valid_json(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "GDP", "value": "120", "unit": "万亿元", "source": "gov.cn"}], "key_conclusions": ["结论1"], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.title == "测试"
        assert len(result.data_points_used) == 1

    def test_parse_invalid_data_point_item_becomes_failed_chapter(self, writer):
        raw = (
            '```json\n{"content": "正文", "data_points_used": ["不是对象"], '
            '"key_conclusions": []}\n```'
        )
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.status == "failed"
        assert result.content == ""
        assert "JSON解析失败" in result.error

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
        assert result.content == ""
        assert result.status == "failed"
        assert result.error

    def test_parse_missing_json_block_fallback(self, writer):
        raw = '{"title": "测试", "content": "正文"}'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.title == "测试"
        assert result.content == "正文"
        assert result.self_check_passed is True

    def test_parse_empty_content_is_failed_not_a_valid_chapter(self, writer):
        result = writer._parse_output(
            '{"title": "测试", "content": ""}',
            {"section_id": "ch1", "section_name": "测试"},
        )
        assert result.status == "failed"
        assert result.content == ""
        assert result.self_check_passed is False

    def test_parse_raw_json_no_code_block(self, writer):
        # I1 起结论行需通过 check_finding_line（>=8 字、非元思考）；
        # 夹具结论补足长度以聚焦本测的目标（无代码块的裸 JSON 解析）。
        raw = '一些文字\n{"title": "市场分析", "content": "市场规模达2000亿", "data_points_used": [], "key_conclusions": ["增速达到15%以上"], "self_check_passed": true}\n更多文字'
        result = writer._parse_output(raw, {"section_id": "ch2", "section_name": "默认标题"})
        assert result.title == "默认标题"
        assert result.content == "市场规模达2000亿"
        assert len(result.key_conclusions) == 1

    def test_parse_removes_internal_cache_and_rewrite_notes(self, writer):
        content = (
            "我将检查缓存。\n\n[数据获取尝试] 缓存 JSON 解析失败。\n\n"
            "---\n\n## 核心结论\n正文结论。\n\n---\n**改写说明**：内部说明\n"
            "如果您需要更简练，我可以继续优化。"
        )
        raw = json.dumps({"title": "测试", "content": content}, ensure_ascii=False)
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.content == "## 核心结论\n正文结论。"
        assert "数据获取尝试" not in result.content
        assert "改写说明" not in result.content

    def test_parse_normalizes_source_url_list(self, writer):
        content = "结论。来源：['[https://m.21jingji.com/a](https://m.21jingji.com/a)', '[https://example.com/x](https://example.com/x)']"
        raw = json.dumps({"title": "测试", "content": content}, ensure_ascii=False)
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert "['" not in result.content
        assert "[m.21jingji.com](https://m.21jingji.com/a)" in result.content
        assert "[example.com](https://example.com/x)" in result.content


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
        assert "evidence_id" in DATAPOINT_FIELDS
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

    def test_evidence_id_is_preserved(self, writer):
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [{"metric": "销量", "value": 38, "unit": "万辆", "source": "公告", "evidence_id": "ev-1"}], "key_conclusions": [], "self_check_passed": true, "self_check_issues": []}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert result.data_points_used[0].evidence_id == "ev-1"

    def test_numeric_key_conclusions_coerced_to_str(self, writer):
        # I1 起结论行需通过 check_finding_line（>=8 字）——数字结论取足够
        # 长的浮点字面量以同时验证数值→字符串强转与行级契约。
        raw = '```json\n{"title": "测试", "content": "正文", "data_points_used": [], "key_conclusions": [1234.5678, "正常结论内容足够长"], "self_check_passed": true, "self_check_issues": [1]}\n```'
        result = writer._parse_output(raw, {"section_id": "ch1", "section_name": "测试"})
        assert all(isinstance(c, str) for c in result.key_conclusions)
        assert result.key_conclusions[0] == "1234.5678"
        assert all(isinstance(i, str) for i in result.self_check_issues)


class TestChapterPromptToolGuidance:
    @pytest.mark.asyncio
    async def test_missing_raw_cache_has_no_tool_call_instruction(self, tmp_path):
        # Regression: with a nonexistent cache path the old template instructed
        # the model to call read_json; with no tools bound the model answered
        # with a bare <function=read_json> tool-call text (155 chars) instead
        # of writing the chapter.
        missing = str(tmp_path / "no_such_cache.json")
        captured = {}

        def _fake_ex(prompt_builder, **kwargs):
            captured["prompt"] = prompt_builder(RetryVariations())
            return "raw"

        streaming_writer = ChapterWriter(prompt_manager=PromptManager())
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=_fake_ex):
            await streaming_writer.write(make_input(raw_data_location=missing))

        prompt_text = captured["prompt"]
        assert "调用 `read_json" not in prompt_text
        assert "不存在 read_json 工具" in prompt_text
        assert "不要尝试调用" in prompt_text
        # Path stays visible in the prompt for context.
        assert missing in prompt_text

    @pytest.mark.asyncio
    async def test_existing_raw_cache_engine_path_has_no_tool_promise(self, tmp_path):
        # The engine transport binds no tools, so even with a valid cache file
        # the write prompt must NOT promise read_json (a promised-but-absent
        # tool produced 155-char tool-call refusals in production).  The
        # tool-bound prompt is only rebuilt for the budget-exhaustion
        # compatibility fallback (tools_bound=True).
        cache_file = tmp_path / "research_result_cache.json"
        cache_file.write_text("{}", encoding="utf-8")
        captured = {}

        def _fake_ex(prompt_builder, **kwargs):
            captured["prompt"] = prompt_builder(RetryVariations())
            return "raw"

        streaming_writer = ChapterWriter(prompt_manager=PromptManager())
        with patch(_CALL_LLM_EX_PATH, new_callable=AsyncMock, side_effect=_fake_ex):
            await streaming_writer.write(make_input(raw_data_location=str(cache_file)))

        prompt_text = captured["prompt"]
        assert "read_json(filepath=" not in prompt_text
        assert "你拥有只读工具 `read_json`" not in prompt_text
        assert "不存在 read_json 工具" in prompt_text
        assert "不要尝试调用" in prompt_text
        # Path stays visible in the prompt for context.
        assert str(cache_file) in prompt_text


class TestChapterPromptPptxBulletLimit:
    """策略接线 B：pptx 提示词的要点字数上限必须来自 PPTXStrategy，不得硬编码。"""

    def _pptx_writer(self):
        # 真实 PromptManager + 真实模板：接线测试必须走生产模板文件。
        return ChapterWriter(prompt_manager=PromptManager(), use_streaming=False)

    def test_pptx_prompt_bullet_limit_comes_from_strategy(self, monkeypatch):
        # 哨兵值（30）证明数字来自策略注入而非模板硬编码：若模板仍写死 25，
        # 渲染结果不会跟随策略变化，本测试失败。
        from dataclasses import replace as dc_replace

        from src.content.format_strategy import get_format_strategy

        real_directive = get_format_strategy("pptx").get_writing_directive()
        sentinel = dc_replace(real_directive, bullet_max_chars=30)

        class _FakeStrategy:
            def get_writing_directive(self, section_type: str = "body"):
                return sentinel

        monkeypatch.setattr(
            "src.content.format_strategy.get_format_strategy",
            lambda fmt: _FakeStrategy(),
        )
        prompt = self._pptx_writer()._build_write_prompt(
            make_input(output_format="pptx"), RetryVariations(), "")
        assert "30 个中文字符" in prompt
        assert "25 个中文字符" not in prompt

    def test_pptx_prompt_uses_strategy_value_without_leftover_placeholder(self):
        from src.content.format_strategy import get_format_strategy

        directive = get_format_strategy("pptx").get_writing_directive()
        prompt = self._pptx_writer()._build_write_prompt(
            make_input(output_format="pptx"), RetryVariations(), "")
        assert f"{directive.bullet_max_chars} 个中文字符" in prompt
        assert "${bullet_max_chars}" not in prompt

    def test_docx_prompt_has_no_bullet_limit_injection(self):
        prompt = self._pptx_writer()._build_write_prompt(
            make_input(), RetryVariations(), "")
        assert "个中文字符" not in prompt
        assert "bullet_max_chars" not in prompt


class TestDeepModeEvidencePrompt:
    def _writer(self, mock_prompts):
        return ChapterWriter(prompt_manager=mock_prompts, use_streaming=False)
    def test_write_prompt_appends_deep_mode_evidence_block(self, mock_prompts):
        writer = self._writer(mock_prompts)
        inp = make_input(chapter_data={
            "deep_mode_evidence": {
                "tables": "| 公司 | 市场份额 |\n|---|---|\n| 比亚迪 | 22.3% |",
                "gap_notes": ["供应商配套关系"],
            },
        })

        prompt = writer._build_write_prompt(inp, RetryVariations(), "前文摘要")

        assert "深度模式结构化证据" in prompt
        assert "### 深度模式数据表" in prompt
        assert "| 比亚迪 | 22.3% |" in prompt
        assert "供应商配套关系" in prompt
        assert "不得虚构数值填补" in prompt
        assert "self_check" in prompt

    def test_write_prompt_has_no_deep_evidence_block_by_default(self, mock_prompts):
        writer = self._writer(mock_prompts)

        prompt = writer._build_write_prompt(make_input(), RetryVariations(), "前文摘要")

        assert "深度模式结构化证据" not in prompt


class TestLengthTargetResolution:
    def _writer(self, mock_prompts):
        return ChapterWriter(prompt_manager=mock_prompts, use_streaming=False)

    def test_prefers_chapter_spec_over_framework(self):
        assert ChapterWriter._resolve_expected_chars(
            {"word_count_target": 3000},
            {"agent_config": {"content": {"min_section_length": 5000}}},
        ) == 3000

    def test_falls_back_to_framework_min_section_length(self):
        assert ChapterWriter._resolve_expected_chars(
            {},
            {"agent_config": {"content": {"min_section_length": 5000}}},
        ) == 5000

    def test_defaults_to_2000_without_any_target(self):
        assert ChapterWriter._resolve_expected_chars({}, {}) == 2000
        assert ChapterWriter._resolve_expected_chars({}, None) == 2000

    def test_garbage_values_fall_back_to_default(self):
        assert ChapterWriter._resolve_expected_chars(
            {"word_count_target": "abc"}, {}
        ) == 2000

    def test_prompt_contains_length_directive(self, mock_prompts):
        writer = self._writer(mock_prompts)
        inp = make_input(framework_config={
            "name": "行业研究",
            "agent_config": {"content": {"min_section_length": 5000}},
        })

        prompt = writer._build_write_prompt(inp, RetryVariations(), "前文摘要")

        assert "篇幅要求" in prompt
        assert "5000" in prompt

    def test_pptx_prompt_has_no_length_directive(self, mock_prompts):
        writer = self._writer(mock_prompts)
        inp = make_input(
            output_format="pptx",
            framework_config={
                "name": "行业研究",
                "agent_config": {"content": {"min_section_length": 5000}},
            },
        )

        prompt = writer._build_write_prompt(inp, RetryVariations(), "前文摘要")

        assert "篇幅要求" not in prompt
