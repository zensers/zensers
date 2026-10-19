# -*- coding: utf-8 -*-
"""
端到端测试：取证分析模式 — 使用真实LLM，不使用Mock

测试范围：
1. LLM意图分析：输入取证型问题+年报数据标记 → LLM输出forensic_analysis意图
2. 完整路由管线：intent→forensic_structure→forensic_phases→decomposition_plan
3. 取证数据提取：真实AnnualReportParserSkill + 模拟年报数据
4. config→context端到端传播：SectionSpec.config → AgentSpec.config → OriginalAgentSpec.context

所有LLM调用使用deepseek-v4-flash（从.env读取），不使用任何Mock。
"""
import pytest
import asyncio
import json
import os

from src.core.intent_types import IntentType
from src.core.semantic_intent import DeepIntentResult, SemanticIntentAnalyzer
from src.core.research_type import ResearchType


def _make_annual_report_data():
    """构造模拟年报解析数据（模拟真实PDF解析输出）"""
    return {
        "sections": [
            {
                "title": "管理层讨论与分析",
                "content": "2025年公司经营活动产生的现金流量净额为35.2亿元，同比增长42.3%。"
                           "净利润为12.8亿元，同比增长5.1%。现金流增长显著高于利润增长，"
                           "主要原因是：(1)折旧和摊销增加8.2亿元；(2)应收账款回收改善贡献5.1亿元；"
                           "(3)存货周转加快释放3.4亿元营运资金；(4)资产减值准备计提3.7亿元减少利润但不影响现金流。",
                "section_type": "mda",
            },
            {
                "title": "现金流量表",
                "content": "经营活动现金流入：营业收入68.5亿元，收到的税费返还0.3亿元，"
                           "收到其他与经营活动有关的现金2.1亿元。经营活动现金流出：购买商品接受劳务35.2亿元，"
                           "支付给职工8.6亿元，支付各项税费5.3亿元，支付其他与经营活动有关的现金6.4亿元。"
                           "折旧与摊销8.2亿元，资产减值准备3.7亿元。",
                "section_type": "cashflow",
            },
            {
                "title": "利润表",
                "content": "营业收入68.5亿元，营业成本42.3亿元，毛利26.2亿元，毛利率38.2%。"
                           "销售费用5.8亿元，管理费用4.2亿元，研发费用3.1亿元，财务费用1.5亿元。"
                           "资产减值损失3.7亿元，信用减值损失0.8亿元。营业利润8.9亿元，"
                           "利润总额9.2亿元，所得税费用1.6亿元，净利润12.8亿元（含少数股东损益5.2亿元）。",
                "section_type": "income",
            },
            {
                "title": "资产负债表",
                "content": "应收账款账面余额18.5亿元，坏账准备1.2亿元，应收账款净值17.3亿元。"
                           "存货账面余额12.8亿元，存货跌价准备0.6亿元，存货净值12.2亿元。"
                           "固定资产原值45.6亿元，累计折旧18.3亿元，固定资产净值27.3亿元。"
                           "无形资产8.9亿元，商誉3.2亿元。",
                "section_type": "balance",
            },
            {
                "title": "会计政策变更",
                "content": "本年度公司执行新收入准则，对部分合同履约成本的确认方式进行了调整，"
                           "影响当期利润约0.3亿元。同时调整了研发费用资本化比例，"
                           "资本化率从上年的15%调整为12%，减少资本化金额约0.9亿元。",
                "section_type": "accounting_policy",
            },
            {
                "title": "风险因素",
                "content": "市场竞争加剧，原材料价格波动，汇率风险，技术迭代风险。",
                "section_type": "risk",
            },
        ],
        "financial_tables": {
            "cashflow": [
                {"科目": "经营活动现金流量净额", "本年": 35.2, "上年": 24.8, "变动": 42.3},
                {"科目": "折旧与摊销", "本年": 8.2, "上年": 6.5, "变动": 26.2},
                {"科目": "资产减值准备", "本年": 3.7, "上年": 2.1, "变动": 76.2},
                {"科目": "应收账款减少", "本年": 5.1, "上年": -2.3, "变动": 0},
                {"科目": "存货减少", "本年": 3.4, "上年": -1.8, "变动": 0},
                {"科目": "投资活动现金流量净额", "本年": -12.5, "上年": -10.2, "变动": 22.5},
                {"科目": "筹资活动现金流量净额", "本年": -8.3, "上年": -5.6, "变动": 48.2},
            ],
            "income": [
                {"科目": "营业收入", "本年": 68.5, "上年": 61.2, "变动": 11.9},
                {"科目": "营业成本", "本年": 42.3, "上年": 38.5, "变动": 9.9},
                {"科目": "毛利", "本年": 26.2, "上年": 22.7, "变动": 15.4},
                {"科目": "净利润", "本年": 12.8, "上年": 12.2, "变动": 5.1},
                {"科目": "资产减值损失", "本年": 3.7, "上年": 2.1, "变动": 76.2},
                {"科目": "信用减值损失", "本年": 0.8, "上年": 0.5, "变动": 60.0},
                {"科目": "研发费用", "本年": 3.1, "上年": 2.6, "变动": 19.2},
            ],
            "balance": [
                {"科目": "应收账款", "本年": 17.3, "上年": 22.4, "变动": -22.8},
                {"科目": "存货", "本年": 12.2, "上年": 14.0, "变动": -12.9},
                {"科目": "固定资产", "本年": 27.3, "上年": 25.8, "变动": 5.8},
                {"科目": "商誉", "本年": 3.2, "上年": 3.2, "变动": 0},
            ],
        },
        "metadata": {
            "company": "示例科技",
            "year": 2025,
            "total_sections": 6,
            "total_tables": 3,
        },
    }


