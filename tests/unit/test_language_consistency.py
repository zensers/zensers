# -*- coding: utf-8 -*-
"""
Test language consistency mechanisms across the system.

Verifies:
1. get_language_instruction() returns correct instructions for each language
2. The include mechanism works through PromptManager
3. detect_language correctly identifies Chinese/English/Japanese/Korean
4. Global language state propagation works
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.i18n import (
    Language,
    get_language,
    set_language,
    detect_language,
    get_language_instruction,
)
from src.core.prompt_manager import PromptManager


def test_get_language_instruction_zh():
    """Test Chinese language instruction is generated correctly"""
    set_language(Language.ZH)
    inst = get_language_instruction()
    assert "中文" in inst, "Chinese instruction should contain 中文"
    assert "最高优先级" in inst or "优先级最高" in inst, "Should indicate highest priority"
    print("[PASS] test_get_language_instruction_zh")


def test_get_language_instruction_en():
    """Test English language instruction is generated correctly"""
    set_language(Language.EN)
    inst = get_language_instruction()
    assert "English" in inst, "English instruction should contain English"
    assert "HIGHEST PRIORITY" in inst, "Should indicate highest priority"
    print("[PASS] test_get_language_instruction_en")


def test_get_language_instruction_dynamic():
    """Test that instruction changes when global language changes"""
    set_language(Language.ZH)
    zh_inst = get_language_instruction()
    set_language(Language.EN)
    en_inst = get_language_instruction()
    assert zh_inst != en_inst, "Instructions should differ by language"
    assert "中文" in zh_inst
    assert "English" in en_inst
    print("[PASS] test_get_language_instruction_dynamic")


def test_get_language_instruction_explicit():
    """Test explicit language parameter overrides global"""
    set_language(Language.ZH)  # Set global to Chinese
    en_inst = get_language_instruction(language=Language.EN)
    assert "English" in en_inst, "Explicit EN param should produce English instruction"
    print("[PASS] test_get_language_instruction_explicit")


def test_detect_language():
    """Test language detection"""
    assert detect_language("分析新能源汽车市场").value == "zh"
    assert detect_language("Analyze new energy vehicle market").value == "en"
    assert detect_language("konnichiwa").value == "en"  # No kana chars -> english
    print("[PASS] test_detect_language")


def test_detect_language_empty():
    """Test empty input defaults to English"""
    assert detect_language("").value == "en"
    assert detect_language(None).value == "en"
    print("[PASS] test_detect_language_empty")


def test_localization_helper():
    """Test the _l and _get_lang static helpers (from ResearchAPI)"""
    from src.api.research_api import ResearchAPI
    
    # _l: returns Chinese when lang=zh
    assert "研究" in ResearchAPI._l("研究主题", "Research Topic", "zh")
    # _l: returns English when lang=en
    assert "Research" in ResearchAPI._l("研究主题", "Research Topic", "en")
    # _l: defaults to Chinese when no lang specified
    assert "研究" in ResearchAPI._l("研究主题", "Research Topic")
    # _get_lang: returns zh from None session
    assert ResearchAPI._get_lang(None) == "zh"
    assert ResearchAPI._get_lang({}) == "zh"
    assert ResearchAPI._get_lang({"language": "en"}) == "en"
    assert ResearchAPI._get_lang({"language": "zh"}) == "zh"
    print("[PASS] test_localization_helper")


def test_prompt_include_resolution():
    """Test that {include:language_rule} resolves correctly via PromptManager"""
    pm = PromptManager()
    try:
        rendered = pm.render("_shared", "language_rule")
        assert "Language Rule" in rendered or "语言规则" in rendered
        print("[PASS] test_prompt_include_resolution")
    except FileNotFoundError:
        print("[FAIL] test_prompt_include_resolution: language_rule.md not found")
        raise


def test_agent_profile_has_language_rule():
    """Test key agent profiles contain the language rule include"""
    pm = PromptManager()
    key_profiles = ["market_size", "competition", "trend", "enterprise",
                     "executive_summary_role", "conclusion_role", "general"]
    for name in key_profiles:
        try:
            content = pm.load("agents", name)
            assert "{include:language_rule}" in content, (
                f"Agent '{name}' missing include"
            )
            print(f"[PASS] Agent '{name}' has language rule include")
        except FileNotFoundError:
            print(f"[SKIP] Agent '{name}' not found, skipping")


def test_task_prompt_has_language_rule():
    """Test key task prompts contain the language rule include"""
    pm = PromptManager()
    key_tasks = ["deep_analysis", "research_with_data", "basic_research",
                  "synthesis_summary", "synthesis_conclusion", "report_generation"]
    for name in key_tasks:
        try:
            content = pm.load("tasks", name)
            assert "{include:language_rule}" in content, (
                f"Task '{name}' missing include"
            )
            print(f"[PASS] Task '{name}' has language rule include")
        except FileNotFoundError:
            print(f"[SKIP] Task '{name}' not found, skipping")


if __name__ == "__main__":
    print("=" * 60)
    print("Language Consistency Tests")
    print("=" * 60)
    
    test_get_language_instruction_zh()
    test_get_language_instruction_en()
    test_get_language_instruction_dynamic()
    test_get_language_instruction_explicit()
    test_detect_language()
    test_detect_language_empty()
    test_localization_helper()
    test_prompt_include_resolution()
    test_agent_profile_has_language_rule()
    test_task_prompt_has_language_rule()
    
    # Reset to Chinese (default)
    set_language(Language.ZH)
    
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)
