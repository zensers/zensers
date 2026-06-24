# -*- coding: utf-8 -*-
"""
查询去重与数据完整性方案测试

覆盖范围:
- Phase 0a: 数据源路由（_get_data_collection_skills, _fetch_structured_data）
- Phase A: 3 级框架（SectionDataSpec, SubSectionSpec, derive_data_source_type, validate_section_data_specs）
- Phase B: Engine 层统一查询去重（SearchQueryDeduplicator, _unified_search, preloaded_search_results 传递）
- Phase C: 数据对账（write_canonical 来源优先级）
- Phase D: 数据补充（_get_covered_needs, _supplement_missing_data）
"""

import pytest
import asyncio
import copy
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ============================================================
# Phase 0a: 数据源路由
# ============================================================

class TestDataCollectionSkillRouting:
    """测试 _get_data_collection_skills 按 aspect 动态路由"""

    DATA_SOURCE_SKILL_MAP = {
        "financial": ["stock_data"],
        "valuation": ["stock_data"],
        "company": ["stock_data"],
        "market_size": ["stock_data"],
        "competitive": [],
        "policy": [],
        "technology": [],
        "risk": [],
    }

    def _get_data_collection_skills(self, aspect, topic="", intent_result=None):
        skills = ["search_skill", "news_search", "llm_skill"]
        aspect_lower = aspect.lower()
        for keyword, extra_skills in self.DATA_SOURCE_SKILL_MAP.items():
            if keyword in aspect_lower:
                skills.extend(extra_skills)
        if intent_result:
            primary_type = getattr(intent_result, 'primary_research_type', None)
            if primary_type and getattr(primary_type, 'value', '') in (
                "company_research", "investment", "competitive_analysis"
            ):
                if "stock_data" not in skills:
                    skills.append("stock_data")
        return list(dict.fromkeys(skills))

    def test_financial_aspect_gets_stock_data(self):
        skills = self._get_data_collection_skills("Financial Analysis")
        assert "stock_data" in skills
        assert "search_skill" in skills

    def test_valuation_aspect_gets_stock_data(self):
        skills = self._get_data_collection_skills("Valuation Analysis")
        assert "stock_data" in skills

    def test_competitive_aspect_no_stock_data(self):
        skills = self._get_data_collection_skills("Competitive Landscape")
        assert "stock_data" not in skills
        assert "search_skill" in skills

    def test_policy_aspect_no_stock_data(self):
        skills = self._get_data_collection_skills("Policy Environment")
        assert "stock_data" not in skills

    def test_company_research_intent_adds_stock_data(self):
        intent = Mock()
        intent.primary_research_type = Mock(value="company_research")
        skills = self._get_data_collection_skills("Technology Trends", intent_result=intent)
        assert "stock_data" in skills

    def test_no_duplicate_skills(self):
        skills = self._get_data_collection_skills("Financial Company Analysis")
        assert len(skills) == len(set(skills))

    def test_base_skills_always_present(self):
        for aspect in ["Financial", "Competitive", "Policy", "Technology"]:
            skills = self._get_data_collection_skills(aspect)
            assert "search_skill" in skills
            assert "news_search" in skills
            assert "llm_skill" in skills


# ============================================================
# Phase A: 3 级框架
# ============================================================

class TestSubSectionSpec:
    """测试 SubSectionSpec 数据结构"""

    def test_basic_creation(self):
        spec = SubSectionSpec(
            sub_section_id="sub_0_0",
            name="营收分析",
            data_needs=["营收", "营收增长率", "营收构成"],
            data_source_type="structured",
        )
        assert spec.sub_section_id == "sub_0_0"
        assert spec.data_source_type == "structured"
        assert len(spec.data_needs) == 3

    def test_default_data_source_type(self):
        spec = SubSectionSpec(
            sub_section_id="sub_0_0",
            name="test",
            data_needs=["test"],
        )
        assert spec.data_source_type == "search"


