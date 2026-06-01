"""
QC 数据接口修复验证测试

验证 engine.py 中 batch_results → check_data 转换与三个 checker 的数据契约匹配。

检查器预期数据格式：
  - AnalysisQualityChecker:   data["content"] (str), data["sources"] (list)
  - DataCollectionQualityChecker: data["quality_metadata"] (dict)
  - ReportQualityChecker:     data["content"]/data["sections"], data["sources"]

转换逻辑（engine.py:1190-1216）：
  1. 从 batch_results 聚合 content、sources、data_points
  2. 构建 quality_metadata（data_volume/sources/quality_score）
  3. 将聚合结构传给 checker.check()
"""

import pytest
from typing import Dict, List, Any


# ============================================================
# 生产代码级别的数据转换（镜像 engine.py:1190-1216）
# ============================================================

def build_check_data(batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """精确复制 engine.py:1190-1216 的数据转换逻辑"""
    combined_content = "\n\n".join([
        r.get("content", "") or r.get("result", "")
        for r in batch_results if r.get("success")
    ])
    all_sources = []
    all_data_points = []
    for r in batch_results:
        if r.get("success"):
            all_sources.extend(r.get("sources", []))
            all_data_points.extend(r.get("data_points", []))
    check_data = {
        "content": combined_content,
        "sources": all_sources,
        "data_points": all_data_points,
        "quality_metadata": {
            "data_volume": len(all_data_points) or len(all_sources),
            "sources": all_sources,
            "quality_score": 50.0,
        },
    }
    return check_data


# ============================================================
# 测试夹具：模拟 Agent 结果
# ============================================================

@pytest.fixture
def sample_agent_result():
    """单个标准的成功 Agent 结果"""
    return {
        "agent_id": "research_market_size_3",
        "success": True,
        "content": "2026年中国新能源汽车市场规模达到1.2万亿元，同比增长25%。",
        "result": "",
        "sources": [
            "https://www.gov.cn/statistics/2026",
            "https://www.caixin.com/auto/2026",
        ],
        "data_points": [
            {"indicator": "market_size", "value": "1.2万亿", "year": 2026},
            {"indicator": "yoy_growth", "value": "25%", "year": 2026},
        ],
    }


@pytest.fixture
def sample_agent_result_competitive():
    """第二个成功 Agent 结果"""
    return {
        "agent_id": "research_competitive_4",
        "success": True,
        "content": "比亚迪、特斯拉和蔚来占据市场前三。比亚迪市占率35%，同比增长8个百分点。",
        "result": "",
        "sources": ["https://www.reuters.com/china-ev-2026"],
        "data_points": [
            {"indicator": "market_share_byd", "value": "35%", "year": 2026},
        ],
    }


@pytest.fixture
def sample_agent_failed():
    """失败的 Agent 结果"""
    return {
        "agent_id": "research_risk_11",
        "success": False,
        "error": "API timeout",
        "content": "",
        "sources": [],
        "data_points": [],
    }


@pytest.fixture
def batch_results_all_success(sample_agent_result, sample_agent_result_competitive):
    """全成功的批次"""
    return [sample_agent_result, sample_agent_result_competitive]


@pytest.fixture
def batch_results_with_failure(sample_agent_result, sample_agent_result_competitive,
                                sample_agent_failed):
    """含失败的批次"""
    return [sample_agent_result, sample_agent_failed, sample_agent_result_competitive]


@pytest.fixture
def batch_results_data_collection():
    """数据收集阶段的结果（有 data_points/sources，无 content）"""
    return [
        {
            "agent_id": "collector_1",
            "success": True,
            "content": "",
            "result": "",
            "sources": ["https://www.gov.cn/data"],
            "data_points": [{"key": "val1"}, {"key": "val2"}, {"key": "val3"}],
        },
        {
            "agent_id": "collector_2",
            "success": True,
            "content": "",
            "result": "",
            "sources": ["https://bloomberg.com/markets"],
            "data_points": [{"key": "val4"}, {"key": "val5"}],
        },
    ]


@pytest.fixture
def batch_results_mixed_content_result():
    """混合使用 content 和 result 字段的 Agent"""
    return [
        {
            "agent_id": "agent_a",
            "success": True,
            "content": "这是 content 字段的内容",
            "result": "",
            "sources": [],
            "data_points": [],
        },
        {
            "agent_id": "agent_b",
            "success": True,
            "content": "",
            "result": "这是 result 字段的内容",
            "sources": [],
            "data_points": [],
        },
    ]


@pytest.fixture
def batch_results_minimal():
    """最小有效结果"""
    return [
        {"agent_id": "minimal_1", "success": True, "content": "简短内容",
         "sources": [], "data_points": []},
    ]


@pytest.fixture
def rich_analysis_batch():
    """富含分析内容、结论和数据引用，足以通过阈值 70 的批次"""
    content = (
        "2026年中国新能源汽车市场规模达到1.2万亿元，同比增长25%。"
        "根据工信部最新数据显示，该市场连续五年保持双位数增长，渗透率突破40%。\n\n"
        "根本驱动因素分析：第一，技术降本效应显著，电池成本较2020年下降40%。"
        "第二，政策支持持续加码，购置税减免和充电基建补贴刺激需求。"
        "第三，消费认知加速转变，消费者接受度从2020年的20%提升至2026年的65%。\n\n"
        "影响机制方面，供给端和需求端的良性循环正在形成。"
        "根本原因在于技术创新和规模效应共同推动成本下降。"
        "综上所述，行业处于快速增长期，预计2027年市场规模将达1.8万亿元。"
    )
    return [{
        "agent_id": "research_analysis_main",
        "success": True,
        "content": content,
        "result": "",
        "sources": [
            "https://www.gov.cn/statistics/2026",
            "https://www.caixin.com/auto/2026",
            "https://www.reuters.com/china-ev-2026",
            "https://report.miit.gov.cn/industry2026",
        ],
        "data_points": [
            {"indicator": "market_size", "value": "1.2万亿", "year": 2026},
            {"indicator": "yoy_growth", "value": "25%", "year": 2026},
            {"indicator": "penetration_rate", "value": "40%", "year": 2026},
        ],
    }]


# ============================================================
# 转换逻辑测试
# ============================================================

class TestBuildCheckData:
    """测试 build_check_data 转换逻辑"""

    def test_content_aggregation(self, batch_results_all_success):
        """验证 content 拼接正确"""
        data = build_check_data(batch_results_all_success)
        assert "content" in data
        assert "1.2万亿元" in data["content"]
        assert "比亚迪" in data["content"]
        assert "\n\n" in data["content"]

    def test_content_excludes_failed(self, batch_results_with_failure):
        """失败 Agent 的 content 不应出现在聚合中"""
        data = build_check_data(batch_results_with_failure)
        assert data["content"].count("\n\n") == 1  # 2 个成功结果之间 1 个分隔符

    def test_sources_aggregation(self, batch_results_all_success):
        """验证 sources 合并"""
        data = build_check_data(batch_results_all_success)
        assert "sources" in data
        assert len(data["sources"]) == 3
        assert "gov.cn" in data["sources"][0]

    def test_sources_skips_failed(self, batch_results_with_failure):
        """失败 Agent 的 sources 不应出现"""
        data = build_check_data(batch_results_with_failure)
        assert len(data["sources"]) == 3

    def test_data_points_aggregation(self, batch_results_all_success):
        """验证 data_points 合并"""
        data = build_check_data(batch_results_all_success)
        assert "data_points" in data
        assert len(data["data_points"]) == 3

    def test_quality_metadata_structure(self, batch_results_all_success):
        """验证 quality_metadata 结构完整"""
        data = build_check_data(batch_results_all_success)
        assert "quality_metadata" in data
        qm = data["quality_metadata"]
        assert "data_volume" in qm
        assert "sources" in qm
        assert "quality_score" in qm
        assert qm["quality_score"] == 50.0

    def test_quality_metadata_data_volume(self, batch_results_all_success,
                                           batch_results_data_collection):
        """验证 data_volume 计算正确"""
        data = build_check_data(batch_results_all_success)
        assert data["quality_metadata"]["data_volume"] == 3  # 3 data_points

        data_dc = build_check_data(batch_results_data_collection)
        assert data_dc["quality_metadata"]["data_volume"] == 5  # 5 data_points

    def test_empty_batch(self):
        """空批次"""
        data = build_check_data([])
        assert data["content"] == ""
        assert data["sources"] == []
        assert data["data_points"] == []
        assert data["quality_metadata"]["data_volume"] == 0

    def test_all_failed(self, sample_agent_failed):
        """全部失败"""
        data = build_check_data([sample_agent_failed, sample_agent_failed])
        assert data["content"] == ""
        assert data["sources"] == []
        assert data["data_points"] == []

    def test_content_result_fallback(self, batch_results_mixed_content_result):
        """验证 content 为空时回退到 result 字段"""
        data = build_check_data(batch_results_mixed_content_result)
        assert "content 字段" in data["content"]
        assert "result 字段" in data["content"]

    def test_minimal_result(self, batch_results_minimal):
        """最小有效结果"""
        data = build_check_data(batch_results_minimal)
        assert data["content"] == "简短内容"
        assert data["sources"] == []
        assert data["data_points"] == []

    def test_no_side_effects(self, batch_results_all_success):
        """验证 build_check_data 不修改原始 batch_results"""
        original = [dict(r) for r in batch_results_all_success]
        build_check_data(batch_results_all_success)
        assert batch_results_all_success == original

    def test_data_volume_fallback_to_sources(self):
        """无 data_points 时 data_volume 回退到 sources 数量"""
        batch = [{
            "agent_id": "t", "success": True,
            "content": "", "result": "",
            "sources": ["a.com", "b.com", "c.com"],
            "data_points": [],
        }]
        data = build_check_data(batch)
        assert data["quality_metadata"]["data_volume"] == 3


# ============================================================
# Checker 契约测试
# ============================================================

class TestAnalysisCheckerContract:
    """AnalysisQualityChecker 能否消费转换后的数据"""

    @pytest.fixture
    def checker(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        return AnalysisQualityChecker(threshold=70.0)

    def test_checker_receives_content_and_passes(self, checker, rich_analysis_batch):
        """验证 AnalysisQualityChecker 读取聚合 content 并正确评分通过"""
        data = build_check_data(rich_analysis_batch)
        result = checker.check(data, {})
        assert result.score >= 70.0, (
            f"Rich content should pass threshold 70, got score={result.score:.1f}"
        )
        assert result.passed is True

    def test_checker_empty_content_fails(self, checker):
        """空内容得 0 分"""
        data = build_check_data([])
        result = checker.check(data, {})
        assert result.score == 0.0
        assert result.passed is False

    def test_checker_ignores_extra_fields(self, checker, batch_results_all_success):
        """额外的 sources/data_points/quality_metadata 不应干扰 analysis 评分"""
        data = build_check_data(batch_results_all_success)
        result = checker.check(data, {})
        assert hasattr(result, "score")
        assert hasattr(result, "passed")
        assert hasattr(result, "issues")

    def test_checker_long_content_scores_high(self, checker):
        """长内容应获得较高分数"""
        long_content = "市场分析。" * 500
        batch_results = [{
            "agent_id": "test", "success": True,
            "content": long_content, "result": "",
            "sources": [], "data_points": [],
        }]
        data = build_check_data(batch_results)
        result = checker.check(data, {})
        assert result.score >= 50, f"Long content should score >= 50, got {result.score}"

    def test_checker_with_data_references_scores_higher(self, checker):
        """含数据引用的内容得分高于无引用内容"""
        with_data = "同比增长25%，市场规模达到100亿元，medium content here% and million"
        without_data = "市场表现良好，前景广阔，分析认为未来发展可期"

        r1 = checker.check(build_check_data([
            {"agent_id": "a", "success": True, "content": with_data,
             "result": "", "sources": [], "data_points": []}
        ]), {})
        r2 = checker.check(build_check_data([
            {"agent_id": "b", "success": True, "content": without_data,
             "result": "", "sources": [], "data_points": []}
        ]), {})
        assert r1.score > r2.score, (
            f"Data refs ({r1.score}) should score > no refs ({r2.score})"
        )


class TestDataCollectionCheckerContract:
    """DataCollectionQualityChecker 能否消费转换后的数据"""

    @pytest.fixture
    def checker(self):
        from src.core.quality.checkers import DataCollectionQualityChecker
        return DataCollectionQualityChecker(threshold=70.0)

    def test_with_quality_metadata_scores_properly(self, checker,
                                                     batch_results_data_collection):
        """inline quality_metadata 能正确计算分数"""
        data = build_check_data(batch_results_data_collection)
        # volume=5 → 20, quality=50 → 50, sources with "gov.cn" → authoritative 1/2
        # source_score = 80*0.5 + 30*0.5 = 55
        # final = 20*0.3 + 50*0.4 + 55*0.3 = 6 + 20 + 16.5 = 42.5
        result = checker.check(data, {})
        assert result.score == 42.5, f"Expected 42.5, got {result.score}"
        assert result.passed is False

    def test_high_volume_passes(self, checker):
        """大量数据点应能通过阈值"""
        batch = [{
            "agent_id": "big_collector", "success": True,
            "content": "", "result": "",
            "sources": ["https://www.gov.cn/official"],
            "data_points": [{"i": n} for n in range(100)],
        }]
        data = build_check_data(batch)
        # volume=100 → 100, quality=50, source: authoritative → 80
        # final = 100*0.3 + 50*0.4 + 80*0.3 = 30 + 20 + 24 = 74
        result = checker.check(data, {})
        assert result.passed is True, f"Expected passed, got score={result.score}"

    def test_data_volume_scoring(self, checker):
        """数据量评分分段正确"""
        volumes_and_scores = [
            (0, 10.0), (3, 10.0), (5, 20.0), (10, 40.0),
            (20, 60.0), (50, 80.0), (100, 100.0), (200, 100.0),
        ]
        for volume, expected_score in volumes_and_scores:
            actual = checker._calculate_volume_score({"data_volume": volume})
            assert actual == expected_score, (
                f"volume={volume}: expected {expected_score}, got {actual}"
            )

    def test_no_data_points_fallback(self, checker):
        """无 data_points 时使用 sources 数量"""
        batch = [{
            "agent_id": "collector", "success": True,
            "content": "", "result": "",
            "sources": ["url1", "url2", "url3", "url4", "url5"],
            "data_points": [],
        }]
        data = build_check_data(batch)
        result = checker.check(data, {})
        # volume=5 → 20, quality=50, source: all non-authoritative → 30
        # final = 20*0.3 + 50*0.4 + 30*0.3 = 6 + 20 + 9 = 35
        assert result.score == 35.0


class TestReportCheckerContract:
    """ReportQualityChecker 能否消费转换后的数据"""

    @pytest.fixture
    def checker(self):
        from src.core.quality.checkers import ReportQualityChecker
        return ReportQualityChecker(threshold=80.0)

    def test_with_content_returns_score(self, checker, batch_results_all_success):
        """ReportQualityChecker 通过 content 回退读取聚合内容"""
        data = build_check_data(batch_results_all_success)
        result = checker.check(data, {})
        assert result.score > 0

    def test_sources_passed_to_checker(self, checker, batch_results_all_success):
        """验证 sources 已传递给 ReportQualityChecker"""
        data = build_check_data(batch_results_all_success)
        details = checker._get_details(data, {})
        assert details["sources_count"] == 3

    def test_empty_report_fails(self, checker):
        """空内容评分低于阈值"""
        data = build_check_data([])
        result = checker.check(data, {})
        assert result.score < 80.0
        assert result.passed is False


# ============================================================
# 端到端回归测试（模拟完整 engine.py 链路）
# ============================================================

class TestFullPipelineContract:
    """完整链路的回归测试"""

    @pytest.fixture
    def engine(self):
        """创建 ExecutionEngine 实例（mock 依赖）"""
        from unittest.mock import MagicMock
        from src.core.orchestrator.execution.engine import ExecutionEngine
        from src.core.orchestrator.execution.engine import ExecutionConfig
        mock_bus = MagicMock()
        mock_memory = MagicMock()
        return ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=mock_bus,
            shared_memory=mock_memory,
            enable_quality_control=True,
        )

    def test_select_checker_routes_correctly(self, engine):
        """验证 _select_checker_for_batch 路由正确"""
        dc_results = [
            {"success": True, "data_points": [{"k": "v"}],
             "sources": ["url"], "content": "", "result": ""},
        ]
        assert engine._select_checker_for_batch(dc_results) == engine.data_checker

        analysis_results = [
            {"success": True, "content": "分析内容", "result": "",
             "sources": [], "data_points": []},
        ]
        assert engine._select_checker_for_batch(analysis_results) == engine.analysis_checker

        mixed_results = [
            {"success": True, "content": "分析内容", "result": "",
             "sources": ["url"], "data_points": [{"k": "v"}]},
        ]
        assert engine._select_checker_for_batch(mixed_results) == engine.analysis_checker

    def test_engine_initializes_all_checkers(self, engine):
        """验证 engine 初始化了所有 checker"""
        assert engine.data_checker is not None
        assert engine.analysis_checker is not None
        assert engine.report_checker is not None
        assert engine.metadata_extractor is not None

    def test_engine_with_disabled_qc(self):
        """禁用 QC 时 checker 应为 None"""
        from unittest.mock import MagicMock
        from src.core.orchestrator.execution.engine import ExecutionEngine
        from src.core.orchestrator.execution.engine import ExecutionConfig
        mock_bus = MagicMock()
        mock_memory = MagicMock()
        engine = ExecutionEngine(
            config=ExecutionConfig(), message_bus=mock_bus,
            shared_memory=mock_memory, enable_quality_control=False,
        )
        assert engine.data_checker is None
        assert engine.analysis_checker is None


# ============================================================
# 边界条件测试
# ============================================================

class TestEdgeCases:
    """边界条件"""

    def test_very_large_content(self):
        """超大内容不应出错"""
        large_content = "测试内容。" * 10000
        batch_results = [{
            "agent_id": "big", "success": True,
            "content": large_content, "result": "",
            "sources": ["url"] * 1000,
            "data_points": [{"i": n} for n in range(500)],
        }]
        data = build_check_data(batch_results)
        assert len(data["content"]) > 30000
        assert len(data["sources"]) == 1000
        assert len(data["data_points"]) == 500

    def test_unicode_content(self):
        """Unicode 内容（中文特殊字符）"""
        batch_results = [{
            "agent_id": "unicode", "success": True,
            "content": "测试①：同比增长②③④⑤%△▲※→←",
            "result": "",
            "sources": [], "data_points": [],
        }]
        data = build_check_data(batch_results)
        assert data["content"] == "测试①：同比增长②③④⑤%△▲※→←"

    def test_extra_fields_ignored(self):
        """Agent 结果包含额外字段不应影响"""
        batch_results = [{
            "agent_id": "extra", "success": True,
            "content": "内容", "result": "",
            "sources": [], "data_points": [],
            "extra_field_1": "不应干扰",
            "extra_field_2": {"nested": "data"},
        }]
        data = build_check_data(batch_results)
        assert data["content"] == "内容"
        assert data["sources"] == []
        assert data["data_points"] == []

    def test_none_content_handling(self):
        """content 为 None 时回退到 result"""
        batch_results = [{
            "agent_id": "none_test", "success": True,
            "content": None, "result": "回退内容",
            "sources": [], "data_points": [],
        }]
        data = build_check_data(batch_results)
        assert data["content"] == "回退内容"

    def test_success_field_missing(self):
        """缺少 success 字段的项应排除"""
        batch_results = [
            {"agent_id": "a", "content": "不应出现", "sources": [], "data_points": []},
            {"agent_id": "b", "success": True, "content": "应出现",
             "sources": [], "data_points": []},
        ]
        data = build_check_data(batch_results)
        assert "不应出现" not in data["content"]
        assert "应出现" in data["content"]
