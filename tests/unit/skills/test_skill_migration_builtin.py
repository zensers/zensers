"""
Task 1.4: annual_report_parser + knowledge_query SKILL.md 迁移测试 - TDD模式
"""
import pytest
from pathlib import Path


class TestAnnualReportParserMigration:
    def test_dir_exists(self):
        assert Path("src/skills/annual_report_parser").is_dir()

    def test_skill_md_exists(self):
        assert Path("src/skills/annual_report_parser/SKILL.md").is_file()

    def test_skill_py_exists(self):
        assert Path("src/skills/annual_report_parser/skill.py").is_file()

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/annual_report_parser/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "annual_report_parser"
        assert meta["priority"] == "structured_db"
        assert "parse" in meta["capabilities"] or "analyze" in meta["capabilities"]

    def test_re_export(self):
        from src.skills.annual_report_parser.skill import AnnualReportParserSkill
        from src.skills.analysis.annual_report_parser import AnnualReportParserSkill as Orig
        assert AnnualReportParserSkill is Orig

    def test_discovery_finds(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        assert "annual_report_parser" in names


class TestKnowledgeQueryMigration:
    def test_dir_exists(self):
        assert Path("src/skills/knowledge_query").is_dir()

    def test_skill_md_exists(self):
        assert Path("src/skills/knowledge_query/SKILL.md").is_file()

    def test_skill_py_exists(self):
        assert Path("src/skills/knowledge_query/skill.py").is_file()

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/knowledge_query/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "knowledge_query"
        assert "enrich" in meta["capabilities"]

    def test_re_export(self):
        from src.skills.knowledge_query.skill import KnowledgeQuerySkill
        from src.skills.builtin.knowledge_query_skill import KnowledgeQuerySkill as Orig
        assert KnowledgeQuerySkill is Orig

    def test_discovery_finds(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        assert "knowledge_query" in names