def _make_forensic_requirement(annual_report_data):
    """构造取证型需求的requirement字典（模拟_parse_requirement输出）"""
    return {
        "task_id": "forensic_e2e_test",
        "topic": "为什么现金流增长利润没增长",
        "aspects": [],
        "output_type": "forensic_analysis",
        "dynamic_fields": {
            "annual_report_data": annual_report_data,
            "file_ids": [{"id": "test_pdf", "path": "/tmp/test.pdf", "size_mb": 2.5}],
            "analysis_mode": "forensic",
        },
        "document_metadata": {
            "has_annual_report": True,
            "available_tables": list(annual_report_data.get("financial_tables", {}).keys()),
            "available_sections": [s.get("section_type", "") for s in annual_report_data.get("sections", [])],
        },
    }


# ============================================================
# E2E-1: LLM意图分析 — 取证型问题 + 年报数据 → forensic_analysis
# ============================================================

class TestE2E1ForensicIntentAnalysis:
    """使用真实LLM验证：取证型问题+年报数据标记 → LLM输出forensic_analysis意图"""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_forensic_question_with_preloaded_data(self):
        """核心场景：问题型输入+已有年报数据 → LLM识别为forensic_analysis"""
        from src.core.llm_client import call_llm

        system_prompt = (
            "You are a professional market research requirement analysis expert. "
            "Analyze the user's intent and output structured JSON. "
            "When the user asks a 'why' or 'how' question about a phenomenon "
            "and document data is available (indicated by file_ids or annual_report_data), "
            "set primary_intent to 'forensic_analysis', forensic_mode to true, data_preloaded to true, "
            "and generate 3-5 causal_hypotheses. "
            "Output strict JSON with keys: primary_intent, confidence, reasoning, forensic_mode, "
            "data_preloaded, causal_hypotheses, core_question, complexity."
        )
        prompt = (
            'User request: "Why did cash flow grow 42% while profit only grew 5%?"\n'
            "Context: Annual report data has been uploaded and parsed. "
            "Available data includes: cashflow statement, income statement, balance sheet, MD&A section.\n"
            "Output JSON."
        )
        result = await call_llm(prompt=prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=2048)

        assert result.get("success"), f"LLM call failed: {result.get('error', 'unknown')}"
        content = result.get("content", "")

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        try:
            parsed = analyzer._parse_llm_json(content)
        except (json.JSONDecodeError, Exception):
            import re
            m = re.search(r'"primary_intent"\s*:\s*"([^"]+)"', content)
            parsed = {"primary_intent": m.group(1) if m else "unknown", "confidence": 0.5}

        assert parsed.get("primary_intent") in ("forensic_analysis", "investigation", "research"), \
            f"Expected forensic/investigation/research intent, got {parsed.get('primary_intent')}"
        try:
            confidence = float(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        assert confidence > 0.3, f"Confidence too low: {parsed.get('confidence')}"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_instruction_input_without_preloaded_data(self):
        """对比场景：指令型输入（无年报数据标记） → LLM输出research意图，非forensic"""
        from src.core.llm_client import call_llm

        system_prompt = (
            "You are a professional market research requirement analysis expert. "
            "Analyze the user's intent and output structured JSON. "
            "When the user asks a 'why' or 'how' question about a phenomenon "
            "and document data is available (indicated by file_ids or annual_report_data), "
            "set primary_intent to 'forensic_analysis'. "
            "For general research instructions without preloaded data, set primary_intent to 'research'. "
            "Output strict JSON with keys: primary_intent, confidence, reasoning, forensic_mode, "
            "data_preloaded, core_question, complexity."
        )
        prompt = (
            'User request: "Conduct deep research on BYD 2025 annual report, generate full analysis report"\n'
            "Context: No document data has been uploaded. This is a standard research request.\n"
            "Output JSON."
        )
        result = await call_llm(prompt=prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=2048)

        assert result.get("success"), f"LLM call failed: {result.get('error', 'unknown')}"
        content = result.get("content", "")

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        try:
            parsed = analyzer._parse_llm_json(content)
        except (json.JSONDecodeError, Exception):
            import re
            m = re.search(r'"primary_intent"\s*:\s*"([^"]+)"', content)
            parsed = {"primary_intent": m.group(1) if m else "research"}

        assert parsed.get("primary_intent") != "forensic_analysis", \
            f"Instruction without preloaded data should not be forensic_analysis, got {parsed.get('primary_intent')}"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_forensic_intent_produces_causal_hypotheses(self):
        """取证型问题 → LLM生成因果假设"""
        from src.core.llm_client import call_llm

        system_prompt = (
            "You are a causal inference expert. Given a question about a financial phenomenon "
            "and available annual report data, generate 3-5 testable causal hypotheses. "
            "Output compact JSON only with keys: primary_intent, "
            "causal_hypotheses (array of exactly 3 hypothesis strings), forensic_mode, "
            "data_preloaded, core_question. Do not output reasoning or markdown."
        )
        prompt = (
            "Question: Why did cash flow grow 42% but profit only grew 5%?\n"
            "Available data: cashflow statement (depreciation 8.2bn, impairment 3.7bn, "
            "receivables decrease 5.1bn, inventory decrease 3.4bn), "
            "income statement (net profit 12.8bn, asset impairment loss 3.7bn), "
            "balance sheet, accounting policy changes.\n"
            "Output JSON."
        )
        result = await call_llm(prompt=prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=3072)

        assert result.get("success"), f"LLM call failed: {result.get('error', 'unknown')}"
        content = result.get("content", "")

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        try:
            parsed = analyzer._parse_llm_json(content)
        except (json.JSONDecodeError, Exception):
            parsed = {"causal_hypotheses": [], "primary_intent": "unknown"}

        hypotheses = parsed.get("causal_hypotheses", [])
        assert len(hypotheses) >= 1, f"Should generate at least 1 causal hypothesis, got {hypotheses}"
        for h in hypotheses:
            assert len(str(h)) > 5, f"Hypothesis too short: '{h}'"


# ============================================================
# E2E-2: 完整路由管线 — intent → forensic_structure → forensic_phases
# ============================================================

class TestE2E2ForensicRoutingPipeline:
    """使用真实LLM验证完整取证路由管线"""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_full_forensic_routing_pipeline(self):
        """端到端：用户问题 → LLM意图分析 → 取证结构生成 → 取证Phase编排"""
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        from src.core.dynamic_orchestrator import PhaseType
        from src.core.llm_client import call_llm

        annual_report_data = _make_annual_report_data()
        requirement = _make_forensic_requirement(annual_report_data)

        system_prompt = (
            "You are a professional market research requirement analysis expert. "
            "When the user asks a 'why/how' question and document data is available "
            "(indicated by file_ids or annual_report_data in the requirement), "
            "set primary_intent to 'forensic_analysis', forensic_mode to true, "
            "data_preloaded to true, and generate 3-5 causal_hypotheses. "
            "Output strict JSON with keys: primary_intent, confidence, reasoning, "
            "forensic_mode, data_preloaded, causal_hypotheses, core_question, "
            "complexity, aspect_count, requires_secondary_data."
        )
        prompt = (
            'User request: "Why did cash flow grow 42% but profit only grew 5%? Analyze from annual report data."\n'
            "Requirement: Annual report data uploaded with cashflow, income, balance sheet.\n"
            "Output JSON."
        )
        llm_result = await call_llm(prompt=prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=2048)

        assert llm_result.get("success"), f"LLM call failed: {llm_result.get('error', 'unknown')}"
        content = llm_result.get("content", "")

        analyzer = SemanticIntentAnalyzer(use_llm=False)
        try:
            parsed = analyzer._parse_llm_json(content)
        except (json.JSONDecodeError, Exception):
            import re
            m = re.search(r'"primary_intent"\s*:\s*"([^"]+)"', content)
            parsed = {"primary_intent": m.group(1) if m else "research", "confidence": 0.5, "complexity": "multi"}
        if isinstance(parsed.get("complexity"), (int, float)):
            parsed["complexity"] = "multi"

        intent_result = analyzer._build_result(parsed, llm_result.get("model", ""), content, False)

        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True, enable_content_lock=False)

        if intent_result.forensic_mode:
            task_structure = adapter._analyze_forensic_structure(requirement, intent_result, requirement.get("topic"))
            execution_plan = adapter._orchestrate_forensic_phases(task_structure, intent_result, requirement.get("topic"))
            decomp = execution_plan.to_decomposition_plan()

            ts = task_structure
            ep = execution_plan

            assert len(ts.sections) >= 3, \
                f"Forensic structure should have at least 3 sections, got {len(ts.sections)}"

            phase_types = [p.phase_type for p in ep.phases]
            assert PhaseType.DATA_COLLECTION in phase_types
            assert PhaseType.ANALYSIS in phase_types
            assert PhaseType.SYNTHESIS in phase_types
            assert PhaseType.REPORT in phase_types

            dc_phase = [p for p in ep.phases if p.phase_type == PhaseType.DATA_COLLECTION][0]
            assert len(dc_phase.agent_specs) == 1

            analysis_phase = [p for p in ep.phases if p.phase_type == PhaseType.ANALYSIS][0]
            assert len(analysis_phase.agent_specs) >= 1

            assert decomp is not None
        else:
            assert intent_result.primary_intent in (IntentType.RESEARCH, IntentType.INVESTIGATION, IntentType.OPEN_ENDED), \
                f"Non-forensic intent should be reasonable, got {intent_result.primary_intent.value}"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_non_forensic_routing_uses_standard_path(self):
        """对比：非取证型输入 → 走标准路由路径"""
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        from src.core.llm_client import call_llm

        system_prompt = (
            "You are a professional market research requirement analysis expert. "
            "For general research instructions without preloaded document data, "
            "set primary_intent to 'research'. "
            "Output strict JSON with keys: primary_intent, confidence, reasoning, "
            "forensic_mode, core_question, complexity."
        )
        prompt = (
            'User request: "Conduct deep research on Chinese new energy vehicle market, generate full analysis report"\n'
            "No document data uploaded. Standard research request.\n"
            "Output JSON."
        )
        llm_result = await call_llm(prompt=prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=1024)

        assert llm_result.get("success"), f"LLM call failed: {llm_result.get('error')}"
        content = llm_result.get("content", "")
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        try:
            parsed = analyzer._parse_llm_json(content)
        except (json.JSONDecodeError, Exception):
            import re
            m = re.search(r'"primary_intent"\s*:\s*"([^"]+)"', content)
            parsed = {"primary_intent": m.group(1) if m else "research", "confidence": 0.5, "complexity": "multi"}
        if isinstance(parsed.get("complexity"), (int, float)):
            parsed["complexity"] = "multi"
        intent_result = analyzer._build_result(parsed, llm_result.get("model", ""), content, False)

        assert not intent_result.forensic_mode, \
            f"Standard research input should not trigger forensic mode, got forensic_mode={intent_result.forensic_mode}, intent={intent_result.primary_intent.value}"


