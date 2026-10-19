"""
Task 1.6: llm SKILL.md 迁移测试 - TDD模式
"""
import pytest
from pathlib import Path


class TestLlmSkillMigration:
    def test_dir_exists(self):
        assert Path("src/skills/llm").is_dir()

    def test_skill_md_exists(self):
        assert Path("src/skills/llm/SKILL.md").is_file()

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/llm/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "llm"
        assert meta["is_intrinsic"] is True
        assert meta["priority"] == "llm"
        assert meta["skill_type"] == "standard"

    def test_no_skill_py(self):
        assert not Path("src/skills/llm/skill.py").exists()

    def test_discovery_finds(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        assert "llm" in names