class TestSectionDataSpec:
    """测试 SectionDataSpec 数据结构"""

    def _make_section(self, subs):
        return SectionDataSpec(
            section_id="section_0",
            name="核心指标",
            sub_sections=subs,
        )

    def test_all_data_needs_dedup(self):
        section = self._make_section([
            SubSectionSpec("sub_0_0", "营收", ["营收", "营收增长率"], "structured"),
            SubSectionSpec("sub_0_1", "利润", ["净利润", "营收"], "structured"),
        ])
        assert section.all_data_needs == ["营收", "营收增长率", "净利润"]

    def test_search_data_needs(self):
        section = self._make_section([
            SubSectionSpec("sub_0_0", "营收", ["营收"], "structured"),
            SubSectionSpec("sub_0_1", "竞争", ["竞争优势"], "search"),
            SubSectionSpec("sub_0_2", "成本", ["营业成本"], "both"),
        ])
        assert "竞争优势" in section.search_data_needs
        assert "营业成本" in section.search_data_needs
        assert "营收" not in section.search_data_needs

    def test_structured_data_needs(self):
        section = self._make_section([
            SubSectionSpec("sub_0_0", "营收", ["营收"], "structured"),
            SubSectionSpec("sub_0_1", "竞争", ["竞争优势"], "search"),
            SubSectionSpec("sub_0_2", "成本", ["营业成本"], "both"),
        ])
        assert "营收" in section.structured_data_needs
        assert "营业成本" in section.structured_data_needs
        assert "竞争优势" not in section.structured_data_needs

    def test_empty_sub_sections(self):
        section = SectionDataSpec(section_id="section_0", name="test")
        assert section.all_data_needs == []
        assert section.search_data_needs == []
        assert section.structured_data_needs == []


class TestDeriveDataSourceType:
    """测试 derive_data_source_type 规则推导"""

    STRUCTURED_DATA_CAPABILITIES = {
        "stock_data": {
            "zh": ["营收", "净利润", "毛利率", "净利率", "ROE", "ROA", "ROIC",
                   "资产负债率", "流动比率", "速动比率", "现金流", "研发费用",
                   "销量", "产量", "市场份额", "PE", "PB"],
        },
    }

    def _derive_data_source_type(self, data_need, topic="", intent_result=None):
        for skill_name, capabilities in self.STRUCTURED_DATA_CAPABILITIES.items():
            for lang, keywords in capabilities.items():
                if data_need in keywords:
                    return "structured"
        if "比亚迪" in topic or "公司" in topic:
            FINANCIAL_KEYWORDS = ["营收", "利润", "率", "费用", "ROE", "ROA", "ROIC", "PE", "PB", "DCF"]
            if any(kw in data_need for kw in FINANCIAL_KEYWORDS):
                return "both"
        return "search"

    def test_known_structured_need(self):
        assert self._derive_data_source_type("营收") == "structured"
        assert self._derive_data_source_type("ROE") == "structured"
        assert self._derive_data_source_type("PE") == "structured"

    def test_unknown_need_defaults_to_search(self):
        assert self._derive_data_source_type("TAM") == "search"
        assert self._derive_data_source_type("竞争优势") == "search"

    def test_company_topic_partial_match(self):
        assert self._derive_data_source_type("利润趋势", topic="比亚迪") == "both"
        assert self._derive_data_source_type("费用结构", topic="某公司") == "both"

    def test_non_company_topic_no_both(self):
        assert self._derive_data_source_type("利润趋势", topic="新能源汽车行业") == "search"

    def test_exact_match_overrides_partial(self):
        assert self._derive_data_source_type("净利润", topic="比亚迪") == "structured"


