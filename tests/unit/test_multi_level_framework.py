"""Tests for multi-level research framework support (P0 changes).

Covers:
- _build_response() transparently passes framework_tree
- _format_framework() multi-level formatting
- _build_section_details_from_tree() helper
- _enter_framework_mode() builds sections_tree in framework dict
- _start_execution() passes sections_tree and section_details in final_plan
- _parse_requirement() uses section_details/sections_tree from user_input
- strategies.py sub_aspects injection in DATA_COLLECTION and DEEP_ANALYSIS agents
- result_aggregator framework skeleton matching for subsections
- framework_tree -> section_data_specs P0 alignment
- _match_content_to_sub_section helper
"""

import pytest
from unittest.mock import MagicMock, patch


# ============================================================
# 1. _build_response() transparently passes framework_tree
# ============================================================

class TestBuildResponseFrameworkTree:
    def test_framework_tree_passed_through(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        parsed = {
            'message': 'test',
            'action': 'enter_framework',
            'framework_sections': ['s1', 's2'],
            'framework_tree': [
                {'name': 's1', 'sub_sections': [{'name': 's1.1', 'points': ['p1']}]},
                {'name': 's2', 'sub_sections': []}
            ],
        }
        result = api._build_response(parsed, None, None)
        assert result['framework_tree'] == parsed['framework_tree']
        assert result['framework_sections'] == ['s1', 's2']

    def test_framework_tree_none_when_absent(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        parsed = {'message': 'test', 'action': 'continue_chat'}
        result = api._build_response(parsed, None, None)
        assert result.get('framework_tree') is None

    def test_framework_tree_empty_list(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        parsed = {'message': 'test', 'action': 'enter_framework', 'framework_tree': []}
        result = api._build_response(parsed, None, None)
        assert result['framework_tree'] == []


# ============================================================
# 2. _format_framework() multi-level formatting
# ============================================================

class TestFormatFrameworkMultiLevel:
    def test_sections_tree_three_level(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        framework = {
            'sections': ['核心财务指标', '竞争格局'],
            'sections_tree': [
                {
                    'name': '核心财务指标',
                    'sub_sections': [
                        {'name': '营收与利润趋势', 'points': ['年度营收规模', '归母净利润']},
                        {'name': '盈利能力指标', 'points': ['毛利率与净利率', 'ROE与ROIC']},
                    ]
                },
                {
                    'name': '竞争格局',
                    'sub_sections': [
                        {'name': '市场份额', 'points': ['CR4集中度']},
                    ]
                }
            ]
        }
        result = api._format_framework(framework)
        lines = result.split('\n')
        assert '1. 核心财务指标' in lines[0]
        assert '1.1 营收与利润趋势' in lines[1]
        assert '1.1.1 年度营收规模' in lines[2]
        assert '1.1.2 归母净利润' in lines[3]
        assert '1.2 盈利能力指标' in lines[4]
        assert '2. 竞争格局' in lines[7]
        assert '2.1 市场份额' in lines[8]

    def test_no_sections_tree_fallback_flat(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        framework = {'sections': ['Market Size', 'Competition'], 'section_details': {}}
        result = api._format_framework(framework)
        assert '1. Market Size' in result
        assert '2. Competition' in result
        assert '1.1' not in result

    def test_sections_tree_with_empty_points(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        framework = {
            'sections': ['Overview'],
            'sections_tree': [
                {'name': 'Overview', 'sub_sections': [{'name': 'Summary', 'points': []}]}
            ]
        }
        result = api._format_framework(framework)
        assert '1. Overview' in result
        assert '1.1 Summary' in result

    def test_sections_tree_with_no_sub_sections(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        framework = {
            'sections': ['Overview'],
            'sections_tree': [{'name': 'Overview', 'sub_sections': []}]
        }
        result = api._format_framework(framework)
        assert '1. Overview' in result
        assert '1.1' not in result


# ============================================================
# 3. _build_section_details_from_tree() helper
# ============================================================

class TestBuildSectionDetailsFromTree:
    def test_basic_tree(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        tree = [
            {
                'name': '核心财务指标',
                'sub_sections': [
                    {'name': '营收与利润', 'points': ['年度营收', '净利润']},
                    {'name': '盈利能力', 'points': ['ROE']},
                ]
            }
        ]
        result = api._build_section_details_from_tree(tree)
        assert len(result) == 1
        assert result[0]['name'] == '核心财务指标'
        assert len(result[0]['sub_sections']) == 2
        assert result[0]['sub_sections'][0]['name'] == '营收与利润'
        assert result[0]['sub_sections'][0]['points'] == ['年度营收', '净利润']
        assert result[0]['sub_sections'][1]['name'] == '盈利能力'
        assert result[0]['sub_sections'][1]['points'] == ['ROE']

    def test_empty_tree(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        assert api._build_section_details_from_tree(None) == []
        assert api._build_section_details_from_tree([]) == []

    def test_tree_without_sub_sections(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        tree = [{'name': 'Overview', 'sub_sections': []}]
        result = api._build_section_details_from_tree(tree)
        assert len(result) == 1
        assert result[0]['sub_sections'] == []

    def test_tree_missing_sub_sections_key(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        tree = [{'name': 'Overview'}]
        result = api._build_section_details_from_tree(tree)
        assert len(result) == 1
        assert result[0]['sub_sections'] == []

    def test_id_generation(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        tree = [{'name': 'Market Size', 'sub_sections': []}]
        result = api._build_section_details_from_tree(tree)
        assert result[0]['id'] == 'market_size'


# ============================================================
# 4. _enter_framework_mode() with sections_tree
# ============================================================

class TestEnterFrameworkModeSectionsTree:
    @pytest.mark.asyncio
    async def test_framework_tree_stored_in_framework_dict(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        api._l = lambda zh, en, lang='zh': zh if lang == 'zh' else en
        api._get_lang = lambda s: 'zh'
        api._sync_state_machine_to_framework = MagicMock()
        api._framework_response = MagicMock(return_value={'session_id': 'test'})

        fw_tree = [
            {'name': '核心财务指标', 'sub_sections': [{'name': '营收', 'points': ['年度营收']}]},
            {'name': '竞争格局', 'sub_sections': []},
        ]

        session = {
            'research_context': {
                '_suggested_sections': ['核心财务指标', '竞争格局'],
                '_framework_tree': fw_tree,
                'topic': '比亚迪',
                'details': {},
            },
            'mode': 'chat',
            'language': 'zh',
        }

        with patch('src.api.research_api.session_manager') as mock_sm:
            with patch('src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager') as mock_cm:
                mock_sm.get.return_value = session
                mock_cm.return_value.is_cancelled.return_value = False
                await api._enter_framework_mode('test', 'test_input')

        framework = session['research_context']['framework']
        assert 'sections_tree' in framework
        assert framework['sections_tree'] == fw_tree
        assert framework['sections'] == ['核心财务指标', '竞争格局']

    @pytest.mark.asyncio
    async def test_no_framework_tree_uses_flat_sections(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        api._l = lambda zh, en, lang='zh': zh if lang == 'zh' else en
        api._get_lang = lambda s: 'zh'
        api._sync_state_machine_to_framework = MagicMock()
        api._framework_response = MagicMock(return_value={'session_id': 'test'})

        session = {
            'research_context': {
                '_suggested_sections': ['Market Size', 'Competition'],
                'topic': 'EV Market',
                'details': {},
            },
            'mode': 'chat',
            'language': 'zh',
        }

        with patch('src.api.research_api.session_manager') as mock_sm:
            with patch('src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager') as mock_cm:
                mock_sm.get.return_value = session
                mock_cm.return_value.is_cancelled.return_value = False
                await api._enter_framework_mode('test', 'test_input')

        framework = session['research_context']['framework']
        assert framework.get('sections_tree') is None
        assert framework['sections'] == ['Market Size', 'Competition']


# ============================================================
# 5. _start_execution() passes sections_tree in final_plan
# ============================================================

class TestStartExecutionSectionsTree:
    @pytest.mark.asyncio
    async def test_final_plan_contains_sections_tree(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        api._l = lambda zh, en, lang='zh': zh if lang == 'zh' else en
        api._executor_tasks = {}

        fw_tree = [{'name': '核心财务', 'sub_sections': [{'name': '营收', 'points': ['年度营收']}]}]

        session = {
            'research_context': {
                'topic': '比亚迪',
                'framework': {
                    'sections': ['核心财务'],
                    'sections_tree': fw_tree,
                    'output_type': 'industry_report',
                    'depth': 'standard',
                },
                'details': {},
            },
            'mode': 'framework',
            'language': 'zh',
            'state_machine': MagicMock(),
            'current_step': 5,
        }
        session['state_machine'].transition = MagicMock()

        with patch('src.api.research_api.session_manager') as mock_sm, \
             patch('src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager') as mock_cm, \
             patch('src.api.research_api.asyncio') as mock_asyncio, \
             patch('src.core.progress_streamer.ProgressStreamer'):
            mock_sm.get.return_value = session
            mock_cm.return_value.is_paused.return_value = False
            mock_asyncio.create_task.return_value = MagicMock()
            mock_asyncio.create_task.return_value.add_done_callback = MagicMock()

            await api._start_execution('test')

        final_plan = session.get('final_plan', {})
        assert 'sections_tree' in final_plan
        assert final_plan['sections_tree'] == fw_tree
        assert 'section_details' in final_plan
        assert len(final_plan['section_details']) == 1
        assert final_plan['section_details'][0]['name'] == '核心财务'
        assert len(final_plan['section_details'][0]['sub_sections']) == 1

    @pytest.mark.asyncio
    async def test_final_plan_no_sections_tree(self):
        from src.api.research_api import ResearchAPI

        api = ResearchAPI.__new__(ResearchAPI)
        api._l = lambda zh, en, lang='zh': zh if lang == 'zh' else en
        api._executor_tasks = {}

        session = {
            'research_context': {
                'topic': 'EV Market',
                'framework': {
                    'sections': ['Market Size'],
                    'output_type': 'industry_report',
                    'depth': 'standard',
                },
                'details': {},
            },
            'mode': 'framework',
            'language': 'zh',
            'state_machine': MagicMock(),
            'current_step': 5,
        }
        session['state_machine'].transition = MagicMock()

        with patch('src.api.research_api.session_manager') as mock_sm, \
             patch('src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager') as mock_cm, \
             patch('src.api.research_api.asyncio') as mock_asyncio, \
             patch('src.core.progress_streamer.ProgressStreamer'):
            mock_sm.get.return_value = session
            mock_cm.return_value.is_paused.return_value = False
            mock_asyncio.create_task.return_value = MagicMock()
            mock_asyncio.create_task.return_value.add_done_callback = MagicMock()

            await api._start_execution('test')

        final_plan = session.get('final_plan', {})
        assert final_plan.get('sections_tree') is None
        assert final_plan.get('section_details') == []


# ============================================================
# 6. _parse_requirement() with section_details/sections_tree
# ============================================================

class TestParseRequirementSectionsTree:
    def test_uses_provided_section_details(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)

        section_details = [
            {
                'id': 'core_financial',
                'name': '核心财务指标',
                'content': '核心财务指标',
                'sub_sections': [{'name': '营收', 'points': ['年度营收']}]
            }
        ]

        user_input = {
            'topic': '比亚迪',
            'aspects': ['核心财务指标'],
            'section_details': section_details,
            'output_format': 'docx',
        }

        result = orch._parse_requirement(user_input)
        assert result.section_details == section_details
        assert len(result.section_details) == 1
        assert result.section_details[0].get('sub_sections') is not None

    def test_uses_sections_tree_when_no_section_details(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        orch._load_template_sections = MagicMock(return_value=[])
        orch._convert_section_ids_to_names = MagicMock(return_value=[])

        sections_tree = [
            {
                'name': '核心财务指标',
                'sub_sections': [{'name': '营收', 'points': ['年度营收']}]
            }
        ]

        user_input = {
            'topic': '比亚迪',
            'aspects': ['核心财务指标'],
            'sections_tree': sections_tree,
            'output_format': 'docx',
        }

        result = orch._parse_requirement(user_input)
        assert len(result.section_details) == 1
        assert result.section_details[0]['name'] == '核心财务指标'
        assert len(result.section_details[0].get('sub_sections', [])) == 1

    def test_fallback_flat_when_neither(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)

        user_input = {
            'topic': '比亚迪',
            'aspects': ['核心财务指标'],
            'output_format': 'docx',
        }

        result = orch._parse_requirement(user_input)
        assert len(result.section_details) == 1
        assert result.section_details[0].get('sub_sections') is None or \
               result.section_details[0].get('sub_sections') == []


# ============================================================
# 7. strategies.py sub_aspects injection
# ============================================================

class TestStrategiesSubAspects:
    def test_sub_aspects_in_dc_context(self):
        from src.core.decomposition.strategies import SectionDataSpec, SubSectionSpec
        spec = SectionDataSpec(
            section_id='section_0',
            name='核心财务指标',
            sub_sections=[
                SubSectionSpec(sub_section_id='sub_0_0', name='营收与利润', data_needs=['年度营收'], data_source_type='search'),
                SubSectionSpec(sub_section_id='sub_0_1', name='盈利能力', data_needs=['ROE'], data_source_type='search'),
            ]
        )
        sub_aspects = [sub.name for sub in spec.sub_sections]
        assert sub_aspects == ['营收与利润', '盈利能力']

        context = {
            "aspect": '核心财务指标',
            "topic": '比亚迪',
            "section_id": 'section_0',
            "data_needs": spec.all_data_needs,
            "search_data_needs": spec.search_data_needs,
            "sub_aspects": sub_aspects,
        }
        assert context['sub_aspects'] == ['营收与利润', '盈利能力']

    def test_sub_aspects_empty_when_no_spec(self):
        matched_spec = None
        sub_aspects = [sub.name for sub in matched_spec.sub_sections] if matched_spec and matched_spec.sub_sections else []
        assert sub_aspects == []

    def test_sub_aspects_empty_when_no_sub_sections(self):
        from src.core.decomposition.strategies import SectionDataSpec
        spec = SectionDataSpec(section_id='section_0', name='Market Size', sub_sections=[])
        sub_aspects = [sub.name for sub in spec.sub_sections] if spec and spec.sub_sections else []
        assert sub_aspects == []


# ============================================================
# 8. result_aggregator framework skeleton matching
# ============================================================

class TestResultAggregatorFrameworkSkeleton:
    def test_framework_skeleton_subsections(self):
        from src.core.orchestrator.aggregation.result_aggregator import (
            _build_subsections_from_skeleton
        )

        content = "### 营收与利润趋势\n\n2024年营收达到5000亿元，同比增长15%。\n\n### 盈利能力指标\n\nROE达到18%，高于行业平均水平。\n\n### 其他分析\n\n这是LLM自行添加的内容。"

        framework_sub_sections = [
            {'name': '营收与利润趋势', 'points': ['年度营收规模']},
            {'name': '盈利能力指标', 'points': ['ROE']},
        ]

        subsections = _build_subsections_from_skeleton(content, framework_sub_sections)
        assert len(subsections) == 2
        sub_names = [s['title'] for s in subsections]
        assert '营收与利润趋势' in sub_names
        assert '盈利能力指标' in sub_names

    def test_fallback_to_auto_parse_without_sub_sections(self):
        from src.core.orchestrator.aggregation.result_aggregator import (
            _parse_markdown_subsections
        )

        content = "### Revenue\n\nRevenue is growing.\n\n### Profit\n\nProfit is stable."
        result = _parse_markdown_subsections(content)
        assert len(result) >= 2
        titles = [r['title'] for r in result]
        assert any('Revenue' in t or '营收' in t for t in titles)


# ============================================================
# 9. framework_tree -> section_data_specs P0 alignment
# ============================================================

class TestFrameworkTreeSectionDataSpecsAlignment:
    def test_alignment_overrides_sub_section_names(self):
        from src.core.decomposition.strategies import (
            IndustryResearchStrategy, SectionDataSpec, SubSectionSpec
        )

        strategy = IndustryResearchStrategy()

        section_data_specs = [
            SectionDataSpec(
                section_id='section_0',
                name='核心财务指标',
                sub_sections=[
                    SubSectionSpec(sub_section_id='sub_0_0', name='收入分析', data_needs=['营收数据'], data_source_type='search'),
                    SubSectionSpec(sub_section_id='sub_0_1', name='利润分析', data_needs=['利润数据'], data_source_type='search'),
                ]
            )
        ]

        sections_tree = [
            {
                'name': '核心财务指标',
                'sub_sections': [
                    {'name': '营收与利润趋势', 'points': ['年度营收规模', '归母净利润']},
                    {'name': '盈利能力指标', 'points': ['ROE', '毛利率']},
                ]
            }
        ]

        aligned = strategy._align_section_data_specs_with_tree(section_data_specs, sections_tree)
        assert aligned[0].sub_sections[0].name == '营收与利润趋势'
        assert aligned[0].sub_sections[0].data_needs == ['年度营收规模', '归母净利润']
        assert aligned[0].sub_sections[1].name == '盈利能力指标'
        assert aligned[0].sub_sections[1].data_needs == ['ROE', '毛利率']

    def test_alignment_appends_new_sub_sections(self):
        from src.core.decomposition.strategies import (
            IndustryResearchStrategy, SectionDataSpec, SubSectionSpec
        )

        strategy = IndustryResearchStrategy()

        section_data_specs = [
            SectionDataSpec(
                section_id='section_0',
                name='核心财务指标',
                sub_sections=[
                    SubSectionSpec(sub_section_id='sub_0_0', name='营收', data_needs=['营收数据'], data_source_type='search'),
                ]
            )
        ]

        sections_tree = [
            {
                'name': '核心财务指标',
                'sub_sections': [
                    {'name': '营收与利润', 'points': ['年度营收']},
                    {'name': '盈利能力', 'points': ['ROE']},
                ]
            }
        ]

        aligned = strategy._align_section_data_specs_with_tree(section_data_specs, sections_tree)
        assert len(aligned[0].sub_sections) == 2
        assert aligned[0].sub_sections[1].name == '盈利能力'
        assert aligned[0].sub_sections[1].data_needs == ['ROE']

    def test_no_alignment_when_no_tree(self):
        from src.core.decomposition.strategies import (
            IndustryResearchStrategy, SectionDataSpec, SubSectionSpec
        )

        strategy = IndustryResearchStrategy()

        specs = [
            SectionDataSpec(
                section_id='section_0',
                name='核心财务',
                sub_sections=[
                    SubSectionSpec(sub_section_id='sub_0_0', name='营收', data_needs=['营收数据'], data_source_type='search'),
                ]
            )
        ]

        aligned = strategy._align_section_data_specs_with_tree(specs, None)
        assert aligned[0].sub_sections[0].name == '营收'
        assert aligned[0].sub_sections[0].data_needs == ['营收数据']


# ============================================================
# 10. _match_content_to_sub_section
# ============================================================

class TestMatchContentToSubSection:
    def test_match_subsection_by_normalized_title(self):
        from src.core.orchestrator.aggregation.result_aggregator import _match_content_to_sub_section

        content = "### 营收与利润趋势\n\n2024年营收5000亿。\n\n### 盈利能力指标\n\nROE达到18%。"
        sub_section = {'name': '营收与利润趋势', 'points': ['年度营收规模']}
        result = _match_content_to_sub_section(content, sub_section)
        assert result is not None
        assert '5000亿' in result

    def test_match_fuzzy_normalized(self):
        from src.core.orchestrator.aggregation.result_aggregator import _match_content_to_sub_section

        content = "### 营收与利润  \n\n2024年营收5000亿。\n\n### 盈利能力\n\nROE达到18%。"
        sub_section = {'name': '营收与利润', 'points': []}
        result = _match_content_to_sub_section(content, sub_section)
        assert result is not None
        assert '5000亿' in result

    def test_no_match_returns_placeholder(self):
        from src.core.orchestrator.aggregation.result_aggregator import _match_content_to_sub_section

        content = "### 完全不相关的内容\n\nSome text here."
        sub_section = {'name': '营收与利润趋势', 'points': ['年度营收']}
        result = _match_content_to_sub_section(content, sub_section)
        assert result is not None
        assert len(result) > 0


# ============================================================
# 11. Frontend type extensions
# ============================================================

class TestFrontendTypes:
    def test_framework_section_type_exists(self):
        import os
        api_ts_path = os.path.join(os.path.dirname(__file__), '..', '..', 'web', 'src', 'types', 'api.ts')
        if not os.path.exists(api_ts_path):
            pytest.skip("Frontend types not available for Python test")

        with open(api_ts_path, 'r', encoding='utf-8') as f:
            content = f.read()

        assert 'FrameworkSection' in content or 'sections_tree' in content


# ============================================================
# 12. Data flow integrity: research_executor passes sections_tree
# ============================================================

class TestDataFlowIntegrity:
    def test_research_executor_passes_sections_tree(self):
        import ast
        with open('src/api/research_executor.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'sections_tree' in content, "research_executor.py must include sections_tree in user_input_dict"
        assert 'section_details' in content, "research_executor.py must include section_details in user_input_dict"
        assert 'plan.get("sections_tree")' in content, "sections_tree should come from plan parameter"
        assert 'plan.get("section_details"' in content, "section_details should come from plan parameter"

    def test_generic_agent_passes_sub_aspects(self):
        with open('src/core/agents/generic_agent.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'sub_aspects=self._context.get("sub_aspects")' in content, \
            "generic_agent.py must pass sub_aspects from context to _build_analysis_prompt_with_data"

    def test_framework_modify_includes_new_framework_tree(self):
        with open('src/api/research_api.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'new_framework_tree' in content, \
            "_llm_framework_modify prompt must include new_framework_tree in output schema"

    def test_json_output_schema_includes_framework_tree(self):
        with open('src/api/research_api.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert '"framework_tree"' in content, \
            "_JSON_OUTPUT_SCHEMA must include framework_tree field definition"


# ============================================================
# 9. Gap fixes: prompt builders, LLM guidance, schema rules
# ============================================================

class TestBuildDataCollectionPromptSubAspects:
    def test_sub_aspects_injected_into_prompt(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_focus_areas.return_value = []
        config.get_priority_sources.return_value = []
        prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=["NLP", "CV", "Robotics"])
        assert "NLP" in prompt
        assert "CV" in prompt
        assert "Robotics" in prompt

    def test_sub_aspects_none_no_extra_section(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_focus_areas.return_value = []
        config.get_priority_sources.return_value = []
        prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=None)
        assert "Sub-topics" not in prompt

    def test_call_site_passes_sub_aspects(self):
        with open('src/core/decomposition/strategies.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert '_build_data_collection_prompt(topic, aspect, framework_config, sub_aspects=' in content, \
            "DATA_COLLECTION call site must pass sub_aspects to _build_data_collection_prompt"


class TestBuildAnalysisPromptSubAspects:
    def test_sub_aspects_injected_into_prompt(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_analysis_depth.return_value = "deep"
        config.get_key_metrics.return_value = []
        prompt = decomposer._build_analysis_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
        assert "NLP" in prompt
        assert "CV" in prompt

    def test_sub_aspects_none_no_extra_section(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_analysis_depth.return_value = "deep"
        config.get_key_metrics.return_value = []
        prompt = decomposer._build_analysis_prompt("AI", "market", config, sub_aspects=None)
        assert "Sub-topics" not in prompt

    def test_call_site_passes_sub_aspects(self):
        with open('src/core/decomposition/strategies.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert '_build_analysis_prompt(topic, aspect, framework_config, sub_aspects=' in content, \
            "DEEP_ANALYSIS call site must pass sub_aspects to _build_analysis_prompt"


class TestFrameworkTreeLLMGuidance:
    def test_context_summary_mentions_framework_tree(self):
        with open('src/api/research_api.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'framework_tree' in content.split('NOTE:')[1].split('\n')[0] if 'NOTE:' in content else False, \
            "context_summary NOTE must mention framework_tree"
        assert 'Also output "framework_tree"' in content or 'also output "framework_tree"' in content or 'ALSO output "framework_tree"' in content, \
            "context_summary must instruct LLM to output framework_tree for multi-level topics"

    def test_framework_confirm_state_mentions_framework_tree(self):
        with open('src/api/research_api.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'ConversationState.FRAMEWORK_CONFIRM' in content
        assert 'framework_tree' in content, "research_api.py must reference framework_tree"
        assert 'Also output "framework_tree"' in content or 'also output "framework_tree"' in content or 'ALSO output "framework_tree"' in content, \
            "FRAMEWORK_CONFIRM guidance or context_summary must instruct LLM to output framework_tree"

    def test_json_schema_has_framework_tree_rule(self):
        from src.api.research_api import ResearchAPI
        assert 'framework_tree' in ResearchAPI._JSON_OUTPUT_SCHEMA
        assert 'prefer' in ResearchAPI._JSON_OUTPUT_SCHEMA.lower() or 'RULE' in ResearchAPI._JSON_OUTPUT_SCHEMA, \
            "_JSON_OUTPUT_SCHEMA must include rule about preferring framework_tree for multi-level topics"


# ============================================================
# 10. B5: HTML/DOCX multi-level rendering
# ============================================================

class TestResultAggregatorPointsField:
    def test_build_subsections_from_skeleton_includes_points(self):
        from src.core.orchestrator.aggregation.result_aggregator import _build_subsections_from_skeleton
        framework_subs = [
            {"name": "Market Size", "points": ["Revenue", "Growth Rate"]},
            {"name": "Competition", "points": []},
        ]
        content = "### Market Size\nRevenue data here.\n### Competition\nCompetitor list."
        result = _build_subsections_from_skeleton(content, framework_subs)
        assert len(result) >= 1
        market_sub = [s for s in result if s["title"] == "Market Size"][0]
        assert market_sub["points"] == ["Revenue", "Growth Rate"]
        comp_sub = [s for s in result if s["title"] == "Competition"][0]
        assert comp_sub["points"] == []

    def test_parse_markdown_subsections_includes_empty_points(self):
        from src.core.orchestrator.aggregation.result_aggregator import _parse_markdown_subsections
        content = "### Sub1\nSome content\n### Sub2\nMore content"
        result = _parse_markdown_subsections(content)
        assert all("points" in s for s in result)
        assert all(s["points"] == [] for s in result)


class TestContentSectionPointsField:
    def test_content_section_has_points_field(self):
        from src.content.content_orchestrator import ContentSection
        cs = ContentSection(id="test", title="Test", content="body")
        assert cs.points == []

    def test_content_section_with_points(self):
        from src.content.content_orchestrator import ContentSection
        cs = ContentSection(id="test", title="Test", content="body", points=["p1", "p2"])
        assert cs.points == ["p1", "p2"]


class TestHTMLFallbackThreeLevelTOC:
    def test_toc_includes_three_level_entries(self):
        from src.content.content_orchestrator import ContentSection, ContentOrchestrator
        co = ContentOrchestrator.__new__(ContentOrchestrator)
        sections = [
            ContentSection(
                id="s1", title="Market", content="", order=0,
                subsections=[
                    ContentSection(
                        id="s1_1", title="Size", content="", order=0,
                        points=["Revenue", "Growth"]
                    )
                ]
            )
        ]
        html = co._generate_word_html("Report", sections, [], [])
        assert "1.1.1 Revenue" in html
        assert "1.1.2 Growth" in html
        assert 'margin-left: 40px' in html


class TestHTMLFallbackThreeLevelRendering:
    def test_render_section_html_with_points(self):
        from src.content.content_orchestrator import ContentSection, ContentOrchestrator
        co = ContentOrchestrator.__new__(ContentOrchestrator)
        section = ContentSection(
            id="s1", title="Market", content="Overview text",
            subsections=[
                ContentSection(
                    id="s1_1", title="Size", content="### Revenue\nRev data\n### Growth\nGrowth data",
                    points=["Revenue", "Growth"]
                )
            ]
        )
        html = co._render_section_html(section)
        assert '<h4 class="sub-subsection-title">Revenue</h4>' in html
        assert '<h4 class="sub-subsection-title">Growth</h4>' in html
        assert '<h3 class="subsection-title">Size</h3>' in html

    def test_render_section_html_without_points(self):
        from src.content.content_orchestrator import ContentSection, ContentOrchestrator
        co = ContentOrchestrator.__new__(ContentOrchestrator)
        section = ContentSection(
            id="s1", title="Market", content="Overview",
            subsections=[
                ContentSection(id="s1_1", title="Size", content="Size data", points=[])
            ]
        )
        html = co._render_section_html(section)
        assert '<h3 class="subsection-title">Size</h3>' in html
        assert 'sub-subsection-title' not in html


class TestHTMLTemplateSubsectionFixes:
    def test_word_default_uses_h3_for_subsection(self):
        with open('config/document_templates/word_default.html', 'r', encoding='utf-8') as f:
            content = f.read()
        assert '<h3 class="subsection-title">{{ subsection.title }}</h3>' in content, \
            "word_default.html must use <h3> for subsections, not <h2>"

    def test_word_default_toc_includes_subsections(self):
        with open('config/document_templates/word_default.html', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'section.subsections' in content, \
            "word_default.html TOC must iterate section.subsections"

    def test_word_default_section_content_not_dropped(self):
        with open('config/document_templates/word_default.html', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'section.content' in content, \
            "word_default.html must render section.content even when subsections exist"

    def test_word_research_uses_h3_for_subsection(self):
        with open('config/document_templates/word_research_report.html', 'r', encoding='utf-8') as f:
            content = f.read()
        assert '<h3 class="subsection-title">{{ subsection.title }}</h3>' in content, \
            "word_research_report.html must use <h3> for subsections"

    def test_templates_have_sub_subsection_style(self):
        for tpl in ['config/document_templates/word_default.html', 'config/document_templates/word_research_report.html']:
            with open(tpl, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'sub-subsection-title' in content, \
                f"{tpl} must have sub-subsection-title CSS class"


class TestDOCXTocThreeLevel:
    def test_generate_toc_includes_level3(self):
        from src.core.orchestrator.output.document_generator import DocumentGenerator
        from src.core.orchestrator.output.document_generator import DocumentConfig
        config = DocumentConfig()
        dg = DocumentGenerator(config)
        dg._content = [
            {"type": "heading", "text": "Chapter 1", "level": 1},
            {"type": "heading", "text": "Section 1.1", "level": 2},
            {"type": "heading", "text": "Point 1.1.1", "level": 3},
            {"type": "heading", "text": "Point 1.1.2", "level": 3},
            {"type": "heading", "text": "Chapter 2", "level": 1},
        ]
        toc = dg._generate_toc()
        assert "1.1.1 Point 1.1.1" in toc
        assert "1.1.2 Point 1.1.2" in toc


class TestHTMLToWordH4Size:
    def test_default_styles_include_h4_size(self):
        from src.converters.html_to_word import HTMLToWordConverter
        assert "h4_size" in HTMLToWordConverter.DEFAULT_STYLES
        assert HTMLToWordConverter.DEFAULT_STYLES["h4_size"] == 14

    def test_apply_heading_style_sub_subsection(self):
        with open('src/converters/html_to_word.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'sub-subsection-title' in content, \
            "html_to_word.py must handle sub-subsection-title CSS class"


class TestExtractPointContent:
    def test_extract_point_content_finds_heading(self):
        from src.content.content_orchestrator import ContentOrchestrator
        content = "### Revenue\nRevenue data here.\n### Growth\nGrowth data."
        result = ContentOrchestrator._extract_point_content(content, "Revenue")
        assert "Revenue data here." in result
        assert "Growth" not in result

    def test_extract_point_content_no_match(self):
        from src.content.content_orchestrator import ContentOrchestrator
        content = "### Other\nSome content."
        result = ContentOrchestrator._extract_point_content(content, "Revenue")
        assert result == ""

    def test_extract_point_content_stops_at_next_heading(self):
        from src.content.content_orchestrator import ContentOrchestrator
        content = "### Revenue\nRev data\n### Growth\nGrowth data"
        result = ContentOrchestrator._extract_point_content(content, "Revenue")
        assert "Rev data" in result
        assert "Growth" not in result


class TestDocGenExtractPointText:
    def test_extract_point_text(self):
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        content = "### Revenue\nRevenue data here.\n### Growth\nGrowth data."
        result = DocumentGenerationAgent._extract_point_text(content, "Revenue")
        assert "Revenue data here." in result
        assert "Growth" not in result


# ============================================================
# 11. Bilingual support for multi-level rendering
# ============================================================

class TestBilingualSubAspectsInjection:
    def test_data_collection_prompt_zh(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        from src.core.i18n import set_language, Language
        set_language(Language.ZH)
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_focus_areas.return_value = []
        config.get_priority_sources.return_value = []
        prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
        assert "子主题" in prompt or "数据采集" in prompt
        set_language(Language.EN)

    def test_data_collection_prompt_en(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        from src.core.i18n import set_language, Language
        set_language(Language.EN)
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_focus_areas.return_value = []
        config.get_priority_sources.return_value = []
        prompt = decomposer._build_data_collection_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
        assert "Sub-topics" in prompt
        set_language(Language.ZH)

    def test_analysis_prompt_zh(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        from src.core.i18n import set_language, Language
        set_language(Language.ZH)
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_analysis_depth.return_value = "deep"
        config.get_key_metrics.return_value = []
        prompt = decomposer._build_analysis_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
        assert "子主题" in prompt or "分析" in prompt
        set_language(Language.EN)

    def test_analysis_prompt_en(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy
        from src.core.i18n import set_language, Language
        set_language(Language.EN)
        decomposer = IndustryResearchStrategy.__new__(IndustryResearchStrategy)
        config = MagicMock()
        config.get_analysis_depth.return_value = "deep"
        config.get_key_metrics.return_value = []
        prompt = decomposer._build_analysis_prompt("AI", "market", config, sub_aspects=["NLP", "CV"])
        assert "Sub-topics" in prompt
        set_language(Language.ZH)


class TestBilingualDocxToc:
    def test_toc_empty_zh(self):
        from src.core.orchestrator.output.document_generator import DocumentGenerator, DocumentConfig
        from src.core.i18n import set_language, Language
        set_language(Language.ZH)
        dg = DocumentGenerator(DocumentConfig())
        dg._content = []
        toc = dg._generate_toc()
        assert "无章节内容" in toc
        set_language(Language.EN)

    def test_toc_empty_en(self):
        from src.core.orchestrator.output.document_generator import DocumentGenerator, DocumentConfig
        from src.core.i18n import set_language, Language
        set_language(Language.EN)
        dg = DocumentGenerator(DocumentConfig())
        dg._content = []
        toc = dg._generate_toc()
        assert "No section content" in toc
        set_language(Language.ZH)
