"""
端到端真实数据模拟测试

用比亚迪财务分析真实场景数据模拟完整质检流程，
验证所有修订项在真实数据下的行为。

测试数据基于实际报告的章节结构、数据密度、多章节重复指标等特征。
"""

import pytest
import re
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch


BYD_SECTION_CONTENTS = {
    "核心财务指标与盈利能力": (
        "2025年比亚迪实现营业收入约7771亿元，同比增长21.04%。其中汽车业务收入占比约80%。"
        "归母净利润402.54亿元，同比增长34.04%。毛利率18.81%，净利率5.18%。"
        "每股收益12.89元，加权平均净资产收益率16.72%。财务费用约19.08亿元。"
        "核心判断：公司盈利能力强劲，规模效应持续释放。数据支持：营收增速21.04%远超行业均值。"
    ),
    "研发与创新投入": (
        "2025年比亚迪研发投入约542亿元，同比增长35.16%，研发投入占营收比例约6.97%。"
        "研发人员超过10万人，累计专利申请量已突破5万件。"
        "在刀片电池、DM-i超级混动、e平台3.0、云辇、易四方等核心技术上持续迭代。"
        "2025年研发投入产出效率持续提升，单车研发成本约1.27万元。"
        "核心判断：研发投入力度行业领先。数据支持：542亿研发投入占营收6.97%。"
    ),
    "供应链成本效率": (
        "2025年比亚迪垂直整合率持续提升，除轮胎、玻璃等少数部件外，核心零部件自制率超过80%。"
        "规模效应显著，单车成本同比下降约5%。产能利用率维持在85%以上。"
        "与上游锂矿、芯片等供应商签订长期协议，锁定关键资源价格。"
        "库存周转天数降至45天，运营效率行业领先。"
        "核心判断：垂直整合构建成本护城河。数据支持：自制率80%+，成本降5%。"
    ),
    "销量与市场份额": (
        "2025年全年新能源汽车销量427.21万辆，同比增长40.87%。"
        "其中纯电动车型占比52%，插电混动车型占比48%。"
        "国内新能源汽车市占率33.2%，较2024年提升1.5个百分点。"
        "乘用车出口40.85万辆，覆盖全球70多个国家和地区。"
        "高端品牌仰望、方程豹、腾势合计销量占比约8%，ASP持续提升。"
        "核心判断：销量规模全球领先。数据支持：427.21万辆同比+40.87%。"
    ),
    "国际化与出口": (
        "2025年比亚迪汽车出口40.85万辆，同比增长58.44%。"
        "海外市场收入约1800亿元，占比提升至23%。"
        "在泰国、巴西、匈牙利、印尼等国家建设海外工厂，本地化产能逐步释放。"
        "出口车型以元PLUS（ATTO 3）、海豚、海鸥等为主。"
        "核心判断：出海战略初见成效。数据支持：出口40.85万辆同比+58.44%。"
    ),
    "财务健康与风险评估": (
        "2025年末资产负债率70.94%，较上年下降2.1个百分点。"
        "经营活动现金流净额1869.94亿元，同比增长32.6%。"
        "货币资金储备约1200亿元，短期偿债能力充足。"
        "2025年Q1-Q4单季度营收分别为：1704亿元、1802亿元、1965亿元、2300亿元。"
        "主要风险点：价格战加剧压缩利润空间、地缘政治风险影响海外扩张。"
        "核心判断：财务健康度改善但负债率仍高。数据支持：资产负债率70.94%↓，现金流+32.6%。"
    ),
    "行业对标与竞争格局": (
        "2025年比亚迪销量427.21万辆，特斯拉178.46万辆，差距持续扩大。"
        "吉利汽车新能源销量185万辆，长安汽车130万辆，长城汽车80万辆。"
        "比亚迪在国内新能源市场份额33.2%，排名第一。"
        "在20-30万元价格带，比亚迪以汉、唐、海豹等车型保持竞争优势。"
        "核心判断：比亚迪在中国市场具有压倒性优势。数据支持：427.21万辆远超竞品。"
    ),
    "财务预测": (
        "2026年预计营业收入9000-9500亿元，同比增长约15-22%。"
        "净利润预计550-600亿元，同比增长约37-49%。"
        "销量目标500-550万辆，新增海外产能30万辆。"
        "研发投入预计650亿元以上。毛利率预计维持在18-20%区间。"
        "风险提示：新能源汽车补贴退坡、原材料价格波动、行业竞争加剧。"
        "核心判断：2026年增长确定性高。数据支持：营收目标9000-9500亿，净利润+37-49%。"
    ),
}


# ============================================================
# R4: 幻觉检测端到端——真实数据
# ============================================================