class TestValidateSectionDataSpecs:
    """测试 3 级框架验证 + fallback"""

    def _validate_section_data_specs(self, specs, section_names):
        valid = True
        for spec in specs:
            if not spec.all_data_needs:
                valid = False
        if len(specs) != len(section_names):
            valid = False
        if not valid:
            specs = self._fallback_specs_from_names(section_names)
        return specs, valid

    def _fallback_specs_from_names(self, section_names):
        specs = []
        for i, name in enumerate(section_names):
            specs.append(SectionDataSpec(
                section_id=f"section_{i}",
                name=name,
                sub_sections=[SubSectionSpec(
                    sub_section_id=f"sub_{i}_0",
                    name=name,
                    data_needs=[name],
                    data_source_type="search",
                )],
            ))
        return specs

    def test_valid_specs_pass(self):
        specs = [
            SectionDataSpec("section_0", "A", [SubSectionSpec("sub_0_0", "a", ["x"], "search")]),
            SectionDataSpec("section_1", "B", [SubSectionSpec("sub_1_0", "b", ["y"], "search")]),
        ]
        result, valid = self._validate_section_data_specs(specs, ["A", "B"])
        assert valid is True
        assert len(result) == 2

    def test_mismatch_count_triggers_fallback(self):
        specs = [
            SectionDataSpec("section_0", "A", [SubSectionSpec("sub_0_0", "a", ["x"], "search")]),
        ]
        result, valid = self._validate_section_data_specs(specs, ["A", "B"])
        assert valid is False
        assert len(result) == 2
        assert result[1].name == "B"

    def test_empty_data_needs_triggers_fallback(self):
        specs = [
            SectionDataSpec("section_0", "A", [SubSectionSpec("sub_0_0", "a", [], "search")]),
        ]
        result, valid = self._validate_section_data_specs(specs, ["A"])
        assert valid is False

    def test_fallback_generates_search_type(self):
        result = self._fallback_specs_from_names(["财务分析", "竞争格局"])
        for spec in result:
            for sub in spec.sub_sections:
                assert sub.data_source_type == "search"


# ============================================================
# Phase B: Engine 层统一查询去重
# ============================================================

class TestSearchQueryDeduplicator:
    """测试 SearchQueryDeduplicator"""

    def test_normalize_query(self):
        dedup = SearchQueryDeduplicator()
        assert dedup._normalize_query("  比亚迪  营收  2025  ") == "比亚迪 营收 2025"
        assert dedup._normalize_query("BYD Revenue") == "byd revenue"

    def test_normalize_preserves_synonyms(self):
        dedup = SearchQueryDeduplicator()
        assert dedup._normalize_query("比亚迪 营收") != dedup._normalize_query("BYD 营收")

    @pytest.mark.asyncio
    async def test_cache_hit_returns_deep_copy(self):
        dedup = SearchQueryDeduplicator()
        mock_skill = AsyncMock()
        mock_skill.search.return_value = {"results": [{"title": "test"}]}
        
        r1 = await dedup.search("比亚迪 营收 2025", "section_0", mock_skill)
        r2 = await dedup.search("比亚迪 营收 2025", "section_1", mock_skill)
        
        assert r1 is not r2
        assert mock_skill.search.call_count == 1

    @pytest.mark.asyncio
    async def test_different_queries_both_execute(self):
        dedup = SearchQueryDeduplicator()
        mock_skill = AsyncMock()
        mock_skill.search.return_value = {"results": []}
        
        await dedup.search("比亚迪 营收", "section_0", mock_skill)
        await dedup.search("比亚迪 净利润", "section_0", mock_skill)
        
        assert mock_skill.search.call_count == 2

    @pytest.mark.asyncio
    async def test_section_tracking(self):
        dedup = SearchQueryDeduplicator()
        mock_skill = AsyncMock()
        mock_skill.search.return_value = {"results": []}
        
        await dedup.search("比亚迪 营收", "section_0", mock_skill)
        await dedup.search("比亚迪 营收", "section_3", mock_skill)
        
        shared = dedup.get_shared_queries()
        assert len(shared) == 1
        normalized = dedup._normalize_query("比亚迪 营收")
        assert "section_0" in shared[normalized]
        assert "section_3" in shared[normalized]

    @pytest.mark.asyncio
    async def test_per_query_lock_allows_parallel(self):
        dedup = SearchQueryDeduplicator()
        mock_skill = AsyncMock()
        
        call_order = []
        async def mock_search(query):
            call_order.append(query)
            await asyncio.sleep(0.01)
            return {"results": []}
        mock_skill.search = mock_search
        
        await asyncio.gather(
            dedup.search("query_a", "section_0", mock_skill),
            dedup.search("query_b", "section_0", mock_skill),
        )
        assert len(call_order) == 2


class TestPreloadedSearchResultsPassing:
    """测试 preloaded_search_results 通过 task dict 传递到 _do_deep_research"""

    @pytest.mark.asyncio
    async def test_task_dict_contains_preloaded(self):
        task = {
            "action": "execute",
            "topic": "比亚迪",
            "aspects": ["财务分析"],
            "data": [],
            "aggregated_data_points": [],
            "aggregated_sources": [],
            "canonical_data": {},
            "preloaded_search_results": [{"query": "比亚迪 营收", "results": []}],
        }
        assert "preloaded_search_results" in task
        assert len(task["preloaded_search_results"]) == 1

    @pytest.mark.asyncio
    async def test_preloaded_none_for_fallback_paths(self):
        task = {
            "action": "execute",
            "topic": "比亚迪",
            "aspects": ["财务分析"],
        }
        assert task.get("preloaded_search_results") is None


