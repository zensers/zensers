import os
import sys

import pytest

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "agents")
REQUIRED_INCLUDE = "{include:quality_rubric}"
EXPECTED_COUNT = 24


def test_all_agent_prompts_have_quality_rubric():
    files = sorted(f for f in os.listdir(PROMPTS_DIR) if f.endswith(".md"))
    assert len(files) == EXPECTED_COUNT, f"Expected {EXPECTED_COUNT} agent prompts, found {len(files)}"

    missing = []
    for fname in files:
        filepath = os.path.join(PROMPTS_DIR, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if REQUIRED_INCLUDE not in content:
            missing.append(fname)

    assert not missing, f"Missing {REQUIRED_INCLUDE} in: {', '.join(missing)}"


def test_quality_rubric_include_at_file_end():
    files = sorted(f for f in os.listdir(PROMPTS_DIR) if f.endswith(".md"))
    for fname in files:
        filepath = os.path.join(PROMPTS_DIR, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert REQUIRED_INCLUDE in content, f"{fname} missing {REQUIRED_INCLUDE}"
        last_line = content.strip().split("\n")[-1]
        assert REQUIRED_INCLUDE in last_line, f"{fname}: {REQUIRED_INCLUDE} should be on last line"


def test_quality_rubric_file_exists():
    rubric_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "_shared", "quality_rubric.md")
    assert os.path.isfile(rubric_path), "quality_rubric.md not found in prompts/_shared/"


RUBRIC_MARKER = "Quality Evaluation Rubric"


def test_load_profile_resolves_rubric_at_runtime():
    """Verify that load_profile() actually resolves {include:quality_rubric}"""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.core.prompt_manager import PromptManager
    pm = PromptManager()
    pm.reset_instance()
    pm = PromptManager()

    for name in ["body_agent", "trend", "conversation", "section_analysis_system",
                  "intent_analysis_user", "survey_cross_synthesis", "validation"]:
        profile = pm.load_profile(name)
        assert REQUIRED_INCLUDE not in profile.system_prompt, (
            f"{name}: include tag not resolved"
        )
        assert RUBRIC_MARKER in profile.system_prompt, (
            f"{name}: rubric content missing from resolved prompt"
        )


def test_render_resolves_rubric_at_runtime():
    """Verify that render() also resolves rubric"""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.core.prompt_manager import PromptManager
    pm = PromptManager()
    pm.reset_instance()
    pm = PromptManager()

    result = pm.render("agents", "section_analysis_system")
    assert REQUIRED_INCLUDE not in result, "render() must resolve includes"
    assert RUBRIC_MARKER in result, "render() must include rubric content"
