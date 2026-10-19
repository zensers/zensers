"""
Skill 自描述架构 - 自动发现引擎

从 SKILL.md (YAML front matter + Markdown body) 解析 skill 元数据，
自动构建全链路注册数据，消灭手动触点。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type, Any

import frontmatter

from .base import Skill

import logging

logger = logging.getLogger(__name__)


@dataclass
class ActionRule:
    pattern: str
    actions: List[str]
    aspect_keywords: Optional[List[str]] = None


@dataclass
class SkillManifest:
    name: str
    description: str
    version: str
    categories: List[str]
    priority: str
    keywords: List[str]
    aliases: List[str]
    capabilities: List[str]
    data_types: Dict[str, List[str]]
    data_source_keywords: List[str]
    action_rules: List[ActionRule]
    action_param_map: Dict[str, Dict[str, str]]
    supports_topic_fallback: bool
    topic_fallback_pattern: Optional[str]
    is_intrinsic: bool
    aspect_coverage: List[str]
    skill_type: str
    skill_dir: Path
    has_code: bool
    instructions: str


@dataclass
class SkillRegistries:
    category_to_skills: Dict[str, List[str]]
    priority_map: Dict[str, str]
    keywords_map: Dict[str, set]
    alias_map: Dict[str, str]
    capabilities_map: Dict[str, str]
    data_source_skill_map: Dict[str, List[str]]
    structured_data_capabilities: Dict[str, Dict[str, List[str]]]
    aspect_skill_map: Dict[str, List[str]]


class SkillDiscovery:
    def discover_all(self, skills_dir: Path) -> List[SkillManifest]:
        manifests = []
        if not skills_dir.is_dir():
            return manifests
        for skill_dir in sorted(skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                continue
            try:
                manifest = self._parse_skill_md(skill_md)
                manifest.skill_dir = skill_dir
                manifest.has_code = (skill_dir / "skill.py").exists()
                manifests.append(manifest)
            except Exception as e:
                logger.warning(f"Failed to parse {skill_md}: {e}")
        return manifests

    def _parse_skill_md(self, path: Path) -> SkillManifest:
        post = frontmatter.load(str(path))
        meta = post.metadata
        body = post.content

        action_rules = []
        for rule_data in meta.get("action_rules", []):
            action_rules.append(ActionRule(
                pattern=rule_data["pattern"],
                actions=rule_data["actions"],
                aspect_keywords=rule_data.get("aspect_keywords"),
            ))

        return SkillManifest(
            name=meta["name"],
            description=meta["description"],
            version=str(meta.get("version", "1.0")),
            categories=meta.get("categories", []),
            priority=meta.get("priority", "web_search"),
            keywords=meta.get("keywords", []),
            aliases=meta.get("aliases", []),
            capabilities=meta.get("capabilities", []),
            data_types=meta.get("data_types", {}),
            data_source_keywords=meta.get("data_source_keywords", []),
            action_rules=action_rules,
            action_param_map=meta.get("action_param_map", {}),
            supports_topic_fallback=meta.get("supports_topic_fallback", False),
            topic_fallback_pattern=meta.get("topic_fallback_pattern"),
            is_intrinsic=meta.get("is_intrinsic", False),
            aspect_coverage=meta.get("aspect_coverage", []),
            skill_type=meta.get("skill_type", "standard"),
            skill_dir=Path(),
            has_code=False,
            instructions=body,
        )

    def load_skill_class(self, manifest: SkillManifest) -> Optional[Type[Skill]]:
        if not manifest.has_code:
            return None
        skill_py = manifest.skill_dir / "skill.py"
        if not skill_py.exists():
            return None

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"skills.{manifest.name}.skill",
            str(skill_py),
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning(f"Failed to load {skill_py}: {e}")
            return None

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Skill)
                and attr is not Skill
            ):
                return attr
        return None

    def build_registries(self, manifests: List[SkillManifest]) -> SkillRegistries:
        return SkillRegistries(
            category_to_skills=self._build_category_map(manifests),
            priority_map=self._build_priority_map(manifests),
            keywords_map=self._build_keywords_map(manifests),
            alias_map=self._build_alias_map(manifests),
            capabilities_map=self._build_capabilities_map(manifests),
            data_source_skill_map=self._build_data_source_skill_map(manifests),
            structured_data_capabilities=self._build_structured_data_capabilities(manifests),
            aspect_skill_map=self._build_aspect_skill_map(manifests),
        )

    def _build_category_map(self, manifests: List[SkillManifest]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for m in manifests:
            for cat in m.categories:
                result.setdefault(cat, [])
                if m.name not in result[cat]:
                    result[cat].append(m.name)
        return result

    def _build_priority_map(self, manifests: List[SkillManifest]) -> Dict[str, str]:
        return {m.name: m.priority for m in manifests}

    def _build_keywords_map(self, manifests: List[SkillManifest]) -> Dict[str, set]:
        return {m.name: set(m.keywords) for m in manifests}

    def _build_alias_map(self, manifests: List[SkillManifest]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for m in manifests:
            for alias in m.aliases:
                result[alias] = m.name
        return result

    def _build_capabilities_map(self, manifests: List[SkillManifest]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for m in manifests:
            for cap in m.capabilities:
                result[cap] = m.name
        return result

    def _build_data_source_skill_map(self, manifests: List[SkillManifest]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for m in manifests:
            for keyword in m.data_source_keywords:
                result.setdefault(keyword, [])
                if m.name not in result[keyword]:
                    result[keyword].append(m.name)
        return result

    def _build_structured_data_capabilities(self, manifests: List[SkillManifest]) -> Dict[str, Dict[str, List[str]]]:
        return {
            m.name: m.data_types
            for m in manifests
            if m.data_types and m.priority == "structured_db"
        }

    def _build_aspect_skill_map(self, manifests: List[SkillManifest]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for m in manifests:
            for aspect in m.aspect_coverage:
                result.setdefault(aspect, [])
                if m.name not in result[aspect]:
                    result[aspect].append(m.name)
        return result