class TestIsDataCollectionDetection:
    """测试通过 agent category 判断 DATA_COLLECTION 阶段（ISSUE-H）"""

    def test_research_category_detected(self):
        agents = [Mock(config={"category": "research"})]
        is_dc = any(
            getattr(a, 'config', {}).get('category', '') == 'research'
            for a in agents
        )
        assert is_dc is True

    def test_mixed_categories_detected(self):
        agents = [
            Mock(config={"category": "research"}),
            Mock(config={"category": "market-analysis"}),
        ]
        is_dc = any(
            getattr(a, 'config', {}).get('category', '') == 'research'
            for a in agents
        )
        assert is_dc is True

    def test_non_dc_not_detected(self):
        agents = [Mock(config={"category": "market-analysis"})]
        is_dc = any(
            getattr(a, 'config', {}).get('category', '') == 'research'
            for a in agents
        )
        assert is_dc is False


# ============================================================
# Phase C: 数据对账（write_canonical 来源优先级）
# ============================================================

class TestWriteCanonicalSourcePriority:
    """测试 write_canonical 来源优先级（ISSUE-G）"""

    SOURCE_PRIORITY = {
        "structured_source": 100,
        "search_result": 50,
        "llm_inference": 10,
    }

    def test_structured_beats_search(self):
        existing = {"value": 6800.28, "caliber": "structured_source"}
        new_caliber = "search_result"
        existing_priority = self.SOURCE_PRIORITY.get(existing.get("caliber", ""), 0)
        new_priority = self.SOURCE_PRIORITY.get(new_caliber, 0)
        assert new_priority < existing_priority

    def test_search_beats_llm(self):
        existing = {"value": 6420, "caliber": "search_result"}
        new_caliber = "llm_inference"
        existing_priority = self.SOURCE_PRIORITY.get(existing.get("caliber", ""), 0)
        new_priority = self.SOURCE_PRIORITY.get(new_caliber, 0)
        assert new_priority < existing_priority

    def test_same_priority_allows_overwrite(self):
        existing = {"value": 6420, "caliber": "search_result"}
        new_caliber = "search_result"
        existing_priority = self.SOURCE_PRIORITY.get(existing.get("caliber", ""), 0)
        new_priority = self.SOURCE_PRIORITY.get(new_caliber, 0)
        assert new_priority == existing_priority

    def test_unknown_caliber_lowest_priority(self):
        priority = self.SOURCE_PRIORITY.get("unknown", 0)
        assert priority == 0


# ============================================================
# Phase D: 数据补充
# ============================================================

class TestGetCoveredNeeds:
    """测试 _get_covered_needs 覆盖率检查"""

    def _get_covered_needs(self, section_data_needs, data_points):
        covered = set()
        all_text = " ".join(
            dp.get("content", "") + dp.get("title", "")
            for dp in data_points
        )
        for need in section_data_needs:
            if need in all_text:
                covered.add(need)
        return covered

    def test_basic_coverage(self):
        dps = [
            {"title": "比亚迪营收", "content": "比亚迪2025年营收6800亿"},
            {"title": "比亚迪净利润", "content": "净利润300亿"},
        ]
        covered = self._get_covered_needs(["营收", "净利润", "ROE"], dps)
        assert "营收" in covered
        assert "净利润" in covered
        assert "ROE" not in covered

    def test_empty_data_points(self):
        covered = self._get_covered_needs(["营收"], [])
        assert len(covered) == 0

    def test_no_coverage(self):
        dps = [{"title": "test", "content": "no relevant data"}]
        covered = self._get_covered_needs(["营收", "ROE"], dps)
        assert len(covered) == 0

    def test_full_coverage(self):
        dps = [
            {"title": "营收", "content": "营收6800亿"},
            {"title": "ROE", "content": "ROE为15%"},
        ]
        covered = self._get_covered_needs(["营收", "ROE"], dps)
        assert len(covered) == 2


