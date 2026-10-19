"""
Task 1.2: Utility Skills SKILL.md + skill.py migration tests - TDD mode
"""
import pytest
from pathlib import Path


class TestFileSkillMigration:
    """Verify file_skill SKILL.md + skill.py migration"""

    def test_dir_exists(self):
        assert Path("src/skills/file").is_dir(), "src/skills/file/ directory does not exist"

    def test_skill_md_exists(self):
        assert Path("src/skills/file/SKILL.md").is_file(), "src/skills/file/SKILL.md does not exist"

    def test_skill_py_exists(self):
        assert Path("src/skills/file/skill.py").is_file(), "src/skills/file/skill.py does not exist"

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/file/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "file_skill"
        assert meta["priority"] == "llm"
        assert "read" in meta["capabilities"]
        assert "write" in meta["capabilities"]
        assert "list" in meta["capabilities"]
        assert "delete" in meta["capabilities"]
        assert "file-operation" in meta["categories"]

    def test_skill_md_keywords(self):
        import frontmatter
        post = frontmatter.load("src/skills/file/SKILL.md")
        meta = post.metadata
        assert "文件" in meta["keywords"]
        assert "file" in meta["keywords"]

    def test_re_export(self):
        from src.skills.file.skill import FileSkill
        from src.skills.file_skill import FileSkill as Original
        assert FileSkill is Original


class TestHTTPSkillMigration:
    """Verify http_skill SKILL.md + skill.py migration"""

    def test_dir_exists(self):
        assert Path("src/skills/http").is_dir(), "src/skills/http/ directory does not exist"

    def test_skill_md_exists(self):
        assert Path("src/skills/http/SKILL.md").is_file(), "src/skills/http/SKILL.md does not exist"

    def test_skill_py_exists(self):
        assert Path("src/skills/http/skill.py").is_file(), "src/skills/http/skill.py does not exist"

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/http/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "http_skill"
        assert meta["priority"] == "llm"
        assert "get" in meta["capabilities"]
        assert "post" in meta["capabilities"]
        assert "put" in meta["capabilities"]
        assert "delete" in meta["capabilities"]
        assert "network" in meta["categories"]

    def test_skill_md_keywords(self):
        import frontmatter
        post = frontmatter.load("src/skills/http/SKILL.md")
        meta = post.metadata
        assert "HTTP" in meta["keywords"]
        assert "请求" in meta["keywords"]

    def test_re_export(self):
        from src.skills.http.skill import HTTPSkill
        from src.skills.http_skill import HTTPSkill as Original
        assert HTTPSkill is Original


class TestDocxSkillMigration:
    """Verify docx_skill SKILL.md + skill.py migration"""

    def test_dir_exists(self):
        assert Path("src/skills/docx").is_dir(), "src/skills/docx/ directory does not exist"

    def test_skill_md_exists(self):
        assert Path("src/skills/docx/SKILL.md").is_file(), "src/skills/docx/SKILL.md does not exist"

    def test_skill_py_exists(self):
        assert Path("src/skills/docx/skill.py").is_file(), "src/skills/docx/skill.py does not exist"

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/docx/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "docx_skill"
        assert meta["priority"] == "llm"
        assert "generate_docx" in meta["capabilities"]
        assert "document-generation" in meta["categories"]

    def test_skill_md_keywords(self):
        import frontmatter
        post = frontmatter.load("src/skills/docx/SKILL.md")
        meta = post.metadata
        assert "Word" in meta["keywords"]
        assert "docx" in meta["keywords"]

    def test_re_export(self):
        from src.skills.docx.skill import DocxSkill
        from src.skills.docx_skill import DocxSkill as Original
        assert DocxSkill is Original


class TestWebScraperMigration:
    """Verify web_scraper SKILL.md + skill.py migration"""

    def test_dir_exists(self):
        assert Path("src/skills/web_scraper").is_dir(), "src/skills/web_scraper/ directory does not exist"

    def test_skill_md_exists(self):
        assert Path("src/skills/web_scraper/SKILL.md").is_file(), "src/skills/web_scraper/SKILL.md does not exist"

    def test_skill_py_exists(self):
        assert Path("src/skills/web_scraper/skill.py").is_file(), "src/skills/web_scraper/skill.py does not exist"

    def test_skill_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/web_scraper/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "web_scraper"
        assert meta["priority"] == "web_search"
        assert "scrape" in meta["capabilities"]
        assert "data-collection" in meta["categories"]
        assert "web-search" in meta["categories"]

    def test_skill_md_keywords(self):
        import frontmatter
        post = frontmatter.load("src/skills/web_scraper/SKILL.md")
        meta = post.metadata
        assert "爬虫" in meta["keywords"]
        assert "scraper" in meta["keywords"]

    def test_re_export(self):
        from src.skills.web_scraper.skill import WebScraperSkill
        from src.skills.web_scraper_skill import WebScraperSkill as Original
        assert WebScraperSkill is Original


class TestDiscoveryFindsAllUtilitySkills:
    """SkillDiscovery should find all 4 migrated utility skills"""

    def test_discovery_finds_all_four(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        for expected in ["file_skill", "http_skill", "docx_skill", "web_scraper"]:
            assert expected in names, f"{expected} not discovered, available: {names}"

    def test_discovery_has_code_for_all_four(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        by_name = {m.name: m for m in manifests}
        for name in ["file_skill", "http_skill", "docx_skill", "web_scraper"]:
            assert by_name[name].has_code is True, f"{name} should have skill.py"

    def test_discovery_loads_skill_classes(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        by_name = {m.name: m for m in manifests}
        expected_classes = {
            "file_skill": "FileSkill",
            "http_skill": "HTTPSkill",
            "docx_skill": "DocxSkill",
            "web_scraper": "WebScraperSkill",
        }
        for name, cls_name in expected_classes.items():
            cls = d.load_skill_class(by_name[name])
            assert cls is not None, f"{name} class not loaded"
            assert cls.__name__ == cls_name, f"{name} class name mismatch: {cls.__name__} != {cls_name}"