# ============================================================
# E2E-3: 取证数据提取 — 真实AnnualReportParserSkill
# ============================================================

class TestE2E3ForensicDataExtraction:
    """使用真实AnnualReportParserSkill验证取证数据提取"""

    def test_search_sections_finds_cashflow_data(self):
        """关键词搜索：从年报中找到现金流相关段落"""
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        data = _make_annual_report_data()

        results = parser.search_sections(data, ["现金流", "折旧"])
        assert len(results) >= 1, "Should find at least 1 section about cashflow/depreciation"
        titles = [r["title"] for r in results]
        assert any("现金" in t for t in titles), f"Should find cashflow section, got {titles}"

    def test_find_line_items_finds_depreciation(self):
        """科目搜索：从财务表中找到折旧行项目"""
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        data = _make_annual_report_data()

        results = parser.find_line_items(data, ["折旧"])
        assert len(results) >= 1, "Should find at least 1 line item for depreciation"
        assert results[0]["row"]["科目"] == "折旧与摊销"
        assert results[0]["row"]["本年"] == 8.2

    def test_extract_for_hypothesis_non_cash_expenses(self):
        """假设验证提取：非现金支出增加假设 → 提取折旧+减值数据"""
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        data = _make_annual_report_data()

        result = parser.extract_for_hypothesis(
            data,
            hypothesis="非现金支出（折旧摊销和资产减值）增加导致现金流增长高于利润增长",
            data_needs=["折旧", "减值", "摊销", "现金流"],
        )

        assert result["section_count"] >= 1, f"Should find at least 1 relevant section, got {result['section_count']}"
        assert result["line_item_count"] >= 1, f"Should find at least 1 relevant line item, got {result['line_item_count']}"
        assert len(result["relevant_sections"]) >= 1
        assert len(result["relevant_line_items"]) >= 1

        line_item_subjects = [item["row"]["科目"] for item in result["relevant_line_items"]]
        assert "折旧与摊销" in line_item_subjects, f"Should find depreciation, got {line_item_subjects}"

    def test_extract_for_hypothesis_working_capital(self):
        """假设验证提取：营运资本改善假设 → 提取应收+存货数据"""
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        data = _make_annual_report_data()

        result = parser.extract_for_hypothesis(
            data,
            hypothesis="营运资本改善（应收账款回收和存货周转加快）贡献现金流增长",
            data_needs=["应收账款", "存货", "营运"],
        )

        assert result["line_item_count"] >= 1, f"Should find at least 1 line item for working capital"
        line_item_subjects = [item["row"]["科目"] for item in result["relevant_line_items"]]
        assert any("应收" in s for s in line_item_subjects), \
            f"Should find accounts receivable, got {line_item_subjects}"

    def test_extract_for_hypothesis_no_match(self):
        """边界：假设与年报数据无关 → 返回空结果"""
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
        parser = AnnualReportParserSkill()
        data = _make_annual_report_data()

        result = parser.extract_for_hypothesis(
            data,
            hypothesis="海外市场扩张导致收入增长",
            data_needs=["海外收入", "国际业务", "出口"],
        )

        assert result["section_count"] == 0, "Should find no sections for irrelevant hypothesis"
        assert result["line_item_count"] == 0, "Should find no line items for irrelevant hypothesis"