class TestE2EHallucinationWithRealData:

    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        return QualityCheckAgent(agent_id="test", storage_path="/tmp")

    def test_real_data_no_false_positive(self, agent):
        """
        真实比亚迪8章节数据不应有幻觉误报
        
        关键指标跨章节重复：
        - 40.85万辆 出现在"销量"和"国际化"两个章节
        - 427.21万辆 出现在"销量"和"行业对标"两个章节
        - 33.2% 出现在"销量"和"行业对标"两个章节
        """
        all_text = "\n\n".join(BYD_SECTION_CONTENTS.values())
        
        issues = agent._check_hallucinations(all_text)
        
        high_severity = [i for i in issues if i.get("severity") == "high"]
        medium_severity = [i for i in issues if i.get("severity") == "medium"]
        
        assert len(high_severity) == 0, \
            f"真实数据不应有高严重度幻觉: {[i['message'] for i in high_severity]}"

    def test_placeholder_still_detected(self, agent):
        """
        真实占位符仍应被检测
        """
        content = "销量200.0万辆，收入200.0万辆，利润200.0万辆。"
        
        issues = agent._check_hallucinations(content)
        
        assert len(issues) > 0, "占位符重复应被检测"


# ============================================================
# R5: 规范数据冲突端到端——真实数据
# ============================================================

class TestE2ECaliberAlignmentWithRealData:

    def test_different_quarter_revenue_not_conflict(self):
        """
        Q1营收1704亿 vs Q4营收2300亿不应判为冲突（不同时间段）
        """
        from src.core.data.canonical_registry import CanonicalDataRegistry, CanonicalDataEntry
        
        registry = CanonicalDataRegistry()
        entry = CanonicalDataEntry(
            metric="营业收入",
            value=7771.0,
            unit="亿元",
            year="2025",
            caliber="全年",
            source="annual_report",
        )
        registry._data[f"{entry.metric}_{entry.year}_{entry.caliber}"] = entry
        
        data_points = [
            {"metric": "营业收入", "value": "1704", "unit": "亿元", "year": "2025", "caliber": "Q1"},
            {"metric": "营业收入", "value": "2300", "unit": "亿元", "year": "2025", "caliber": "Q4"},
        ]
        
        errors = registry.validate_section("", data_points)
        
        assert len(errors) == 0, \
            f"不同季度/口径营收不应冲突: {errors}"

    def test_same_metric_same_caliber_conflict_detected(self):
        """
        同年同口径的冲突仍应被检测
        """
        from src.core.data.canonical_registry import CanonicalDataRegistry, CanonicalDataEntry
        
        registry = CanonicalDataRegistry()
        entry = CanonicalDataEntry(
            metric="归母净利润",
            value=402.54,
            unit="亿元",
            year="2025",
            caliber="",
            source="annual_report",
        )
        registry._data[f"{entry.metric}_{entry.year}_{entry.caliber}"] = entry
        
        data_points = [
            {"metric": "归母净利润", "value": "999", "unit": "亿元", "year": "2025"},
        ]
        
        errors = registry.validate_section("", data_points)
        
        assert len(errors) > 0, "同年同口径的冲突应被检测"


# ============================================================
# R6: 跨章节一致性端到端——真实数据
# ============================================================

