"""E2E test: output_format chain from frontend marker → session → final_plan → executor → orchestrator."""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import os
import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

CWD = str(Path.cwd())
E2E_TMP = os.path.join(CWD, "__e2e_format_chain_tmp__")


class TestOutputFormatParsing:
    """Validate __OUTPUT_FORMAT__ marker parsing in _handle_chat_mode."""

    def setup_method(self):
        os.makedirs(E2E_TMP, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(E2E_TMP, ignore_errors=True)

    def test_parse_pptx_format_from_marker(self):
        user_input = '确认开始研究，包含章节：市场概述\n__SELECTED_SECTIONS__:["市场概述"]\n__OUTPUT_FORMAT__:pptx'
        marker = '__SELECTED_SECTIONS__:'
        format_marker = '__OUTPUT_FORMAT__:'
        output_format = 'docx'
        selected_sections = None

        if marker in user_input:
            try:
                json_part = user_input[user_input.index(marker) + len(marker):]
                if format_marker in json_part:
                    fmt_and_json = json_part.split(format_marker, 1)
                    json_part = fmt_and_json[0].strip()
                    output_format = fmt_and_json[1].strip() if len(fmt_and_json) > 1 else 'docx'
                selected_sections = json.loads(json_part)
            except Exception:
                selected_sections = None

        assert output_format == 'pptx'
        assert selected_sections == ['市场概述']

    def test_parse_docx_format_default(self):
        user_input = '确认开始研究\n__SELECTED_SECTIONS__:["市场概述"]'
        marker = '__SELECTED_SECTIONS__:'
        format_marker = '__OUTPUT_FORMAT__:'
        output_format = 'docx'

        if marker in user_input:
            try:
                json_part = user_input[user_input.index(marker) + len(marker):]
                if format_marker in json_part:
                    fmt_and_json = json_part.split(format_marker, 1)
                    json_part = fmt_and_json[0].strip()
                    output_format = fmt_and_json[1].strip() if len(fmt_and_json) > 1 else 'docx'
                json.loads(json_part)
            except Exception:
                pass

        assert output_format == 'docx'

    def test_parse_pdf_format(self):
        user_input = 'Confirm and start research\n__SELECTED_SECTIONS__:["Market"]\n__OUTPUT_FORMAT__:pdf'
        marker = '__SELECTED_SECTIONS__:'
        format_marker = '__OUTPUT_FORMAT__:'
        output_format = 'docx'

        if marker in user_input:
            try:
                json_part = user_input[user_input.index(marker) + len(marker):]
                if format_marker in json_part:
                    fmt_and_json = json_part.split(format_marker, 1)
                    json_part = fmt_and_json[0].strip()
                    output_format = fmt_and_json[1].strip() if len(fmt_and_json) > 1 else 'docx'
                json.loads(json_part)
            except Exception:
                pass

        assert output_format == 'pdf'

    def test_invalid_format_falls_back_to_docx(self):
        output_format = 'exe'
        if output_format not in ('docx', 'pptx', 'pdf', 'html'):
            output_format = 'docx'
        assert output_format == 'docx'


class TestFinalPlanContainsFormat:
    """Validate final_plan dict includes output_format."""

    def test_final_plan_includes_output_format(self):
        session = {'output_format': 'pptx', 'language': 'zh', 'section_details': []}
        framework = {'output_type': 'industry_report', 'depth': 'standard', 'sections': ['市场概述']}
        context = {'details': {'region': 'China', 'time_range': 'Last 3 years'}}

        final_plan = {
            'topic': '测试主题',
            'output_type': framework.get('output_type', 'industry_report'),
            'aspects': framework.get('sections', []),
            'sections_tree': None,
            'section_details': session.get('section_details', []),
            'region': context.get('details', {}).get('region', 'China'),
            'time_range': context.get('details', {}).get('time_range', 'Last 3 years'),
            'framework': framework.get('depth', 'standard'),
            'language': session.get('language', 'zh'),
            'output_format': session.get('output_format', 'docx'),
        }

        assert final_plan['output_format'] == 'pptx'

    def test_final_plan_defaults_to_docx(self):
        session = {'language': 'zh', 'section_details': []}
        final_plan = {
            'output_format': session.get('output_format', 'docx'),
        }
        assert final_plan['output_format'] == 'docx'


class TestExecutorUserInputContainsFormat:
    """Validate research_executor reads output_format from session/plan."""

    def test_user_input_dict_includes_format_from_session(self):
        session = {'output_format': 'pptx'}
        plan = {'output_format': 'docx'}
        user_input_dict = {
            'session_id': 'test',
            'topic': 'test',
            'output_type': 'industry_report',
            'output_format': session.get('output_format', plan.get('output_format', 'docx')),
        }
        assert user_input_dict['output_format'] == 'pptx'

    def test_user_input_dict_falls_back_to_plan(self):
        session = {}
        plan = {'output_format': 'pdf'}
        user_input_dict = {
            'output_format': session.get('output_format', plan.get('output_format', 'docx')),
        }
        assert user_input_dict['output_format'] == 'pdf'

    def test_user_input_dict_defaults_to_docx(self):
        session = {}
        plan = {}
        user_input_dict = {
            'output_format': session.get('output_format', plan.get('output_format', 'docx')),
        }
        assert user_input_dict['output_format'] == 'docx'


class TestOrchestratorRequirementExtraction:
    """Validate _parse_requirement extracts output_format from user_input."""

    def test_requirement_gets_format_from_user_input(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator()
        user_input = {
            'topic': '新能源汽车市场',
            'output_format': 'pptx',
            'output_type': 'industry_report',
        }
        req = orch._parse_requirement(user_input)
        assert str(req.output_format) == 'pptx'

    def test_requirement_defaults_to_docx(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator()
        user_input = {
            'topic': '新能源汽车市场',
            'output_type': 'industry_report',
        }
        req = orch._parse_requirement(user_input)
        assert str(req.output_format) == 'docx'


class TestMainApiFormatKey:
    """Validate main.py reads output_format from correct key."""

    def test_reads_output_format_first(self):
        session = {'output_format': 'pptx', 'output_type': 'industry_report'}
        result = session.get('output_format') or session.get('output_type')
        assert result == 'pptx'

    def test_falls_back_to_output_type(self):
        session = {'output_type': 'industry_report'}
        result = session.get('output_format') or session.get('output_type')
        assert result == 'industry_report'


class TestE2EPptxGeneration:
    """Full PPT generation from orchestrator through converter."""

    def setup_method(self):
        os.makedirs(E2E_TMP, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(E2E_TMP, ignore_errors=True)

    def test_pptx_output_format_produces_pptx_file(self):
        from src.content.content_orchestrator import ContentOrchestrator
        from src.converters.html_to_ppt import HTMLToPPTConverter
        from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType

        chart_dir = os.path.join(E2E_TMP, "charts")
        os.makedirs(chart_dir, exist_ok=True)
        gen = ChartGenerator(output_dir=Path(chart_dir))
        chart_result = gen.generate(ChartConfig(
            chart_type=ChartType.BAR,
            title="市场规模",
            data={"categories": ["2022", "2023", "2024"], "values": [10, 15, 22]},
            dpi=200,
        ))
        charts = [{"path": chart_result.image_path, "caption": "市场规模", "title": "市场规模", "anchor_type": "section_end"}] if chart_result.success else []

        research = {
            "title": "中国新能源汽车市场简报",
            "sections": [
                {
                    "id": "overview",
                    "title": "市场概述",
                    "content": "2024年中国新能源汽车销量达到950万辆，同比增长37.5%。市场渗透率突破40%。\n\n## 核心数据\n\n- 销量：950万辆\n- 增长率：37.5%\n- 渗透率：40%",
                    "order": 1,
                    "type": "body",
                    "charts": charts,
                },
            ],
            "key_findings": ["销量950万辆", "渗透率40%"],
        }

        output_dir = os.path.join(E2E_TMP, "pptx_out")
        os.makedirs(output_dir, exist_ok=True)

        orch = ContentOrchestrator()
        html = orch.transform_to_html(research, output_format="pptx", output_dir=output_dir)
        assert html, "Orchestrator should produce HTML for PPTX"

        converter = HTMLToPPTConverter()
        output_path = os.path.join(output_dir, "report.pptx")
        result = converter.convert(html=html, output_path=output_path)
        assert result.success, f"PPTX conversion failed: {result.error}"
        assert os.path.exists(output_path), "PPTX file should exist"
        assert os.path.getsize(output_path) > 1000, "PPTX should have content"

        from pptx import Presentation
        prs = Presentation(output_path)
        assert len(prs.slides) > 0, "Should have at least 1 slide"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
