# -*- coding: utf-8 -*-
"""
LLM 实体提取器测试

测试 LLMEntityExtractor 的核心功能：
- 纯正则模式（无 LLM）
- LLM 兜底触发条件
- LLM 响应解析（JSON/代码块/容错）
- 合并去重
- 字典加载
"""

import json
import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, AsyncMock

from src.core.memory.extraction.llm_entity_extractor import LLMEntityExtractor
from src.core.memory.extraction.entity_extractor import EntityExtractor


def _make_sync_llm(response_content: str):
    """创建模拟同步 LLM 客户端（execute 返回 dict）"""

    class FakeLLM:
        async def execute(self, **kwargs):
            return {
                "success": True,
                "data": {"content": response_content},
                "message": "OK",
            }

    return FakeLLM()


def _make_failing_llm():
    class FakeLLM:
        async def execute(self, **kwargs):
            return {"success": False, "error": "API error", "message": "fail"}

    return FakeLLM()


# ========== 1. 纯正则模式（无 LLM 客户端）==========


class TestRegexOnly:
    def test_no_llm_returns_regex_results(self):
        extractor = LLMEntityExtractor(min_entities=999)
        text = "宁德时代和比亚迪在2024年的市场份额持续增长"
        result = extractor.extract(text)
        assert len(result) > 0
        types = {e["entity_type"] for e in result}
        assert "company" in types

    def test_empty_text_returns_empty(self):
        extractor = LLMEntityExtractor()
        assert extractor.extract("") == []
        assert extractor.extract(None) == []

    def test_regex_sufficient_no_llm_called(self):
        extractor = LLMEntityExtractor(min_entities=1)
        text = "宁德时代在2024年营收增长30%"
        result = extractor.extract(text)
        assert len(result) >= 1


# ========== 2. LLM 兜底触发 ==========


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_llm_triggered_when_regex_insufficient(self):
        llm = _make_sync_llm(
            json.dumps(
                [
                    {"name": "量子计算", "type": "technology", "confidence": 0.8},
                    {"name": "中国", "type": "location", "confidence": 0.9},
                ]
            )
        )
        extractor = LLMEntityExtractor(llm_client=llm, min_entities=5)
        text = "量子计算技术在中国发展迅速"
        result = await extractor.extract_async(text)
        names = {e["name"] for e in result}
        assert "量子计算" in names
        assert "中国" in names

    @pytest.mark.asyncio
    async def test_llm_not_triggered_when_regex_sufficient(self):
        llm = _make_sync_llm('[{"name": "fake", "type": "company", "confidence": 0.5}]')
        extractor = LLMEntityExtractor(llm_client=llm, min_entities=1)
        text = "宁德时代和比亚迪在2024年市场份额增长"
        result = await extractor.extract_async(text)
        names = {e["name"] for e in result}
        assert "fake" not in names

    @pytest.mark.asyncio
    async def test_llm_failure_returns_regex_results(self):
        llm = _make_failing_llm()
        extractor = LLMEntityExtractor(llm_client=llm, min_entities=999)
        text = "宁德时代在新能源领域布局"
        result = await extractor.extract_async(text)
        assert len(result) >= 1
        assert result[0]["name"] == "宁德时代"


# ========== 3. LLM 响应解析 ==========


class TestLLMResponseParsing:
    def test_parse_plain_json_array(self):
        extractor = LLMEntityExtractor()
        content = json.dumps(
            [
                {"name": "华为", "type": "company", "confidence": 0.95},
                {"name": "5G", "type": "technology", "confidence": 0.8},
            ]
        )
        entities = extractor._parse_json_entities(content)
        assert len(entities) == 2
        assert entities[0]["name"] == "华为"
        assert entities[0]["entity_type"] == "company"

    def test_parse_json_code_block(self):
        extractor = LLMEntityExtractor()
        content = "```json\n[\n  {\"name\": \"腾讯\", \"type\": \"company\", \"confidence\": 0.9}\n]\n```"
        entities = extractor._parse_json_entities(content)
        assert len(entities) == 1
        assert entities[0]["name"] == "腾讯"

    def test_parse_json_with_surrounding_text(self):
        extractor = LLMEntityExtractor()
        content = 'Here are the entities:\n[{"name": "阿里", "type": "company", "confidence": 0.85}]\nEnd of list.'
        entities = extractor._parse_json_entities(content)
        assert len(entities) == 1

    def test_parse_invalid_json_returns_empty(self):
        extractor = LLMEntityExtractor()
        entities = extractor._parse_json_entities("not json at all")
        assert entities == []

    def test_parse_non_array_returns_empty(self):
        extractor = LLMEntityExtractor()
        entities = extractor._parse_json_entities('{"name": "oops"}')
        assert entities == []

    def test_parse_items_missing_fields_skipped(self):
        extractor = LLMEntityExtractor()
        content = json.dumps(
            [
                {"name": "valid", "type": "company", "confidence": 0.9},
                {"name": "", "type": "company"},
                {"type": "company"},
                "not a dict",
            ]
        )
        entities = extractor._parse_json_entities(content)
        assert len(entities) == 1

    def test_parse_unknown_type_defaults_to_company(self):
        extractor = LLMEntityExtractor()
        content = json.dumps([{"name": "thing", "type": "unknown_type", "confidence": 0.5}])
        entities = extractor._parse_json_entities(content)
        assert entities[0]["entity_type"] == "company"

    def test_confidence_clamped(self):
        extractor = LLMEntityExtractor()
        content = json.dumps([{"name": "X", "type": "company", "confidence": 2.0}])
        entities = extractor._parse_json_entities(content)
        assert entities[0]["confidence"] == 1.0

    def test_parse_markdown_code_block_no_language(self):
        extractor = LLMEntityExtractor()
        content = "```\n[{\"name\": \"字节跳动\", \"type\": \"company\", \"confidence\": 0.9}]\n```"
        entities = extractor._parse_json_entities(content)
        assert len(entities) == 1

    def test_llm_entities_have_source_property(self):
        extractor = LLMEntityExtractor()
        content = json.dumps([{"name": "X", "type": "company", "confidence": 0.8}])
        entities = extractor._parse_json_entities(content)
        assert entities[0]["properties"]["source"] == "llm"


