"""
Task 1.1: search_skill + news_search SKILL.md 迁移测试 - TDD模式
"""
import pytest
from pathlib import Path


class TestSearchSkillMigration:
    """验证 search_skill 和 news_search 的 SKILL.md 迁移"""

    def test_search_skill_dir_exists(self):
        """src/skills/search/ 目录应存在"""
        assert Path("src/skills/search").is_dir(), "src/skills/search/ 目录不存在"

    def test_search_skill_md_exists(self):
        """src/skills/search/SKILL.md 应存在"""
        assert Path("src/skills/search/SKILL.md").is_file(), "src/skills/search/SKILL.md 不存在"

    def test_search_skill_py_exists(self):
        """src/skills/search/skill.py re-export wrapper 应存在"""
        assert Path("src/skills/search/skill.py").is_file(), "src/skills/search/skill.py 不存在"

    def test_search_skill_md_parseable(self):
        """search SKILL.md 应可解析且包含必需字段"""
        import frontmatter
        post = frontmatter.load("src/skills/search/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "search_skill"
        assert meta["priority"] == "web_search"
        assert "search" in meta["capabilities"]
        assert "web_search" in meta["aliases"]

    def test_news_search_dir_exists(self):
        """src/skills/news_search/ 目录应存在"""
        assert Path("src/skills/news_search").is_dir(), "src/skills/news_search/ 目录不存在"

    def test_news_search_md_exists(self):
        """src/skills/news_search/SKILL.md 应存在"""
        assert Path("src/skills/news_search/SKILL.md").is_file(), "src/skills/news_search/SKILL.md 不存在"

    def test_news_search_py_exists(self):
        """src/skills/news_search/skill.py re-export wrapper 应存在"""
        assert Path("src/skills/news_search/skill.py").is_file(), "src/skills/news_search/skill.py 不存在"

    def test_news_search_md_parseable(self):
        """news_search SKILL.md 应可解析且包含必需字段"""
        import frontmatter
        post = frontmatter.load("src/skills/news_search/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "news_search"
        assert meta["priority"] == "web_search"
        assert "search" in meta["capabilities"]

    def test_search_skill_re_export(self):
        """search/skill.py 应能 re-export SearchSkill"""
        from src.skills.search.skill import SearchSkill
        from src.skills.search_skill import SearchSkill as OriginalSearchSkill
        assert SearchSkill is OriginalSearchSkill

    def test_news_search_re_export(self):
        """news_search/skill.py 应能 re-export NewsSearchSkill"""
        from src.skills.news_search.skill import NewsSearchSkill
        from src.skills.search_skill import NewsSearchSkill as OriginalNewsSearchSkill
        assert NewsSearchSkill is OriginalNewsSearchSkill

    def test_discovery_finds_both(self):
        """SkillDiscovery 应能发现 search_skill 和 news_search"""
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        assert "search_skill" in names, f"search_skill 未被发现，可用: {names}"
        assert "news_search" in names, f"news_search 未被发现，可用: {names}"