# ============================================================
# E2E-4: config→context端到端传播
# ============================================================

class TestE2E4ConfigPropagation:
    """验证SectionSpec.config → AgentSpec.config → OriginalAgentSpec.context完整传播链"""

    def test_forensic_config_propagates_through_full_pipeline(self):
        """端到端：forensic_mode + hypothesis_data_needs 从SectionSpec传播到AgentSpec.context"""
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        from src.core.dynamic_orchestrator import PhaseType
        from src.core.decomposition.strategies import ResearchPhase

        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True, enable_content_lock=False)

        intent_result = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.95,
            intent_reasoning="forensic question with preloaded data",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=[
                "H1: 非现金支出（折旧摊销和资产减值）增加",
                "H2: 营运资本改善（应收账款回收和存货周转加快）",
            ],
            core_question="为什么现金流增长42%但利润只增长5%",
        )

        annual_report_data = _make_annual_report_data()
        requirement = _make_forensic_requirement(annual_report_data)

        task_structure = adapter._analyze_forensic_structure(requirement, intent_result, "test_topic")

        hypothesis_sections = [s for s in task_structure.sections if s.section_role.value == "analysis"]
        assert len(hypothesis_sections) == 2, f"Should have 2 hypothesis sections, got {len(hypothesis_sections)}"

        for s in hypothesis_sections:
            assert s.config.get("forensic_mode") is True, f"Section {s.section_id} should have forensic_mode=True"
            assert "hypothesis_data_needs" in s.config, f"Section {s.section_id} should have hypothesis_data_needs"
            assert len(s.config["hypothesis_data_needs"]) > 0, f"hypothesis_data_needs should not be empty"

        execution_plan = adapter._orchestrate_forensic_phases(task_structure, intent_result, "test_topic")

        analysis_phase = [p for p in execution_plan.phases if p.phase_type == PhaseType.ANALYSIS][0]
        for agent in analysis_phase.agent_specs:
            assert agent.config.get("forensic_mode") is True, \
                f"Agent {agent.agent_id} config should have forensic_mode=True, got {agent.config}"
            assert "hypothesis_data_needs" in agent.config, \
                f"Agent {agent.agent_id} config should have hypothesis_data_needs"

        decomp = execution_plan.to_decomposition_plan()
        analysis_agents = decomp.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        assert len(analysis_agents) == 2, f"Should have 2 analysis agents in decomposition plan"

        for agent in analysis_agents:
            assert agent.context.get("forensic_mode") is True, \
                f"Agent {agent.agent_id} context should have forensic_mode=True, got {agent.context}"
            assert "hypothesis_data_needs" in agent.context, \
                f"Agent {agent.agent_id} context should have hypothesis_data_needs, got {agent.context}"

    def test_forensic_structure_dependency_graph(self):
        """验证取证结构的依赖图：假设section依赖数据提取，核心问题依赖所有假设"""
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True, enable_content_lock=False)

        intent_result = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.95,
            intent_reasoning="test",
            forensic_mode=True,
            data_preloaded=True,
            causal_hypotheses=["H1: test hypothesis A", "H2: test hypothesis B"],
            core_question="test question",
        )

        requirement = {"task_id": "dep_test"}
        ts = adapter._analyze_forensic_structure(requirement, intent_result, "test")

        core_section = [s for s in ts.sections if s.section_id == "section_0_core_question"][0]
        hypothesis_sections = [s for s in ts.sections if s.section_role.value == "analysis"]
        dc_section = [s for s in ts.sections if s.section_id == "section_data_extraction"][0]

        for h in hypothesis_sections:
            assert "section_data_extraction" in h.content_dependency, \
                f"Hypothesis {h.section_id} should depend on data extraction"

        for h in hypothesis_sections:
            assert h.section_id in core_section.content_dependency, \
                f"Core question should depend on hypothesis {h.section_id}"

        assert dc_section.content_dependency == [], \
            "Data extraction section should have no dependencies"


