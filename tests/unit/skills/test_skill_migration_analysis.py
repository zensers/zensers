"""
Task 1.3 Steps 2-7: Analysis Skills SKILL.md migration tests - TDD mode
Verifies 6 analysis skills: stock_analysis, market_analysis, data_analysis,
policy_analysis, tech_trend, risk_analysis
"""
import pytest
from pathlib import Path

SKILLS_DIR = Path("src/skills")

SKILL_SPECS = {
    "stock_analysis": {
        "dir": SKILLS_DIR / "stock_analysis",
        "module": "stock_analysis",
        "class_name": "StockAnalysisSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": [
            "Financial Analysis",
            "Valuation Analysis",
            "Investment Advice",
            "Company Analysis",
        ],
    },
    "market_analysis": {
        "dir": SKILLS_DIR / "market_analysis",
        "module": "market_analysis",
        "class_name": "MarketAnalysisSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": [
            "Competitive Landscape",
            "Industry Chain",
            "Strategic Intent",
            "战略意图",
            "战略意图推断",
            "Company Analysis",
        ],
    },
    "data_analysis": {
        "dir": SKILLS_DIR / "data_analysis",
        "module": "data_analysis",
        "class_name": "DataAnalysisSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": [
            "Market Size",
            "Market Share",
            "Industry Trends",
            "Development Trends",
            "User Analysis",
            "Regional Distribution",
            "Growth Analysis",
            "Sales Analysis",
            "Data Comparison",
            "Financial Analysis",
            "Valuation Analysis",
            "Investment Advice",
        ],
    },
    "policy_analysis": {
        "dir": SKILLS_DIR / "policy_analysis",
        "module": "policy_analysis",
        "class_name": "PolicyAnalysisSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": ["Policy Environment"],
    },
    "tech_trend": {
        "dir": SKILLS_DIR / "tech_trend",
        "module": "tech_trend",
        "class_name": "TechTrendSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": ["Technology Trends"],
    },
    "risk_analysis": {
        "dir": SKILLS_DIR / "risk_analysis",
        "module": "risk_analysis",
        "class_name": "RiskAnalysisSkill",
        "priority": "llm",
        "capabilities": ["analyze"],
        "aspect_coverage": ["Risk Analysis"],
    },
}


class TestAnalysisSkillDirectories:
    """Each skill directory exists with SKILL.md and skill.py"""

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_dir_exists(self, skill_name):
        spec = SKILL_SPECS[skill_name]
        assert spec["dir"].is_dir(), f"{spec['dir']} directory does not exist"

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_skill_md_exists(self, skill_name):
        spec = SKILL_SPECS[skill_name]
        assert (spec["dir"] / "SKILL.md").is_file(), f"{spec['dir'] / 'SKILL.md'} does not exist"

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_skill_py_exists(self, skill_name):
        spec = SKILL_SPECS[skill_name]
        assert (spec["dir"] / "skill.py").is_file(), f"{spec['dir'] / 'skill.py'} does not exist"


class TestAnalysisSkillMdParseable:
    """Each SKILL.md is parseable with correct name/priority/capabilities/aspect_coverage"""

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_md_parseable_name(self, skill_name):
        import frontmatter
        spec = SKILL_SPECS[skill_name]
        post = frontmatter.load(str(spec["dir"] / "SKILL.md"))
        assert post.metadata["name"] == skill_name

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_md_parseable_priority(self, skill_name):
        import frontmatter
        spec = SKILL_SPECS[skill_name]
        post = frontmatter.load(str(spec["dir"] / "SKILL.md"))
        assert post.metadata["priority"] == spec["priority"]

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_md_parseable_capabilities(self, skill_name):
        import frontmatter
        spec = SKILL_SPECS[skill_name]
        post = frontmatter.load(str(spec["dir"] / "SKILL.md"))
        for cap in spec["capabilities"]:
            assert cap in post.metadata["capabilities"], \
                f"{skill_name}: expected capability '{cap}' not found in {post.metadata['capabilities']}"

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_md_parseable_aspect_coverage(self, skill_name):
        import frontmatter
        spec = SKILL_SPECS[skill_name]
        post = frontmatter.load(str(spec["dir"] / "SKILL.md"))
        md_aspects = post.metadata.get("aspect_coverage", [])
        for aspect in spec["aspect_coverage"]:
            assert aspect in md_aspects, \
                f"{skill_name}: expected aspect '{aspect}' not in SKILL.md aspect_coverage {md_aspects}"

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_md_has_analysis_category(self, skill_name):
        import frontmatter
        spec = SKILL_SPECS[skill_name]
        post = frontmatter.load(str(spec["dir"] / "SKILL.md"))
        assert "analysis" in post.metadata.get("categories", []), \
            f"{skill_name}: expected 'analysis' in categories"