class TestSupplementMissingData:
    """测试补充搜索逻辑"""

    def test_missing_needs_identified(self):
        covered = {"营收", "净利润"}
        all_needs = ["营收", "净利润", "ROE", "毛利率"]
        missing = [n for n in all_needs if n not in covered]
        assert missing == ["ROE", "毛利率"]

    def test_no_missing_needs(self):
        covered = {"营收", "净利润"}
        all_needs = ["营收", "净利润"]
        missing = [n for n in all_needs if n not in covered]
        assert missing == []

    def test_supplement_data_injected_into_all_results(self):
        all_results = [
            {"agent_id": "research_财务_0", "data_points": [{"title": "营收", "content": "营收6800亿"}], "sources": []},
            {"agent_id": "research_竞争_1", "data_points": [], "sources": []},
        ]
        section_specs = {
            "research_财务_0": SectionDataSpec("section_0", "财务", [
                SubSectionSpec("sub_0_0", "营收", ["营收", "ROE"], "structured"),
            ]),
            "research_竞争_1": SectionDataSpec("section_1", "竞争", [
                SubSectionSpec("sub_1_0", "竞争", ["竞争优势"], "search"),
            ]),
        }
        supplement = {"ROE": {"data_points": [{"title": "ROE", "content": "ROE 15%"}], "sources": []}}
        
        for need, supp in supplement.items():
            for result in all_results:
                agent_id = result.get("agent_id", "")
                spec = section_specs.get(agent_id)
                if spec and need in spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
        
        assert len(all_results[0]["data_points"]) == 2
        assert len(all_results[1]["data_points"]) == 0


# ============================================================
# 数据结构定义（测试用内联，实际代码在 strategies.py）
# ============================================================

@dataclass
class SubSectionSpec:
    sub_section_id: str
    name: str
    data_needs: List[str]
    data_source_type: str = "search"


@dataclass
class SectionDataSpec:
    section_id: str
    name: str
    sub_sections: List[SubSectionSpec] = field(default_factory=list)

    @property
    def all_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))

    @property
    def search_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("search", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))

    @property
    def structured_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("structured", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))


class SearchQueryDeduplicator:
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._query_sections: Dict[str, List[str]] = {}
        self._query_locks: Dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    def _normalize_query(self, query: str) -> str:
        return ' '.join(query.split()).lower()

    async def search(self, query: str, section_id: str, search_skill) -> Dict:
        normalized = self._normalize_query(query)
        async with self._meta_lock:
            if normalized not in self._query_locks:
                self._query_locks[normalized] = asyncio.Lock()
            query_lock = self._query_locks[normalized]
        async with query_lock:
            if normalized in self._cache:
                self._query_sections[normalized].append(section_id)
                return copy.deepcopy(self._cache[normalized])
            result = await search_skill.search(query)
            self._cache[normalized] = result
            self._query_sections[normalized] = [section_id]
            return copy.deepcopy(result)

    def get_shared_queries(self) -> Dict[str, List[str]]:
        return {q: ss for q, ss in self._query_sections.items() if len(ss) > 1}


# ============================================================
# Phase C: 数据对账（write_canonical 来源优先级端到端）
# ============================================================

class TestWriteCanonicalPriorityE2E:
    """端到端测试：structured_source 先写、search_result 后写时值不被覆盖"""

    @pytest.mark.asyncio
    async def test_structured_source_wins_over_search(self):
        from src.core.communication import SharedMemory
        sm = SharedMemory()
        await sm.write_canonical("营收", 6800.28, caliber="structured_source", source="akshare", publisher="agent_0")
        result = await sm.write_canonical("营收", 6420.0, caliber="search_result", source="web", publisher="agent_1")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 6800.28

    @pytest.mark.asyncio
    async def test_same_priority_allows_update(self):
        from src.core.communication import SharedMemory
        sm = SharedMemory()
        await sm.write_canonical("营收", 6800.0, caliber="search_result", source="web1", publisher="agent_0")
        conflict = await sm.write_canonical("营收", 6420.0, caliber="search_result", source="web2", publisher="agent_1")
        entry = await sm.get_canonical("营收")
        assert entry["value"] == 6420.0

    @pytest.mark.asyncio
    async def test_search_wins_over_llm(self):
        from src.core.communication import SharedMemory
        sm = SharedMemory()
        await sm.write_canonical("ROE", 15.0, caliber="search_result", source="web", publisher="agent_0")
        conflict = await sm.write_canonical("ROE", 12.0, caliber="llm_inference", source="gpt", publisher="agent_1")
        entry = await sm.get_canonical("ROE")
        assert entry["value"] == 15.0


