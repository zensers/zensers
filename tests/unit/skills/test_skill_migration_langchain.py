"""
Task 1.5: LangChain Skill SKILL.md 迁移测试 - TDD模式
"""
import pytest
from pathlib import Path


class TestLangChainSkillMigration:
    LANGCHAIN_SKILLS = ["lc_tavily_search", "lc_arxiv", "lc_wikipedia", "lc_python_repl"]

    @pytest.mark.parametrize("skill_name", LANGCHAIN_SKILLS)
    def test_dir_exists(self, skill_name):
        assert Path(f"src/skills/{skill_name}").is_dir(), f"{skill_name} 目录不存在"

    @pytest.mark.parametrize("skill_name", LANGCHAIN_SKILLS)
    def test_skill_md_exists(self, skill_name):
        assert Path(f"src/skills/{skill_name}/SKILL.md").is_file(), f"{skill_name}/SKILL.md 不存在"

    @pytest.mark.parametrize("skill_name", LANGCHAIN_SKILLS)
    def test_skill_md_parseable(self, skill_name):
        import frontmatter
        post = frontmatter.load(f"src/skills/{skill_name}/SKILL.md")
        meta = post.metadata
        assert meta["name"] == skill_name
        assert meta["skill_type"] == "langchain"
        assert meta["priority"] in ("web_search", "llm")
        assert isinstance(meta["capabilities"], list)
        assert len(meta["capabilities"]) > 0

    @pytest.mark.parametrize("skill_name", LANGCHAIN_SKILLS)
    def test_no_skill_py(self, skill_name):
        """LangChain Skill 不需要 skill.py"""
        assert not Path(f"src/skills/{skill_name}/skill.py").exists(), \
            f"{skill_name} 不应有 skill.py（由 registry _create_* 方法创建）"

    def test_discovery_finds_all(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        for skill_name in self.LANGCHAIN_SKILLS:
            assert skill_name in names, f"{skill_name} 未被发现"