class TestAnalysisSkillReExport:
    """Each skill.py re-export wrapper works correctly"""

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_re_export(self, skill_name):
        spec = SKILL_SPECS[skill_name]
        module_path = f"src.skills.{skill_name}.skill"
        original_path = f"src.skills.analysis.{spec['module']}"
        mod = __import__(module_path, fromlist=[spec["class_name"]])
        orig_mod = __import__(original_path, fromlist=[spec["class_name"]])
        re_exported = getattr(mod, spec["class_name"])
        original = getattr(orig_mod, spec["class_name"])
        assert re_exported is original, \
            f"{skill_name}: re-exported class is not the same as original"


class TestAnalysisSkillDiscovery:
    """SkillDiscovery finds all 6 analysis skills"""

    def test_discovery_finds_all_six(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(SKILLS_DIR)
        names = [m.name for m in manifests]
        for skill_name in SKILL_SPECS.keys():
            assert skill_name in names, f"{skill_name} not discovered, found: {names}"


class TestAnalysisAspectSkillMapParity:
    """
    Critical parity test: for each skill, verify that for every aspect in its
    aspect_coverage, the skill appears in ManifestStrategyBuilder's
    build_aspect_skill_map()[aspect]. And for every aspect in ASPECT_SKILL_MAP
    that lists this skill, the skill also appears in the manifest-built map.
    """

    @pytest.fixture(autouse=True)
    def setup_registries(self):
        from src.skills.discovery import SkillDiscovery
        from src.core.decomposition.strategies import ASPECT_SKILL_MAP
        d = SkillDiscovery()
        manifests = d.discover_all(SKILLS_DIR)
        registries = d.build_registries(manifests)
        self.manifest_aspect_map = registries.aspect_skill_map
        self.hardcoded_aspect_map = ASPECT_SKILL_MAP

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_manifest_covers_all_skill_aspects(self, skill_name):
        """Every aspect in skill's aspect_coverage should have the skill in manifest map"""
        spec = SKILL_SPECS[skill_name]
        for aspect in spec["aspect_coverage"]:
            assert aspect in self.manifest_aspect_map, \
                f"Aspect '{aspect}' not in manifest_aspect_map at all"
            assert skill_name in self.manifest_aspect_map[aspect], \
                f"Skill '{skill_name}' not in manifest_aspect_map['{aspect}'], got: {self.manifest_aspect_map[aspect]}"

    @pytest.mark.parametrize("skill_name", list(SKILL_SPECS.keys()))
    def test_hardcoded_aspects_covered_by_manifest(self, skill_name):
        """Every aspect in ASPECT_SKILL_MAP that lists this skill should also have it in manifest map"""
        for aspect, skills in self.hardcoded_aspect_map.items():
            if skill_name in skills:
                assert aspect in self.manifest_aspect_map, \
                    f"ASPECT_SKILL_MAP['{aspect}'] lists '{skill_name}' but manifest map has no entry for '{aspect}'"
                assert skill_name in self.manifest_aspect_map[aspect], \
                    f"ASPECT_SKILL_MAP['{aspect}'] lists '{skill_name}' but manifest map has: {self.manifest_aspect_map[aspect]}"