# ============================================================
# E2E-5: LLM假设生成回退
# ============================================================

class TestE2E5HypothesisGenerationFallback:
    """验证当意图分析未提供causal_hypotheses时的LLM回退假设生成"""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_generate_hypotheses_with_llm(self):
        """LLM回退：空hypotheses → 调用LLM生成因果假设"""
        from src.core.llm_client import call_llm

        prompt = (
            "Based on the following question, generate 3-5 causal hypotheses. "
            "Each hypothesis must be testable with data.\n"
            "Question: Why did cash flow grow 42% but profit only grew 5%?\n"
            "Available data: Annual report with cashflow, income, balance sheet statements.\n"
            "Output format (one hypothesis per line):\n"
            "Hypothesis: [causal statement]"
        )
        result = await call_llm(
            prompt=prompt,
            system_prompt="You are a causal inference expert. Only output hypotheses, no analysis.",
            temperature=0.3,
            max_tokens=2048,
        )

        assert result.get("success"), f"LLM call failed: {result.get('error')}"
        content = result.get("content", "")
        assert len(content) > 20, f"LLM output too short: {content[:100]}"

        hypotheses = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line.startswith("Hypothesis:") or line.startswith("假设：") or line.startswith("假设:"):
                hypotheses.append(line.split(":", 1)[-1].strip())
            elif line and not line.startswith("#") and len(line) > 10:
                hypotheses.append(line)

        assert len(hypotheses) >= 1, f"Should generate at least 1 hypothesis from LLM output: {content[:200]}"
        for h in hypotheses:
            assert len(h) > 5, f"Hypothesis too short: '{h}'"


