# -*- coding: utf-8 -*-
"""
KeywordRegistry Unit Tests

Tests for the centralized keyword registry:
- YAML loading and parsing
- Pattern compilation correctness
- Singleton behavior
- Fallback on missing config
- Listed company detection
- Implicit intent detection
- Global feedback detection
"""

import pytest
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.core.intent.keyword_registry import KeywordRegistry, get_registry, reload_registry


class TestKeywordRegistryYAMLLoading:
    """KeywordRegistry 应正确加载和解析 YAML 配置"""

    def test_loads_default_config(self):
        registry = get_registry()
        assert len(registry._revision_patterns) > 0, "应加载 revision_intents"
        assert len(registry._implicit_zh_patterns) > 0, "应加载隐含意图中文模式"
        assert len(registry._implicit_en_patterns) > 0, "应加载隐含意图英文模式"
        assert len(registry._global_feedback_zh) > 0, "应加载全局反馈中文关键词"
        assert len(registry._listed_company_names) > 0, "应加载公司名称列表"

    def test_handles_missing_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nonexistent.yaml"
            registry = KeywordRegistry(config_path=missing)
            assert len(registry._revision_patterns) == 0
            assert len(registry._implicit_zh_patterns) == 0

    def test_handles_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("::: invalid yaml {{{")
            f.flush()
            registry = KeywordRegistry(config_path=Path(f.name))
            assert len(registry._revision_patterns) == 0

    def test_handles_empty_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("")
            f.flush()
            registry = KeywordRegistry(config_path=Path(f.name))
            assert len(registry._revision_patterns) == 0


class TestKeywordRegistryPatternCompilation:
    """模式应被正确编译为正则表达式"""

    def test_revision_patterns_are_compiled(self):
        registry = get_registry()
        for action_type, patterns in registry.get_revision_patterns().items():
            for p in patterns:
                assert isinstance(p, re.Pattern), f"{action_type} 的模式应为编译后的正则"

    def test_implicit_patterns_are_compiled(self):
        registry = get_registry()
        for p in registry._implicit_zh_patterns:
            assert isinstance(p, re.Pattern)
        for p in registry._implicit_en_patterns:
            assert isinstance(p, re.Pattern)

    def test_global_feedback_en_patterns_compiled(self):
        registry = get_registry()
        for p in registry._global_feedback_en:
            assert isinstance(p, re.Pattern)

    def test_invalid_regex_is_skipped_gracefully(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("""
revision_intents:
  modify:
    patterns:
      - "valid_pattern"
      - "[invalid(regex"
implicit_intent:
  chinese:
    - "[broken"
  english: []
global_feedback:
  chinese: []
  english: []
revision_intent_mapper: {}
listed_company_indicators:
  suffixes: []
  names: []
""")
            f.flush()
            registry = KeywordRegistry(config_path=Path(f.name))
            assert "modify" in registry._revision_patterns
            assert len(registry._implicit_zh_patterns) == 0, "无效正则应被跳过"


class TestKeywordRegistrySingleton:
    """get_registry 应返回单例"""

    def test_get_registry_returns_same_instance(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_reload_registry_creates_new_instance(self):
        r1 = get_registry()
        r2 = reload_registry()
        assert r1 is not r2
        r3 = get_registry()
        assert r3 is r2


class TestKeywordRegistryIsImplicitIntent:
    """is_implicit_intent 应正确识别隐含意图"""

    def setup_method(self):
        self.registry = get_registry()

    def test_chinese_why(self):
        assert self.registry.is_implicit_intent("为什么评分低") is True

    def test_chinese_insufficient(self):
        assert self.registry.is_implicit_intent("深度不够") is True

    def test_chinese_inaccurate(self):
        assert self.registry.is_implicit_intent("数据不准确") is True

    def test_chinese_very_bad(self):
        assert self.registry.is_implicit_intent("质量很差") is True

    def test_english_why_poor(self):
        assert self.registry.is_implicit_intent("why is the quality so poor") is True

    def test_english_insufficient(self):
        assert self.registry.is_implicit_intent("insufficient data") is True

    def test_normal_text_not_implicit(self):
        assert self.registry.is_implicit_intent("修改第三章") is False

    def test_travel_not_implicit(self):
        assert self.registry.is_implicit_intent("我去出差了") is False

    def test_gap_not_implicit(self):
        assert self.registry.is_implicit_intent("分析两者的差距") is False


class TestKeywordRegistryIsGlobalFeedback:
    """is_global_feedback 应正确识别全局反馈"""

    def setup_method(self):
        self.registry = get_registry()

    def test_chinese_overall(self):
        assert self.registry.is_global_feedback("整体评分低") is True

    def test_chinese_total(self):
        assert self.registry.is_global_feedback("总体质量差") is True

    def test_english_overall(self):
        assert self.registry.is_global_feedback("overall quality is poor") is True

    def test_section_level_not_global(self):
        assert self.registry.is_global_feedback("第三章数据不足") is False


class TestKeywordRegistryIsListedCompany:
    """is_listed_company_topic 应正确识别上市公司话题"""

    def setup_method(self):
        self.registry = get_registry()

    def test_by_suffix(self):
        assert self.registry.is_listed_company_topic("腾讯公司") is True

    def test_by_name(self):
        assert self.registry.is_listed_company_topic("比亚迪") is True

    def test_extended_names(self):
        for name in ["蔚来", "小鹏", "理想", "京东", "拼多多", "美团", "小米", "百度", "格力"]:
            assert self.registry.is_listed_company_topic(name) is True, f"{name} 应被识别"

    def test_non_company(self):
        assert self.registry.is_listed_company_topic("市场份额") is False

    def test_empty_string(self):
        assert self.registry.is_listed_company_topic("") is False

    def test_none_like(self):
        assert self.registry.is_listed_company_topic(None or "") is False


class TestKeywordRegistryGetRevisionPatternStrings:
    """get_revision_pattern_strings 应从已编译模式构建"""

    def test_returns_dict(self):
        registry = get_registry()
        result = registry.get_revision_pattern_strings()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_values_are_valid_action_types(self):
        registry = get_registry()
        result = registry.get_revision_pattern_strings()
        for pattern_str, action_type in result.items():
            assert isinstance(action_type, str)
            assert len(action_type) > 0

    def test_keys_are_pipe_joined_patterns(self):
        registry = get_registry()
        result = registry.get_revision_pattern_strings()
        for pattern_str in result.keys():
            assert "|" in pattern_str or len(pattern_str) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