# ========== 4. 合并去重 ==========


class TestMerge:
    def test_merge_no_duplicates(self):
        extractor = LLMEntityExtractor()
        regex = [
            {
                "entity_id": "1",
                "entity_type": "company",
                "name": "宁德时代",
                "aliases": ["CATL"],
                "confidence": 0.95,
                "mention_count": 1,
                "properties": {},
            }
        ]
        llm = [
            {
                "entity_id": "2",
                "entity_type": "technology",
                "name": "固态电池",
                "aliases": [],
                "confidence": 0.8,
                "mention_count": 1,
                "properties": {"source": "llm"},
            }
        ]
        result = extractor._merge(regex, llm)
        assert len(result) == 2
        names = {e["name"] for e in result}
        assert "宁德时代" in names
        assert "固态电池" in names

    def test_merge_deduplicates_by_name(self):
        extractor = LLMEntityExtractor()
        regex = [
            {
                "entity_id": "1",
                "entity_type": "company",
                "name": "宁德时代",
                "aliases": [],
                "confidence": 0.95,
                "mention_count": 1,
                "properties": {},
            }
        ]
        llm = [
            {
                "entity_id": "2",
                "entity_type": "company",
                "name": "宁德时代",
                "aliases": [],
                "confidence": 0.8,
                "mention_count": 1,
                "properties": {},
            }
        ]
        result = extractor._merge(regex, llm)
        assert len(result) == 1

    def test_merge_deduplicates_by_alias(self):
        extractor = LLMEntityExtractor()
        regex = [
            {
                "entity_id": "1",
                "entity_type": "company",
                "name": "宁德时代",
                "aliases": ["CATL"],
                "confidence": 0.95,
                "mention_count": 1,
                "properties": {},
            }
        ]
        llm = [
            {
                "entity_id": "2",
                "entity_type": "company",
                "name": "CATL",
                "aliases": [],
                "confidence": 0.8,
                "mention_count": 1,
                "properties": {},
            }
        ]
        result = extractor._merge(regex, llm)
        assert len(result) == 1

    def test_merge_llm_confidence_discounted(self):
        extractor = LLMEntityExtractor()
        regex = []
        llm = [
            {
                "entity_id": "2",
                "entity_type": "technology",
                "name": "量子计算",
                "aliases": [],
                "confidence": 0.9,
                "mention_count": 1,
                "properties": {},
            }
        ]
        result = extractor._merge(regex, llm)
        assert result[0]["confidence"] == 0.81  # 0.9 * 0.9


# ========== 5. extract_content 从不同响应格式提取 ==========


class TestExtractContent:
    def test_dict_with_data_content(self):
        extractor = LLMEntityExtractor()
        resp = {"success": True, "data": {"content": "hello"}}
        assert extractor._extract_content(resp) == "hello"

    def test_dict_with_data_string(self):
        extractor = LLMEntityExtractor()
        resp = {"success": True, "data": "hello"}
        assert extractor._extract_content(resp) == "hello"

    def test_dict_failure_returns_none(self):
        extractor = LLMEntityExtractor()
        resp = {"success": False, "error": "boom"}
        assert extractor._extract_content(resp) is None

    def test_string_response(self):
        extractor = LLMEntityExtractor()
        assert extractor._extract_content("raw text") == "raw text"


# ========== 6. 字典加载 ==========


