import pytest
from pathlib import Path

from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


@pytest.fixture
def prompts_dir(tmp_path):
    tmpl = tmp_path / "chapter_write.tmpl"
    tmpl.write_text("# 章节撰写任务\n核心问题：${topic}\n章节名：${section_name}", encoding="utf-8")
    return tmp_path


class TestPromptManagerLoad:
    def test_load_and_render_template(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        result = pm.get("chapter_write", topic="新能源汽车", section_name="市场规模")
        assert "新能源汽车" in result
        assert "市场规模" in result

    def test_load_nonexistent_template_raises(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        with pytest.raises(FileNotFoundError):
            pm.get("nonexistent")

    def test_missing_variable_raises_keyerror(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        with pytest.raises(KeyError):
            pm.get("chapter_write", topic="新能源汽车")


class TestPromptManagerCache:
    def test_template_cached_after_first_load(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        pm.get("chapter_write", topic="T1", section_name="S1")
        assert "chapter_write" in pm._cache

    def test_reload_specific_template(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        pm.get("chapter_write", topic="T1", section_name="S1")
        pm.reload("chapter_write")
        assert "chapter_write" not in pm._cache

    def test_reload_all_templates(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        pm.get("chapter_write", topic="T1", section_name="S1")
        pm.reload()
        assert len(pm._cache) == 0


class TestPromptManagerHotUpdate:
    def test_hot_update_reflects_file_change(self, prompts_dir):
        pm = PromptManager(prompts_dir=prompts_dir)
        result1 = pm.get("chapter_write", topic="T1", section_name="S1")
        assert "核心问题" in result1

        tmpl = prompts_dir / "chapter_write.tmpl"
        tmpl.write_text("# UPDATED\n核心问题：${topic}\n章节名：${section_name}", encoding="utf-8")

        pm.reload("chapter_write")
        result2 = pm.get("chapter_write", topic="T1", section_name="S1")
        assert "UPDATED" in result2


class TestPromptManagerAllTemplates:
    def test_all_nine_templates_load(self, tmp_path):
        template_names = [
            "chapter_write", "chapter_rewrite", "chapter_patch_data",
            "chapter_review", "global_review", "global_verify_issues",
            "data_extraction", "conflict_resolution", "exec_summary",
        ]
        for name in template_names:
            (tmp_path / f"{name}.tmpl").write_text(
                f"${{topic}} ${{section_name}}", encoding="utf-8"
            )

        pm = PromptManager(prompts_dir=tmp_path)
        for name in template_names:
            result = pm.get(name, topic="T", section_name="S")
            assert "T" in result
