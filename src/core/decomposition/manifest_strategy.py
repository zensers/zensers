"""
ManifestStrategyBuilder - 从 SkillManifest 动态构建策略映射，替代 strategies.py 中的硬编码 dict。

内部复用 SkillRegistries 的构建结果，额外提供业务方法。
"""
import re
from typing import Any, Dict, List, Optional

from src.skills.discovery import SkillDiscovery, SkillManifest


class ManifestStrategyBuilder:
    """从 SkillManifest 动态构建策略映射，替代 strategies.py 中的硬编码 dict。

    内部复用 SkillRegistries 的构建结果，额外提供业务方法。
    """

    def __init__(self, manifests: Dict[str, SkillManifest]):
        self._manifests = manifests
        discovery = SkillDiscovery()
        self._registries = discovery.build_registries(list(manifests.values()))

    def build_aspect_skill_map(self) -> Dict[str, List[str]]:
        """替代 ASPECT_SKILL_MAP"""
        return self._registries.aspect_skill_map

    def build_skill_priority_map(self) -> Dict[str, str]:
        """替代 SKILL_PRIORITY_MAP"""
        return self._registries.priority_map

    def build_data_source_skill_map(self) -> Dict[str, List[str]]:
        """替代 DATA_SOURCE_SKILL_MAP"""
        return self._registries.data_source_skill_map

    def build_structured_data_capabilities(self) -> Dict[str, Dict[str, List[str]]]:
        """替代 STRUCTURED_DATA_CAPABILITIES"""
        return self._registries.structured_data_capabilities

    def build_action_to_skill_map(self) -> Dict[str, Optional[str]]:
        """替代 generic_agent.py 中的 ACTION_TO_SKILL。
        从 manifest.capabilities 反向构建 action→skill 映射。
        LLM 内在能力映射为 None。

        ⚠️ capabilities_map 的覆盖问题：discovery.py:_build_capabilities_map()
        中，当多个 Skill 有相同 capability 时，后遍历的会覆盖先遍历的。
        例如 search_skill 和 news_search 都有 capability "search"，
        遍历顺序取决于 sorted(dir.iterdir())，news_search 会覆盖 search_skill。
        因此显式覆盖（下面的 result["search"] = "search_skill"）是必需的，
        不能依赖 capabilities_map 的自动构建。"""
        intrinsic_actions = {
            "llm": None, "analyze": None, "analysis": None,
            "reasoning": None, "summarize": None, "translate": None,
            "research": None, "data_collection": None,
            "calibration": None, "execute": None,
        }
        result = dict(intrinsic_actions)
        for cap, skill_name in self._registries.capabilities_map.items():
            if cap not in result:
                result[cap] = skill_name
        result["search"] = "search_skill"
        result["news_search"] = "news_search"
        result["file_operation"] = "file_skill"
        result["http_request"] = "http_skill"
        result["generate_docx"] = "docx_skill"
        result["generate_pptx"] = "pptx_skill"
        result["web_search"] = "lc_tavily_search"
        result["tavily_search"] = "lc_tavily_search"
        result["academic_search"] = "lc_arxiv"
        result["arxiv_search"] = "lc_arxiv"
        result["wiki_search"] = "lc_wikipedia"
        result["wikipedia_search"] = "lc_wikipedia"
        result["data_analysis"] = "lc_python_repl"
        result["python_repl"] = "lc_python_repl"
        return result

    def get_skills_for_aspect(self, aspect: str) -> List[str]:
        """替代 get_skills_for_aspect()"""
        aspect_map = self.build_aspect_skill_map()
        if aspect in aspect_map:
            return aspect_map[aspect]
        for key, skills in aspect_map.items():
            if key in aspect:
                return skills
        return []

    def get_data_collection_skills(self, aspect: str, topic: str = "",
                                    intent_result: Any = None) -> List[str]:
        """替代 _get_data_collection_skills()"""
        db_skills = []
        web_skills = []
        base_skills = ["search_skill", "news_search"]
        aspect_skills = []
        ds_map = self.build_data_source_skill_map()
        priority_map = self.build_skill_priority_map()
        aspect_lower = aspect.lower()
        for keyword, extra_skills in ds_map.items():
            if self._aspect_keyword_matches(keyword, aspect_lower):
                aspect_skills.extend(extra_skills)
        if intent_result:
            primary_type = getattr(intent_result, 'primary_research_type', None)
            if primary_type and getattr(primary_type, 'value', '') in (
                "company_research", "investment", "competitive_analysis",
                "industry_research", "brand_research",
            ):
                for name, m in self._manifests.items():
                    # Competitive landscape is a web/market-source task;
                    # company financial APIs are not automatically relevant.
                    if primary_type.value == "competitive_analysis" and name == "stock_data":
                        continue
                    if m.priority == "structured_db" and name not in aspect_skills:
                        aspect_skills.append(name)
        all_unique = list(dict.fromkeys(aspect_skills + base_skills))
        for skill in all_unique:
            tier = priority_map.get(skill, "web_search")
            if tier == "structured_db":
                db_skills.append(skill)
            else:
                web_skills.append(skill)
        return db_skills + web_skills

    @staticmethod
    def _aspect_keyword_matches(keyword: str, aspect_lower: str) -> bool:
        if keyword.isascii() and any(char.isalpha() for char in keyword):
            return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", aspect_lower) is not None
        return keyword in aspect_lower