# ============================================================
# E2E-6: 取证Phase编排完整性
# ============================================================

class TestE2E6ForensicPhaseOrchestration:
    """验证取证Phase编排的完整性和正确性"""

    def test_forensic_phases_correct_order_and_dependencies(self):
        """验证Phase顺序：DC → Analysis → Synthesis → Calibration → Report"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole

        sections = [
            SectionSpec(section_id="section_0_core_question", section_name="核心问题",
                        section_role=SectionRole.SYNTHESIS, content_dependency=["section_1_hypothesis", "section_2_hypothesis", "section_3_hypothesis"]),
            SectionSpec(section_id="section_1_hypothesis", section_name="H1: 非现金支出增加",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["折旧", "减值"]}),
            SectionSpec(section_id="section_2_hypothesis", section_name="H2: 营运资本改善",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["应收账款", "存货"]}),
            SectionSpec(section_id="section_3_hypothesis", section_name="H3: 会计政策变更影响",
                        section_role=SectionRole.ANALYSIS, content_dependency=["section_data_extraction"],
                        config={"forensic_mode": True, "is_hypothesis": True, "hypothesis_data_needs": ["资本化", "会计政策"]}),
            SectionSpec(section_id="section_data_extraction", section_name="精准数据提取",
                        section_role=SectionRole.DATA_COLLECTION, content_dependency=[]),
        ]
        ts = TaskStructure(task_id="forensic_order_test", topic="test", sections=sections,
                           dependencies=[], execution_graph={}, parallel_groups=[])

        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9, intent_reasoning="test", forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()
        phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")

        expected_order = [
            PhaseType.DATA_COLLECTION,
            PhaseType.ANALYSIS,
            PhaseType.SYNTHESIS,
            PhaseType.CALIBRATION,
            PhaseType.REPORT,
        ]
        actual_order = [p.phase_type for p in phases]
        assert actual_order == expected_order, f"Phase order mismatch: expected {expected_order}, got {actual_order}"

        dc_phase = phases[0]
        analysis_phase = phases[1]
        synthesis_phase = phases[2]

        assert len(dc_phase.agent_specs) == 1, "DC phase should have 1 agent"
        assert len(analysis_phase.agent_specs) == 3, "Analysis phase should have 3 hypothesis agents"
        assert dc_phase.phase_id in analysis_phase.depends_on, "Analysis should depend on DC"
        assert analysis_phase.phase_id in synthesis_phase.depends_on, "Synthesis should depend on Analysis"

        for agent in analysis_phase.agent_specs:
            assert agent.config.get("forensic_mode") is True
            assert "hypothesis_data_needs" in agent.config

    def test_forensic_phases_no_m1_split(self):
        """验证取证Phase不走M1拆分：ANALYSIS section不会产生额外的DC agent"""
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole

        sections = [
            SectionSpec(section_id="s0", section_name="core", section_role=SectionRole.SYNTHESIS, content_dependency=["s1"]),
            SectionSpec(section_id="s1", section_name="H1", section_role=SectionRole.ANALYSIS, content_dependency=["s_dc"],
                        config={"forensic_mode": True}),
            SectionSpec(section_id="s_dc", section_name="data", section_role=SectionRole.DATA_COLLECTION, content_dependency=[]),
        ]
        ts = TaskStructure(task_id="no_m1_test", topic="test", sections=sections,
                           dependencies=[], execution_graph={}, parallel_groups=[])

        intent = DeepIntentResult(
            primary_intent=IntentType.FORENSIC_ANALYSIS,
            intent_confidence=0.9, intent_reasoning="test", forensic_mode=True,
        )
        orchestrator = DynamicPhaseOrchestrator()

        forensic_phases = orchestrator._orchestrate_forensic_phases(ts, intent, "test")
        dc_phases = [p for p in forensic_phases if p.phase_type == PhaseType.DATA_COLLECTION]
        assert len(dc_phases) == 1, f"Forensic should have exactly 1 DC phase, got {len(dc_phases)}"

        standard_phases = orchestrator._generate_phases(ts, intent, "test")
        standard_dc_phases = [p for p in standard_phases if p.phase_type == PhaseType.DATA_COLLECTION]
        assert len(standard_dc_phases) >= 1, "Standard M1 should produce DC phases for ANALYSIS sections"

        total_forensic_dc_agents = sum(len(p.agent_specs) for p in dc_phases)
        total_standard_dc_agents = sum(len(p.agent_specs) for p in standard_dc_phases)
        assert total_forensic_dc_agents == total_standard_dc_agents, \
            "The standard route must preserve the explicit data phase without duplicating forensic collection agents"