class TestDictionaryLoading:
    def test_entity_extractor_loads_dictionary(self):
        extractor = EntityExtractor()
        assert len(extractor._dict_companies) > 5
        assert "华为" in extractor._dict_companies
        assert "英伟达" in extractor._dict_companies

    def test_dictionary_aliases_loaded(self):
        extractor = EntityExtractor()
        assert extractor._dict_aliases.get("CATL") == "宁德时代"
        assert extractor._dict_aliases.get("Huawei") == "华为"

    def test_dictionary_persons_loaded(self):
        extractor = EntityExtractor()
        assert "任正非" in extractor._dict_persons
        assert "雷军" in extractor._dict_persons

    def test_dictionary_products_loaded(self):
        extractor = EntityExtractor()
        assert "4680电池" in extractor._dict_products

    def test_dictionary_metrics_loaded(self):
        extractor = EntityExtractor()
        assert "毛利率" in extractor._dict_metrics
        assert "出货量" in extractor._dict_metrics

    def test_dictionary_extracts_extended_companies(self):
        extractor = EntityExtractor()
        text = "华为和英伟达在AI芯片领域的竞争加剧"
        result = extractor.extract(text)
        names = {e["name"] for e in result}
        assert "华为" in names or "英伟达" in names

    def test_dictionary_extracts_extended_metrics(self):
        extractor = EntityExtractor()
        text = "该公司的毛利率和出货量均创新高"
        result = extractor.extract(text)
        names = {e["name"] for e in result}
        assert "毛利率" in names or "出货量" in names

    def test_missing_dictionary_no_error(self):
        extractor = EntityExtractor(config={"dictionary_path": "/nonexistent/path.yaml"})
        assert extractor._dict_companies == []


# ========== 7. 同步提取（LLM 兜底）==========


class TestSyncExtract:
    def test_sync_extract_with_callable_llm(self):
        response = json.dumps(
            [{"name": "小米", "type": "company", "confidence": 0.9}]
        )
        llm = _make_sync_llm(response)
        extractor = LLMEntityExtractor(llm_client=llm, min_entities=5)
        text = "小米发布新产品"
        result = extractor.extract(text)
        names = {e["name"] for e in result}
        assert "小米" in names

    def test_sync_extract_no_llm_returns_regex(self):
        extractor = LLMEntityExtractor(min_entities=5)
        text = "宁德时代市场份额增长"
        result = extractor.extract(text)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_sync_extract_from_async_context_graceful_fallback(self):
        llm = _make_sync_llm(
            json.dumps([{"name": "量子计算", "type": "technology", "confidence": 0.9}])
        )
        extractor = LLMEntityExtractor(llm_client=llm, min_entities=999)
        text = "宁德时代在新能源领域布局"
        result = extractor.extract(text)
        assert len(result) >= 1
        names = {e["name"] for e in result}
        assert "宁德时代" in names


# ========== 8. 别名归一化（P2 修复验证）==========


class TestAliasNormalization:
    def test_metric_alias_normalized_in_dedup(self):
        extractor = EntityExtractor()
        text = "该公司的市占率达到35%"
        result = extractor.extract(text)
        names = {e["name"] for e in result if e["entity_type"] == "metric"}
        assert "市场份额" in names
        assert "市占率" not in names

    def test_metric_alias_and_canonical_merge(self):
        extractor = EntityExtractor()
        text = "市场份额和市占率都在增长"
        result = extractor.extract(text)
        metrics = [e for e in result if e["name"] == "市场份额"]
        assert len(metrics) == 1
        assert "市占率" in metrics[0].get("aliases", [])

    def test_product_alias_normalized(self):
        extractor = EntityExtractor()
        text = "问界销量突破10万台"
        result = extractor.extract(text)
        product_names = {e["name"] for e in result if e["entity_type"] == "product"}
        assert "AITO问界" in product_names

    def test_person_alias_found_in_text(self):
        extractor = EntityExtractor()
        text = "Elon Musk宣布了新计划"
        result = extractor.extract(text)
        person_names = {e["name"] for e in result if e["entity_type"] == "person"}
        assert "马斯克" in person_names

    def test_metric_aliases_in_dict_aliases(self):
        extractor = EntityExtractor()
        assert extractor._dict_aliases.get("市占率") == "市场份额"
        assert extractor._dict_aliases.get("收入") == "营收"
        assert extractor._dict_aliases.get("利润") == "净利润"

    def test_product_aliases_in_dict_aliases(self):
        extractor = EntityExtractor()
        assert extractor._dict_aliases.get("问界") == "AITO问界"

    def test_person_aliases_in_dict_aliases(self):
        extractor = EntityExtractor()
        assert extractor._dict_aliases.get("Elon Musk") == "马斯克"


# ========== 9. 导入验证 ==========


class TestImport:
    def test_import_from_extraction_module(self):
        from src.core.memory.extraction import LLMEntityExtractor

        assert LLMEntityExtractor is not None

    def test_import_from_llm_module(self):
        from src.core.memory.extraction.llm_entity_extractor import LLMEntityExtractor

        assert LLMEntityExtractor is not None