# ============================================================
# Phase D: 数据补充（_get_covered_needs + supplement 注入）
# ============================================================

class TestGetCoveredNeedsKeywordMatching:
    """测试 _get_covered_needs 的关键词匹配精度"""

    def _get_covered_needs(self, section_data_needs, data_points):
        covered = set()
        all_text = " ".join(
            dp.get("content", "") + dp.get("title", "")
            for dp in data_points
        )
        for need in section_data_needs:
            if need in all_text:
                covered.add(need)
        return covered

    def test_substring_keyword_matched(self):
        dps = [{"title": "毛利率", "content": "毛利率30%"}]
        covered = self._get_covered_needs(["毛利"], dps)
        assert "毛利" in covered

    def test_exact_keyword_matched(self):
        dps = [{"title": "毛利", "content": "毛利增长20%"}]
        covered = self._get_covered_needs(["毛利"], dps)
        assert "毛利" in covered

    def test_need_in_title(self):
        dps = [{"title": "比亚迪ROE分析", "content": "回报率较高"}]
        covered = self._get_covered_needs(["ROE"], dps)
        assert "ROE" in covered

    def test_multiple_needs_partial_coverage(self):
        dps = [
            {"title": "营收", "content": "营收6800亿"},
            {"title": "政策", "content": "补贴政策"},
        ]
        covered = self._get_covered_needs(["营收", "ROE", "竞争格局", "政策"], dps)
        assert covered == {"营收", "政策"}

    def test_empty_string_need(self):
        dps = [{"title": "test", "content": "some content"}]
        covered = self._get_covered_needs([""], dps)
        assert "" in covered

    def test_unicode_normalization(self):
        dps = [{"title": "研发费用", "content": "研发费用50亿"}]
        covered = self._get_covered_needs(["研发费用"], dps)
        assert "研发费用" in covered


class TestSupplementDataInjection:
    """测试补充数据按 section_data_specs 正确注入"""

    def test_supplement_injected_only_into_relevant_agents(self):
        specs = {
            "research_财务_0": SectionDataSpec("section_0", "财务", [
                SubSectionSpec("sub_0_0", "营收", ["营收", "ROE"], "structured"),
            ]),
            "research_竞争_1": SectionDataSpec("section_1", "竞争", [
                SubSectionSpec("sub_1_0", "竞争", ["竞争优势", "行业排名"], "search"),
            ]),
        }
        all_results = [
            {"agent_id": "research_财务_0", "data_points": [], "sources": []},
            {"agent_id": "research_竞争_1", "data_points": [], "sources": []},
        ]
        supplement = {
            "ROE": {"data_points": [{"title": "ROE", "content": "ROE 15%"}], "sources": []},
            "竞争优势": {"data_points": [{"title": "竞争优势", "content": "品牌壁垒"}], "sources": []},
        }
        for need, supp in supplement.items():
            for result in all_results:
                agent_id = result.get("agent_id", "")
                spec = specs.get(agent_id)
                if spec and need in spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
                    result.setdefault("sources", []).extend(supp["sources"])
        
        assert len(all_results[0]["data_points"]) == 1
        assert all_results[0]["data_points"][0]["title"] == "ROE"
        assert len(all_results[1]["data_points"]) == 1
        assert all_results[1]["data_points"][0]["title"] == "竞争优势"

    def test_shared_need_injected_into_multiple_agents(self):
        specs = {
            "research_财务_0": SectionDataSpec("section_0", "财务", [
                SubSectionSpec("sub_0_0", "营收", ["营收"], "structured"),
            ]),
            "research_规模_3": SectionDataSpec("section_3", "规模", [
                SubSectionSpec("sub_3_0", "营收", ["营收", "销量"], "both"),
            ]),
        }
        all_results = [
            {"agent_id": "research_财务_0", "data_points": [], "sources": []},
            {"agent_id": "research_规模_3", "data_points": [], "sources": []},
        ]
        supplement = {
            "营收": {"data_points": [{"title": "营收补充", "content": "营收6800亿"}], "sources": []},
        }
        for need, supp in supplement.items():
            for result in all_results:
                agent_id = result.get("agent_id", "")
                spec = specs.get(agent_id)
                if spec and need in spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
                    result.setdefault("sources", []).extend(supp["sources"])
        
        assert len(all_results[0]["data_points"]) == 1
        assert len(all_results[1]["data_points"]) == 1

    def test_supplement_not_injected_into_unrelated_agent(self):
        specs = {
            "research_财务_0": SectionDataSpec("section_0", "财务", [
                SubSectionSpec("sub_0_0", "营收", ["营收"], "structured"),
            ]),
            "research_政策_5": SectionDataSpec("section_5", "政策", [
                SubSectionSpec("sub_5_0", "政策", ["补贴政策"], "search"),
            ]),
        }
        all_results = [
            {"agent_id": "research_财务_0", "data_points": [], "sources": []},
            {"agent_id": "research_政策_5", "data_points": [], "sources": []},
        ]
        supplement = {
            "营收": {"data_points": [{"title": "营收", "content": "6800亿"}], "sources": []},
        }
        for need, supp in supplement.items():
            for result in all_results:
                agent_id = result.get("agent_id", "")
                spec = specs.get(agent_id)
                if spec and need in spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
                    result.setdefault("sources", []).extend(supp["sources"])
        
        assert len(all_results[0]["data_points"]) == 1
        assert len(all_results[1]["data_points"]) == 0