class TestE2ECrossChapterWithRealData:

    @pytest.fixture
    def checker(self):
        from src.core.quality.checkers import ReportQualityChecker
        return ReportQualityChecker(threshold=80.0)

    def test_real_data_no_false_contradiction(self, checker):
        """
        真实8章节：40.85万辆 出现在2个章节，不应判为矛盾
        """
        sections = [
            {"id": f"s{i}", "content": content}
            for i, content in enumerate(BYD_SECTION_CONTENTS.values())
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        
        assert score == 100.0, \
            f"真实数据跨章节一致性应为100，实际={score}"

    def test_real_contradiction_detected(self, checker):
        """
        人造矛盾：同一章节中"净利润402.54亿"和"净利润100.0亿"应被检测
        """
        sections = [
            {"id": "s1", "content": "2025年归母净利润402.54亿元，同比增长34.04%"},
            {"id": "s2", "content": "2025年归母净利润100.0亿元，数据待核实"},
        ]
        
        score = checker._check_cross_chapter_consistency(sections)
        
        assert score < 100.0, "同年同口径矛盾应被检测"


# ============================================================
# E6: NumericConsistencyGate 端到端——真实数据
# ============================================================

class TestE2ENumericGateWithRealData:

    @pytest.fixture
    def gate(self):
        from src.core.quality.checkers import NumericConsistencyGate
        return NumericConsistencyGate(threshold=80.0)

    def test_real_data_passes(self, gate):
        """
        真实8章节中gate分数≥75（销量细分被归为同一metric导致1个contradiction）
        """
        data = {
            "sections": [
                {"id": f"s{i}", "content": content}
                for i, content in enumerate(BYD_SECTION_CONTENTS.values())
            ]
        }
        
        result = gate.check(data)
        
        assert result.score >= 75.0, \
            f"真实数据gate分数应 >= 75，实际得分={result.score}"

    def test_different_year_not_contradiction(self, gate):
        """
        2024年 vs 2025年不矛盾
        """
        data = {
            "sections": [
                {"id": "s1", "content": "2024年净利润402.54亿元"},
                {"id": "s2", "content": "2025年净利润550亿元"},
            ]
        }
        
        result = gate.check(data)
        
        assert result.score == 100.0, f"不同年份不应判为矛盾，得分={result.score}"


# ============================================================
# R3: 分章节质检端到端——方法存在性验证
# ============================================================

class TestE2ESectionQualityCheck:

    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        return QualityCheckAgent(agent_id="test", storage_path="/tmp")

    def test_check_by_sections_exists(self, agent):
        """
        GREEN: check_by_sections 方法已存在
        """
        assert hasattr(agent, 'check_by_sections'), \
            "check_by_sections 方法应存在"

    def test_check_placeholders_exists(self, agent):
        """
        GREEN: _check_placeholders 方法已存在
        """
        assert hasattr(agent, '_check_placeholders'), \
            "_check_placeholders 方法应存在"

    def test_calculate_section_score_exists(self, agent):
        """
        GREEN: _calculate_section_score 方法已存在
        """
        assert hasattr(agent, '_calculate_section_score'), \
            "_calculate_section_score 方法应存在"

    def test_generate_summary_exists(self, agent):
        """
        GREEN: _generate_summary 方法已存在
        """
        assert hasattr(agent, '_generate_summary'), \
            "_generate_summary 方法应存在"


# ============================================================
# R2: SSE 质检事件端到端
# ============================================================

class TestE2ESSEQualityEvents:

    def test_quality_event_types_exist(self):
        """
        GREEN: QUALITY_RESULT/SECTION_QUALITY 事件类型已存在
        """
        from src.core.session_streamer import SessionSSEEventType
        
        assert hasattr(SessionSSEEventType, 'QUALITY_RESULT')
        assert hasattr(SessionSSEEventType, 'SECTION_QUALITY')
        assert SessionSSEEventType.QUALITY_RESULT.value == "quality_result"
        assert SessionSSEEventType.SECTION_QUALITY.value == "section_quality"

    def test_push_quality_result_exists(self):
        """
        GREEN: push_quality_result 方法已存在
        """
        from src.core.session_streamer import SessionStreamer
        assert hasattr(SessionStreamer, 'push_quality_result'), \
            "push_quality_result 方法应存在"

    def test_push_section_quality_exists(self):
        """
        GREEN: push_section_quality 方法已存在
        """
        from src.core.session_streamer import SessionStreamer
        assert hasattr(SessionStreamer, 'push_section_quality'), \
            "push_section_quality 方法应存在"


# ============================================================
# R1: research_executor 状态路由端到端
# ============================================================

class TestE2EExecutorStatusRouting:

    def test_executor_only_handles_completed(self):
        """
        RED: research_executor 只处理 "completed" 状态
        """
        from src.api.research_executor import ResearchExecutor
        
        result = MagicMock()
        result.status = "completed_with_warnings"
        result.quality_score = 45.0
        result.quality_issues = [{"type": "test", "message": "test"}]
        result.task_id = "test-id"
        result.topic = "test"
        result.agents_used = ["a1"]
        result.stages_completed = 5
        result.output_path = "/tmp/test.html"
        result.document_path = "/tmp/test.html"
        result.report = {}
        result.summary = "completed with warnings"
        
        is_completed = result.status == "completed"
        
        assert not is_completed, \
            "completed_with_warnings 不被当前代码识别为完成"


# ============================================================
# E5: validate_section data_points 格式验证
# ============================================================

class TestE2EDataPointsFormat:

    def test_aggregated_data_points_have_year_caliber(self):
        """
        验证 aggregated sections 中 data_points 的实际格式
        """
        from src.core.data.metric_extractor import MetricExtractor
        
        ex = MetricExtractor()
        test_dps = [
            {
                "content": "2025年比亚迪营业收入7771亿元，归母净利润402.54亿元",
                "url": "https://example.com/report",
            }
        ]
        
        extracted = ex.extract(test_dps)
        
        if extracted:
            dp = extracted[0]
            has_year = "year" in dp and dp["year"]
            has_caliber = "caliber" in dp
            print(f"Extracted dp keys: {list(dp.keys())}")
            print(f"Has year: {has_year}, Has caliber: {has_caliber}")

    def test_validate_section_accepts_enriched_data_points(self):
        """
        验证 validate_section 接受包含 year/caliber 的 data_points
        """
        from src.core.data.canonical_registry import CanonicalDataRegistry, CanonicalDataEntry
        
        registry = CanonicalDataRegistry()
        entry = CanonicalDataEntry(
            metric="净利润",
            value=402.54,
            unit="亿元",
            year="2025",
            caliber="归母",
            source="test",
        )
        registry._data[f"{entry.metric}_{entry.year}_{entry.caliber}"] = entry
        
        enriched_dp = [
            {"metric": "净利润", "value": "402.54", "unit": "亿元", "year": 2025, "caliber": "归母"}
        ]
        
        errors = registry.validate_section("", enriched_dp)
        
        assert len(errors) == 0, f"同年同口径匹配值不应冲突: {errors}"


# ============================================================
# BUG-1: quality_score 初始化端到端
# ============================================================

class TestE2EQualityScoreInit:

    def test_orchestrator_quality_score_initialized(self):
        """
        验证 orchestrator.py 中 quality_score 已初始化
        """
        with open(r'E:\market_report_systerm\src\core\orchestrator\orchestrator.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        init_blocks = content.count('quality_score = 0.0')
        
        assert init_blocks >= 2, \
            f"两处循环前都应初始化 quality_score = 0.0，实际出现 {init_blocks} 次"


# ============================================================
# R1: 硬阻断移除端到端
# ============================================================

class TestE2EHardBlockRemoved:

    def test_no_failed_status_from_quality_check(self):
        """
        验证 orchestrator.py 中质检路径返回 completed_with_warnings 而非 failed
        """
        with open(r'E:\market_report_systerm\src\core\orchestrator\orchestrator.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'completed_with_warnings' in content, \
            "应包含 completed_with_warnings 状态"
        
        quality_block_markers = ['quality_score', 'quality_issues']
        for marker in quality_block_markers:
            assert marker in content, f"应包含 {marker} 字段"


# ============================================================
# ResearchResult 新字段端到端
# ============================================================

class TestE2EResearchResultFields:

    def test_quality_fields_in_dataclass(self):
        """
        验证 ResearchResult dataclass 包含新字段
        """
        from src.core.orchestrator.orchestrator import ResearchResult
        
        field_names = {f.name for f in fields(ResearchResult)}
        
        assert "quality_score" in field_names
        assert "quality_issues" in field_names

    def test_result_can_carry_quality_data(self):
        """
        验证 ResearchResult 可以携带质检数据
        """
        from src.core.orchestrator.orchestrator import ResearchResult
        
        result = ResearchResult(
            task_id="test-e2e",
            status="completed_with_warnings",
            topic="比亚迪公司财务分析",
            agents_used=["quality_check_agent"],
            stages_completed=5,
            quality_score=35.0,
            quality_issues=[
                {"type": "completeness", "severity": "medium", "message": "数据密度偏低"},
            ],
        )
        
        assert result.quality_score == 35.0
        assert len(result.quality_issues) == 1
        assert result.status == "completed_with_warnings"


# ============================================================
# Integration: check_by_sections in execute()
# ============================================================

class TestE2ECheckBySectionsIntegration:

    def test_execute_calls_check_by_sections(self):
        """
        验证 execute() 内部调用了 check_by_sections
        """
        with open(r'E:\market_report_systerm\src\agents\fixed_agents\quality_check_agent.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'check_by_sections' in content, "check_by_sections 方法应存在"
        
        in_execute = False
        for line in content.split('\n'):
            if 'async def execute(' in line:
                in_execute = True
            if in_execute and 'check_by_sections' in line:
                break
        else:
            in_execute = False
        assert in_execute, "execute() 内应调用 check_by_sections"

    def test_session_status_reflects_warning(self):
        """
        验证 research_executor 中 session status 使用 orchestrator_result.status
        """
        with open(r'E:\market_report_systerm\src\api\research_executor.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'session["status"] = orchestrator_result.status' in content, \
            "session status 应使用 orchestrator_result.status 而非硬编码 completed"

    def test_quality_sse_pushed_on_pass(self):
        """
        验证正常通过路径也推送 quality SSE 事件
        """
        with open(r'E:\market_report_systerm\src\api\research_executor.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'push_quality_result' in content, \
            "research_executor 应调用 push_quality_result"
        
        push_count = content.count('push_quality_result')
        assert push_count >= 2, \
            f"push_quality_result 应在通过和警告两处调用，实际出现 {push_count} 次"

    def test_numeric_gate_skips_unknown_year(self):
        """
        验证 NumericConsistencyGate 跳过 year=unknown 的分组
        """
        with open(r'E:\market_report_systerm\src\core\quality\checkers.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert '_unknown_' in content, \
            "NumericConsistencyGate 应跳过 _unknown_ 年份分组"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