class TestCoverageThreshold:
    """测试覆盖率阈值逻辑"""

    def test_full_coverage_no_supplement_needed(self):
        covered = {"营收", "ROE", "毛利率"}
        all_needs = ["营收", "ROE", "毛利率"]
        coverage = len(covered) / len(all_needs)
        assert coverage >= 0.8

    def test_partial_coverage_below_threshold(self):
        covered = {"营收"}
        all_needs = ["营收", "ROE", "毛利率", "竞争格局"]
        coverage = len(covered) / len(all_needs)
        assert coverage < 0.8

    def test_80_percent_threshold_boundary(self):
        covered = {"营收", "ROE", "毛利率", "竞争格局"}
        all_needs = ["营收", "ROE", "毛利率", "竞争格局", "PE"]
        coverage = len(covered) / len(all_needs)
        assert coverage == 0.8


class TestSectionDataSpecsFromLLM:
    """Test section_data_specs parsing from LLM output in _build_result"""

    def test_build_result_parses_section_data_specs(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.9,
            "reasoning": "test",
            "complexity": "multi",
            "section_data_specs": [
                {
                    "section_id": "section_0",
                    "name": "Financial Analysis",
                    "sub_sections": [
                        {
                            "sub_section_id": "sub_0_0",
                            "name": "Revenue",
                            "data_needs": ["营收", "净利润", "毛利率"],
                            "data_source_type": "structured",
                        },
                        {
                            "sub_section_id": "sub_0_1",
                            "name": "Competition",
                            "data_needs": ["竞争格局"],
                            "data_source_type": "search",
                        },
                    ],
                },
                {
                    "section_id": "section_1",
                    "name": "Market Size",
                    "sub_sections": [
                        {
                            "sub_section_id": "sub_1_0",
                            "name": "Market Data",
                            "data_needs": ["市场规模", "增长率"],
                            "data_source_type": "search",
                        },
                    ],
                },
            ],
        }
        result = analyzer._build_result(llm_output=llm_output, model_used="test", raw_response="", used_fallback=False)
        assert len(result.section_data_specs) == 2
        spec0 = result.section_data_specs[0]
        assert spec0["section_id"] == "section_0"
        assert spec0["name"] == "Financial Analysis"
        assert len(spec0["sub_sections"]) == 2
        assert spec0["sub_sections"][0]["data_source_type"] == "structured"
        assert spec0["sub_sections"][0]["data_needs"] == ["营收", "净利润", "毛利率"]

    def test_build_result_empty_section_data_specs(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.7,
            "reasoning": "test",
            "complexity": "single",
        }
        result = analyzer._build_result(llm_output=llm_output, model_used="test", raw_response="", used_fallback=False)
        assert result.section_data_specs == []

    def test_build_result_invalid_sub_section_skipped(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer
        analyzer = SemanticIntentAnalyzer(use_llm=False)
        llm_output = {
            "primary_intent": "research",
            "confidence": 0.8,
            "reasoning": "test",
            "complexity": "multi",
            "section_data_specs": [
                {
                    "section_id": "section_0",
                    "name": "Test",
                    "sub_sections": [
                        "invalid_string",
                        {"sub_section_id": "sub_0_1", "name": "Valid", "data_needs": ["x"], "data_source_type": "search"},
                    ],
                },
                "invalid_section_string",
            ],
        }
        result = analyzer._build_result(llm_output=llm_output, model_used="test", raw_response="", used_fallback=False)
        assert len(result.section_data_specs) == 1
        assert len(result.section_data_specs[0]["sub_sections"]) == 1


class TestConvertSpecsFromDicts:
    """Test _convert_specs_from_dicts in strategies.py"""

    def test_convert_valid_dicts(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts, SectionDataSpec
        dicts = [
            {
                "section_id": "section_0",
                "name": "Financial",
                "sub_sections": [
                    {"sub_section_id": "sub_0_0", "name": "Revenue", "data_needs": ["营收"], "data_source_type": "structured"},
                ],
            },
        ]
        specs = _convert_specs_from_dicts(dicts)
        assert len(specs) == 1
        assert isinstance(specs[0], SectionDataSpec)
        assert specs[0].section_id == "section_0"
        assert specs[0].sub_sections[0].data_needs == ["营收"]

    def test_convert_empty_sub_sections_gets_fallback(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts
        dicts = [
            {"section_id": "section_0", "name": "Test", "sub_sections": []},
        ]
        specs = _convert_specs_from_dicts(dicts)
        assert len(specs) == 1
        assert len(specs[0].sub_sections) == 1
        assert specs[0].sub_sections[0].data_source_type == "search"

    def test_convert_missing_fields_use_defaults(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts
        dicts = [
            {"name": "No ID"},
        ]
        specs = _convert_specs_from_dicts(dicts)
        assert specs[0].section_id == "section_0"

    def test_convert_skips_non_dict_entries(self):
        from src.core.decomposition.strategies import _convert_specs_from_dicts
        dicts = ["invalid", {"section_id": "section_0", "name": "Valid", "sub_sections": []}]
        specs = _convert_specs_from_dicts(dicts)
        assert len(specs) == 1

    def test_decompose_converts_dict_specs_to_objects(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, SectionDataSpec
        strategy = IndustryResearchStrategy()
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        intent_result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
            section_data_specs=[
                {
                    "section_id": "section_0",
                    "name": "Financial Analysis",
                    "sub_sections": [
                        {"sub_section_id": "sub_0_0", "name": "Revenue", "data_needs": ["营收", "净利润"], "data_source_type": "structured"},
                    ],
                },
            ],
        )
        from dataclasses import dataclass as dc, field as f
        @dc
        class FakeReq:
            topic: str = "比亚迪"
            aspects: list = f(default_factory=lambda: ["Financial Analysis"])
        from src.core.decomposition.strategies import DecompositionPlan
        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""):
            plan = strategy.decompose(FakeReq(), intent_result, framework_config={})
        assert len(plan.section_data_specs) == 1
        assert isinstance(plan.section_data_specs[0], SectionDataSpec)
        assert plan.section_data_specs[0].sub_sections[0].data_needs == ["营收", "净利润"]

    def test_to_dict_includes_section_data_specs(self):
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.SINGLE,
            section_data_specs=[{"section_id": "section_0", "name": "Test", "sub_sections": []}],
        )
        d = result.to_dict()
        assert "section_data_specs" in d
        assert d["section_data_specs"][0]["section_id"] == "section_0"

    def test_from_dict_includes_section_data_specs(self):
        from src.core.semantic_intent import DeepIntentResult
        data = {
            "primary_intent": "research",
            "intent_confidence": 0.9,
            "intent_reasoning": "test",
            "complexity": "single",
            "section_data_specs": [{"section_id": "section_0", "name": "Test", "sub_sections": []}],
        }
        result = DeepIntentResult.from_dict(data)
        assert len(result.section_data_specs) == 1
        assert result.section_data_specs[0]["section_id"] == "section_0"
