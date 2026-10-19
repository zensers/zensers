# -*- coding: utf-8 -*-
"""
Task Decomposition Strategy - Professional Research Process

Design Principles:
1. Professionalism First - Follow industry research methodology
2. Quality Oriented - Ensure high-quality output at each stage
3. Flexible Extension - Support differentiation for different research types

Core Research Methodology:
- Data Collection → Data Validation → Deep Analysis → Synthesis → Report Generation
- Quality control checkpoints at each stage
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import logging
import re

# Import PromptManager for external prompt loading
from ..prompt_manager import PromptManager

# Language consistency: instruction to enforce output language
from src.core.i18n import get_language_instruction

logger = logging.getLogger(__name__)

_manifest_strategy: Optional['ManifestStrategyBuilder'] = None


def set_manifest_strategy(builder: 'ManifestStrategyBuilder') -> None:
    global _manifest_strategy
    if _manifest_strategy is not None and builder is not None:
        logger.warning("set_manifest_strategy() called with builder already set; replacing")
    _manifest_strategy = builder


class ResearchPhase(Enum):
    """Research phase - follows professional research methodology"""
    DATA_COLLECTION = "data_collection"      # Data collection
    DATA_VALIDATION = "data_validation"      # Data validation
    DEEP_ANALYSIS = "deep_analysis"          # Deep analysis
    SYNTHESIS = "synthesis"                  # Synthesis
    REPORT_GENERATION = "report_generation"  # Report generation
    CALIBRATION = "calibration"              # Cross-agent numeric calibration


# Dynamically assign Skills by research dimension, avoid all Agents carrying irrelevant skills
# v2: All analysis agents now include search_skill for on-demand model/data lookup
ASPECT_SKILL_MAP = {
    "Market Size": ["data_analysis", "search_skill", "lc_python_repl"],
    "Market Share": ["data_analysis", "search_skill", "lc_python_repl"],
    "Competitive Landscape": ["market_analysis", "search_skill"],
    "Industry Trends": ["data_analysis", "search_skill"],
    "Development Trends": ["data_analysis", "search_skill"],
    "Financial Analysis": ["stock_analysis", "data_analysis", "search_skill"],
    "Valuation Analysis": ["stock_analysis", "data_analysis", "search_skill"],
    "Company Analysis": ["stock_analysis", "market_analysis", "search_skill"],
    "Policy Environment": ["policy_analysis", "search_skill"],
    "Technology Trends": ["tech_trend", "search_skill"],
    "Industry Chain": ["market_analysis", "search_skill"],
    "Risk Analysis": ["risk_analysis", "search_skill"],
    "Investment Advice": ["stock_analysis", "data_analysis", "search_skill"],
    "User Analysis": ["data_analysis", "search_skill", "lc_python_repl"],
    "Regional Distribution": ["data_analysis", "search_skill"],
    "Growth Analysis": ["data_analysis", "search_skill"],
    "Sales Analysis": ["data_analysis", "search_skill", "lc_python_repl"],
    "Data Comparison": ["data_analysis", "search_skill", "lc_python_repl"],
    "Executive Summary": ["search_skill"],
    "Research Conclusion": ["search_skill"],
    "Data Validation": [],
    "Comprehensive Analysis": ["search_skill"],
    "Strategic Intent": ["market_analysis", "search_skill"],
    "战略意图": ["market_analysis", "search_skill"],
    "战略意图推断": ["market_analysis", "search_skill"],
}

DEFAULT_ASPECT_SKILLS = []


def get_skills_for_aspect(aspect: str) -> List[str]:
    """
    Return required Skills list based on research dimension
    
    Args:
        aspect: Research dimension name
        
    Returns:
        Applicable Skills list
    """
    if _manifest_strategy:
        return _manifest_strategy.get_skills_for_aspect(aspect)
    # Exact match
    if aspect in ASPECT_SKILL_MAP:
        return ASPECT_SKILL_MAP[aspect]
    
    # Contains match
    for key, skills in ASPECT_SKILL_MAP.items():
        if key in aspect:
            return skills
    
    # Default: no search_skill (DEEP_ANALYSIS agents use pre-collected data)
    return DEFAULT_ASPECT_SKILLS.copy()


DATA_SOURCE_PRIORITY = {
    "structured_db": 100,
    "web_search": 50,
    "llm": 10,
}

SKILL_PRIORITY_MAP = {
    "stock_data": "structured_db",
    "wind_data": "structured_db",
    "bloomberg_data": "structured_db",
    "xueqiu": "structured_db",
    "search_skill": "web_search",
    "news_search": "web_search",
    "lc_tavily_search": "web_search",
    "lc_wikipedia": "web_search",
}

DATA_SOURCE_SKILL_MAP = {
    "financial": ["stock_data", "xueqiu"],
    "valuation": ["stock_data", "xueqiu"],
    "company": ["stock_data", "xueqiu"],
    "market_size": ["stock_data", "xueqiu"],
    "competitive": ["xueqiu"],
    "policy": [],
    "technology": [],
    "risk": [],
    "财务": ["stock_data", "xueqiu"],
    "估值": ["stock_data", "xueqiu"],
    "公司": ["stock_data", "xueqiu"],
    "盈利": ["stock_data", "xueqiu"],
    "营收": ["stock_data", "xueqiu"],
    "市值": ["stock_data", "xueqiu"],
    "市场规模": ["stock_data", "xueqiu"],
    "利润": ["stock_data", "xueqiu"],
    "资产负债": ["stock_data"],
    "roe": ["stock_data", "xueqiu"],
    "pe": ["stock_data", "xueqiu"],
    "pb": ["stock_data", "xueqiu"],
    "增长": ["stock_data", "xueqiu"],
    "投资": ["stock_data", "xueqiu"],
    "行情": ["xueqiu"],
    "热门": ["xueqiu"],
    "港股": ["xueqiu"],
    "美股": ["xueqiu"],
    "趋势": ["xueqiu"],
    "竞争": ["xueqiu"],
}


def _aspect_keyword_matches(keyword: str, aspect_lower: str) -> bool:
    """Match English metric tokens without substring false positives."""
    if keyword.isascii() and any(char.isalpha() for char in keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", aspect_lower) is not None
    return keyword in aspect_lower


def _get_data_collection_skills(aspect: str, topic: str = "", intent_result: Any = None) -> List[str]:
    if _manifest_strategy:
        return _manifest_strategy.get_data_collection_skills(aspect, topic, intent_result)
    db_skills: List[str] = []
    web_skills: List[str] = []

    base_skills = ["search_skill", "news_search"]
    aspect_skills: List[str] = []
    aspect_lower = aspect.lower()
    for keyword, extra_skills in DATA_SOURCE_SKILL_MAP.items():
        if _aspect_keyword_matches(keyword, aspect_lower):
            aspect_skills.extend(extra_skills)
    if intent_result:
        primary_type = getattr(intent_result, 'primary_research_type', None)
        if primary_type and getattr(primary_type, 'value', '') in (
            "company_research", "investment", "competitive_analysis",
            "industry_research", "brand_research",
        ):
            if primary_type.value != "competitive_analysis" and "stock_data" not in aspect_skills:
                aspect_skills.append("stock_data")
            if "xueqiu" not in aspect_skills:
                aspect_skills.append("xueqiu")

    all_unique = list(dict.fromkeys(aspect_skills + base_skills))
    for skill in all_unique:
        tier = SKILL_PRIORITY_MAP.get(skill, "web_search")
        if tier == "structured_db":
            db_skills.append(skill)
        else:
            web_skills.append(skill)
    return db_skills + web_skills


@dataclass
class SubSectionSpec:
    sub_section_id: str
    name: str
    data_needs: List[str]
    data_source_type: str = "search"


@dataclass
class SectionDataSpec:
    section_id: str
    name: str
    sub_sections: List[SubSectionSpec] = field(default_factory=list)

    @property
    def all_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))

    @property
    def search_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("search", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))

    @property
    def structured_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("structured", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))


STRUCTURED_DATA_CAPABILITIES = {
    "stock_data": {
        "zh": ["营收", "净利润", "毛利率", "净利率", "ROE", "ROA", "ROIC",
               "资产负债率", "流动比率", "速动比率", "现金流", "研发费用",
               "销量", "产量", "市场份额", "PE", "PB", "利润表", "资产负债表", "现金流量表"],
    },
    "xueqiu": {
        "zh": ["换手率", "市盈率", "实时行情", "当前价", "涨跌幅", "成交量",
               "成交额", "市值", "PE_TTM", "K线", "行情", "热门股票",
               "人气排行", "关注排行", "热帖"],
    },
}


def _is_listed_company_topic(topic: str) -> bool:
    if not topic:
        return False
    try:
        from src.core.intent.keyword_registry import get_registry
        return get_registry().is_listed_company_topic(topic)
    except Exception:
        company_indicators = ["公司", "集团", "股份", "有限", "比亚迪", "腾讯", "阿里巴巴",
                              "华为", "茅台", "宁德", "万科", "字节"]
        return any(ind in topic for ind in company_indicators)


def derive_data_source_type(data_need: str, topic: str = "", intent_result: Any = None) -> str:
    for skill_name, capabilities in STRUCTURED_DATA_CAPABILITIES.items():
        for lang, keywords in capabilities.items():
            if data_need in keywords:
                return "structured"
    if _is_listed_company_topic(topic):
        FINANCIAL_KEYWORDS = ["营收", "利润", "率", "费用", "ROE", "ROA", "ROIC", "PE", "PB", "DCF"]
        if any(kw in data_need for kw in FINANCIAL_KEYWORDS):
            return "both"
    return "search"


def validate_section_data_specs(
    specs: List[SectionDataSpec],
    section_names: List[str],
) -> Tuple[List[SectionDataSpec], bool]:
    import re
    valid = True
    for spec in specs:
        if not re.match(r'section_\d+', spec.section_id):
            valid = False
        if not spec.all_data_needs:
            valid = False
    if len(specs) != len(section_names):
        valid = False
    if not valid:
        specs = _fallback_specs_from_names(section_names)
    return specs, valid


def _fallback_specs_from_names(section_names: List[str]) -> List[SectionDataSpec]:
    specs = []
    for i, name in enumerate(section_names):
        specs.append(SectionDataSpec(
            section_id=f"section_{i}",
            name=name,
            sub_sections=[SubSectionSpec(
                sub_section_id=f"sub_{i}_0",
                name=name,
                data_needs=[name],
                data_source_type="search",
            )],
        ))
    return specs


def _convert_specs_from_dicts(spec_dicts: List[Dict]) -> List[SectionDataSpec]:
    specs = []
    for i, sd in enumerate(spec_dicts):
        if not isinstance(sd, dict):
            continue
        sub_sections = []
        for j, sub in enumerate(sd.get("sub_sections", [])):
            if not isinstance(sub, dict):
                continue
            sub_sections.append(SubSectionSpec(
                sub_section_id=sub.get("sub_section_id", f"sub_{i}_{j}"),
                name=sub.get("name", ""),
                data_needs=sub.get("data_needs", []),
                data_source_type=sub.get("data_source_type", "search"),
            ))
        specs.append(SectionDataSpec(
            section_id=sd.get("section_id", f"section_{i}"),
            name=sd.get("name", ""),
            sub_sections=sub_sections if sub_sections else [
                SubSectionSpec(f"sub_{i}_0", sd.get("name", ""), [sd.get("name", "")], "search")
            ],
        ))
    return specs


def _specs_from_framework_tree(
    section_tree: List[Dict],
    aspect_names: List[str],
) -> List[SectionDataSpec]:
    """Rebuild data specs from the confirmed framework when LLM specs are absent."""
    tree = [item for item in (section_tree or []) if isinstance(item, dict)]
    unused = list(tree)
    specs: List[SectionDataSpec] = []

    def _name(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("zh") or value.get("en") or next(iter(value.values()), ""))
        return str(value or "")

    for index, aspect in enumerate(aspect_names or []):
        requested = _name(aspect).strip()
        match_index = -1
        for candidate_index, candidate in enumerate(unused):
            candidate_name = _name(candidate.get("name") or candidate.get("title") or candidate.get("id"))
            candidate_id = str(candidate.get("section_id") or candidate.get("id") or "")
            if requested == candidate_name or requested == candidate_id:
                match_index = candidate_index
                break
        raw = unused.pop(match_index) if match_index >= 0 else {}
        sub_specs: List[SubSectionSpec] = []
        for sub_index, sub in enumerate(raw.get("sub_sections", []) or []):
            if not isinstance(sub, dict):
                continue
            sub_name = _name(sub.get("name") or sub.get("title") or sub.get("id")).strip()
            if not sub_name:
                continue
            raw_needs = sub.get("data_needs") or sub.get("required_metrics") or sub.get("points") or []
            if isinstance(raw_needs, str):
                raw_needs = [raw_needs]
            needs = [str(item).strip() for item in raw_needs if str(item).strip()]
            if not needs:
                needs = [sub_name]
            sub_specs.append(SubSectionSpec(
                sub_section_id=str(sub.get("sub_section_id") or sub.get("id") or f"sub_{index}_{sub_index}"),
                name=sub_name,
                data_needs=list(dict.fromkeys(needs)),
                data_source_type=str(sub.get("data_source_type") or "search"),
            ))

        if not sub_specs:
            sub_specs = [SubSectionSpec(
                sub_section_id=f"sub_{index}_0",
                name=requested,
                data_needs=[requested],
                data_source_type="search",
            )]
        specs.append(SectionDataSpec(
            # The caller passes only data-bearing aspects, so this positional
            # ID is the canonical identity used by IndustryResearchStrategy.
            # Template IDs are metadata and must not leak into execution IDs.
            section_id=f"section_{index}",
            name=requested,
            sub_sections=sub_specs,
        ))
    return specs


@dataclass
class AgentSpec:
    """Agent specification definition"""
    agent_id: str
    agent_type: str                    # research, analysis, synthesis, report
    category: str                      # data-collection, market-analysis, etc.
    task_description: str
    input_keys: List[str] = field(default_factory=list)
    output_keys: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    priority: int = 0
    parallel_group: int = 0
    quality_threshold: float = 0.7
    max_retries: int = 3
    skills: List[str] = field(default_factory=list)
    mcp_tools: List[str] = field(default_factory=list)      # MCP tools assigned to this agent
    system_prompt: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecompositionPlan:
    """Task decomposition plan"""
    task_id: str
    phases: Dict[ResearchPhase, List[AgentSpec]]
    execution_order: List[ResearchPhase]
    quality_gates: Dict[ResearchPhase, float]
    estimated_agents: int
    estimated_duration: str
    section_data_specs: List[SectionDataSpec] = field(default_factory=list)
    # Immutable-at-execution-boundary list of every reportable leaf section.
    # Agent results must join this list by section_id; display names are not
    # identities.
    section_manifest: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_agents_for_phase(self, phase: ResearchPhase) -> List[AgentSpec]:
        """Get Agent list for specified phase"""
        return self.phases.get(phase, [])
    
    def get_total_agents(self) -> int:
        """Get total Agent count"""
        return sum(len(agents) for agents in self.phases.values())

    def get_manifest_ids(self) -> List[str]:
        return [str(item.get("section_id", "")) for item in self.section_manifest if item.get("section_id")]


class TaskDecompositionStrategy(ABC):
    """
    Base task decomposition strategy
    
    All research types must follow professional research methodology:
    1. Data collection phase - systematic multi-source data collection
    2. Data validation phase - cross-validate data quality
    3. Deep analysis phase - apply professional analysis frameworks
    4. Synthesis phase - integrate multi-dimensional insights
    5. Report generation phase - produce professional reports
    """
    
    # Research phase order - fixed professional workflow
    PHASE_ORDER = [
        ResearchPhase.DATA_COLLECTION,
        ResearchPhase.DATA_VALIDATION,
        ResearchPhase.DEEP_ANALYSIS,
        ResearchPhase.SYNTHESIS,
        ResearchPhase.REPORT_GENERATION,
    ]
    
    @abstractmethod
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """
        Decompose task into Agent execution plan
        
        Args:
            requirement: Research requirement
            intent_result: Intent analysis result
            framework_config: Framework config
            
        Returns:
            DecompositionPlan: Task decomposition plan
        """
        pass
    
    def _create_agent_id(self, phase: ResearchPhase, index: int, suffix: str = "") -> str:
        """Create standardized Agent ID"""
        base = f"{phase.value}_{index}"
        if suffix:
            base = f"{base}_{suffix}"
        return base
    
    def _determine_complexity_params(
        self, 
        complexity: str,
        aspects_count: int
    ) -> Dict[str, Any]:
        """
        Determine parameters based on complexity
        
        Returns:
            Contains max_agents_per_aspect, max_results_per_agent, etc.
        """
        params = {
            "trivial": {
                "max_agents_per_aspect": 1,
                "max_results_per_agent": 5,
                "max_retries": 2,
            },
            "single": {
                "max_agents_per_aspect": 1,
                "max_results_per_agent": 10,
                "max_retries": 3,
            },
            "multi": {
                "max_agents_per_aspect": 1,
                "max_results_per_agent": 15,
                "max_retries": 3,
            },
            "complex": {
                "max_agents_per_aspect": 2,
                "max_results_per_agent": 20,
                "max_retries": 3,
            },
        }
        return params.get(complexity, params["multi"])


class IndustryResearchStrategy(TaskDecompositionStrategy):
    """
    Industry Research Strategy - Most professional research type
    
    Follows professional industry research methodology:
    1. Comprehensive data collection (multi-source, multi-dimension)
    2. Data cross-validation (ensure accuracy)
    3. Framework analysis (PEST, Porter's Five Forces, SWOT, etc.)
    4. Comprehensive judgment (integrate all dimensions)
    5. Professional report output
    """
    
    # Dependent section definition (summary and conclusion wait for other sections)
    # **Extended definition**: includes all synthesis section name variants
    DEPENDENT_SECTIONS = {
        # English
        "summary", "conclusion", "executive_summary", "key_insights",
        "research_summary", "research_conclusion", "synthesis",
        "key_findings", "insights",
        # Chinese
        "synthesis_analysis", "core_findings", "key_discoveries",
        "执行摘要", "摘要", "结论",
        # Strategic Intent (dependent on all analysis)
        "strategic_intent", "strategic intent",
        "战略意图", "战略意图推断",
    }

    @staticmethod
    def _build_execution_units(
        normal_aspects: List[Tuple[int, str]],
        section_spec_by_name: Dict[str, SectionDataSpec],
        template_sub_sections_by_aspect: Dict[str, List[Any]],
    ) -> List[Dict[str, Any]]:
        """Expand data-bearing aspects into stable leaf execution units.

        A parent section is a presentation concept; collection/validation/
        analysis need a concrete unit for every required subsection.  Keeping
        the parent when no subsection exists preserves compatibility with old
        plans, while a real subsection gets the canonical ``parent::sub`` ID
        used by report-upgrade and coverage checks.
        """
        units: List[Dict[str, Any]] = []
        parent_position = 0
        for parent_index, parent_name in normal_aspects:
            parent_spec = section_spec_by_name.get(parent_name)
            raw_subs = list(parent_spec.sub_sections) if parent_spec else []
            if not raw_subs:
                raw_subs = template_sub_sections_by_aspect.get(parent_name, []) or []

            normalized_subs: List[Dict[str, Any]] = []
            for sub_index, raw_sub in enumerate(raw_subs):
                if isinstance(raw_sub, SubSectionSpec):
                    sub_id = str(raw_sub.sub_section_id or f"sub_{parent_index}_{sub_index}")
                    sub_name = str(raw_sub.name or "").strip()
                    data_needs = list(raw_sub.data_needs or [])
                    source_type = raw_sub.data_source_type
                elif isinstance(raw_sub, dict):
                    sub_id = str(raw_sub.get("sub_section_id") or raw_sub.get("id") or f"sub_{parent_index}_{sub_index}")
                    sub_name = str(raw_sub.get("name") or raw_sub.get("title") or "").strip()
                    data_needs = raw_sub.get("data_needs") or raw_sub.get("required_metrics") or raw_sub.get("points") or []
                    source_type = str(raw_sub.get("data_source_type") or "search")
                    if isinstance(data_needs, str):
                        data_needs = [data_needs]
                else:
                    continue
                if not sub_name:
                    continue
                needs = [str(item).strip() for item in data_needs if str(item).strip()]
                normalized_subs.append({
                    "sub_section_id": sub_id,
                    "name": sub_name,
                    "data_needs": list(dict.fromkeys(needs or [sub_name])),
                    "data_source_type": source_type,
                })

            if not normalized_subs:
                units.append({
                    "unit_index": len(units),
                    "parent_index": parent_index,
                    "parent_name": parent_name,
                    "name": parent_name,
                    "section_id": f"section_{parent_position}",
                    "parent_section_id": f"section_{parent_position}",
                    "sub_section_id": "",
                    "data_needs": [parent_name],
                    "data_source_type": "search",
                    "template_sub_sections": [],
                })
                parent_position += 1
                continue

            # Parent section IDs are assigned in data-bearing order, not the
            # original list index, because synthesis sections are excluded.
            parent_runtime_id = f"section_{parent_position}"
            for sub in normalized_subs:
                sub_id = sub["sub_section_id"]
                units.append({
                    "unit_index": len(units),
                    "parent_index": parent_index,
                    "parent_name": parent_name,
                    "name": sub["name"],
                    "section_id": f"{parent_runtime_id}::{sub_id}",
                    "parent_section_id": parent_runtime_id,
                    "sub_section_id": sub_id,
                    "data_needs": sub["data_needs"],
                    "data_source_type": sub["data_source_type"],
                    "template_sub_sections": [sub],
                })
            parent_position += 1
        return units
    
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """Execute industry research task decomposition"""
        
        phases: Dict[ResearchPhase, List[AgentSpec]] = {
            ResearchPhase.DATA_COLLECTION: [],
            ResearchPhase.DATA_VALIDATION: [],
            ResearchPhase.DEEP_ANALYSIS: [],
            ResearchPhase.SYNTHESIS: [],
            ResearchPhase.REPORT_GENERATION: [],
        }
        
        # Get parameters
        complexity = getattr(intent_result, 'complexity', None)
        complexity_value = complexity.value if complexity else "multi"
        complexity_params = self._determine_complexity_params(
            complexity_value, 
            len(requirement.aspects)
        )
        
        aspects = requirement.aspects
        topic = requirement.topic
        
        # [P0-4] Annual report mode: use dynamic analysis_framework
        annual_report_data = getattr(requirement, 'dynamic_fields', {}).get("annual_report_data", {}) if hasattr(requirement, 'dynamic_fields') else {}
        analysis_framework = annual_report_data.get("analysis_framework", {}) if annual_report_data else {}
        preloaded_data = getattr(requirement, 'dynamic_fields', {}).get("preloaded_data", False) if hasattr(requirement, 'dynamic_fields') else False
        
        if analysis_framework and analysis_framework.get("aspects"):
            framework_aspects = analysis_framework["aspects"]
            if not aspects or len(aspects) == 0:
                aspects = framework_aspects
        
        section_data_specs = getattr(intent_result, 'section_data_specs', []) or []
        if section_data_specs and isinstance(section_data_specs[0], dict):
            section_data_specs = _convert_specs_from_dicts(section_data_specs)

        # P0 alignment: override section_data_specs with framework_tree when available
        sections_tree = None
        section_details = getattr(requirement, 'section_details', []) or []
        if hasattr(requirement, 'dynamic_fields') and requirement.dynamic_fields and requirement.dynamic_fields.get('sections_tree'):
            sections_tree = requirement.dynamic_fields['sections_tree']
        elif section_details:
            for sd in section_details:
                sd_subs = sd.get("sub_sections", []) if hasattr(sd, 'get') else (sd.sub_sections if hasattr(sd, 'sub_sections') else [])
                if sd_subs:
                    sections_tree = section_details
                    break
        if sections_tree and section_data_specs:
            section_data_specs = self._align_section_data_specs_with_tree(section_data_specs, sections_tree)

        # Build template sub_sections lookup by aspect name
        template_sub_sections_by_aspect = {}
        if section_details:
            for sd in section_details:
                sd_name = sd.get("name", "") if hasattr(sd, 'get') else getattr(sd, 'name', "")
                if isinstance(sd_name, dict):
                    sd_name = sd_name.get("zh", sd_name.get("en", ""))
                sd_subs = sd.get("sub_sections", []) if hasattr(sd, 'get') else getattr(sd, 'sub_sections', [])
                if sd_name and sd_subs:
                    template_sub_sections_by_aspect[sd_name] = sd_subs
                    sd_id = sd.get("id", "") if hasattr(sd, 'get') else getattr(sd, 'id', "")
                    if sd_id:
                        template_sub_sections_by_aspect[sd_id] = sd_subs

        section_spec_by_id = {spec.section_id: spec for spec in section_data_specs} if section_data_specs else {}
        section_spec_by_name = {spec.name: spec for spec in section_data_specs} if section_data_specs else {}
        
        # Separate normal sections and dependent sections
        normal_aspects = []
        dependent_aspects = []
        for i, aspect in enumerate(aspects):
            if aspect.lower() in self.DEPENDENT_SECTIONS or any(ds in aspect for ds in self.DEPENDENT_SECTIONS):
                dependent_aspects.append((i, aspect))
            else:
                normal_aspects.append((i, aspect))

        # This is the canonical identity map for every data-bearing aspect.
        # Do not derive it later with list.index(): duplicate display names
        # are legal and must still receive deterministic, distinct IDs.
        normal_section_ids = {
            key: f"section_{seq_idx}"
            for seq_idx, key in enumerate(normal_aspects)
        }
        execution_units = self._build_execution_units(
            normal_aspects,
            section_spec_by_name,
            template_sub_sections_by_aspect,
        )

        if sections_tree and not section_data_specs:
            # Preserve framework-confirmed subsection metrics when the LLM
            # intentionally returned a compact response for a large task.
            # Only data-bearing aspects participate: synthesis sections have
            # no collection spec and must not shift section_N identities.
            section_data_specs = _specs_from_framework_tree(
                sections_tree,
                [aspect for _, aspect in normal_aspects],
            )
            # Rebuild lookup maps after reconstruction; the maps are consumed
            # by every collection and analysis AgentSpec below.
            section_spec_by_id = {spec.section_id: spec for spec in section_data_specs}
            section_spec_by_name = {spec.name: spec for spec in section_data_specs}
        
        # === Phase 1: Data Collection ===
        for unit in execution_units:
            i = unit["parent_index"]
            aspect = unit["name"]
            agent_index = unit["unit_index"]
            agent_suffix = aspect.lower().replace(" ", "_")
            agent_id = self._create_agent_id(ResearchPhase.DATA_COLLECTION, agent_index, agent_suffix)
            section_id = unit["section_id"]
            matched_spec = section_spec_by_id.get(section_id) or section_spec_by_name.get(aspect)
            template_subs = unit["template_sub_sections"]
            
            # [P0-4] Annual report mode: lightweight preloaded data delivery
            if preloaded_data:
                spec = AgentSpec(
                    agent_id=agent_id,
                    agent_type="research",
                    category="research",
                    task_description=f"Deliver preloaded annual report data for {aspect}",
                    input_keys=["topic", "aspect"],
                    output_keys=[f"data_{aspect}"],
                    dependencies=[],
                    priority=10 - i,
                    parallel_group=0,
                    quality_threshold=0.7,
                    max_retries=1,
                    skills=["annual_report_parser"],
                    system_prompt="Deliver preloaded annual report data.",
                    context={"aspect": aspect, "topic": topic,
                             "preloaded": True,
                             "section_id": section_id},
                )
            else:
                spec = AgentSpec(
                    agent_id=agent_id,
                    agent_type="research",
                    category="research",  # Maps to DATA_COLLECTION
                    task_description=f"Collect data for {topic} - {aspect}",
                    input_keys=["topic", "aspect"],
                    output_keys=[f"data_{aspect}"],
                    dependencies=[],
                    priority=10 - i,  # Priority by order
                    parallel_group=0,  # Same group runs in parallel
                    quality_threshold=0.7,
                    max_retries=complexity_params["max_retries"],
                    skills=_get_data_collection_skills(aspect, topic, intent_result),
                    system_prompt=self._build_data_collection_prompt(topic, aspect, framework_config, sub_aspects=self._resolve_sub_aspect_names(template_subs) or ([sub.name for sub in matched_spec.sub_sections] if matched_spec and matched_spec.sub_sections else None)),
                    context={"aspect": aspect, "topic": topic,
                             "section_id": section_id,
                             "data_needs": unit["data_needs"],
                             "search_data_needs": unit["data_needs"] if unit["data_source_type"] in ("search", "both") else [],
                             "sub_aspects": self._resolve_sub_aspect_names(template_subs),
                             "template_sub_sections": template_subs},
                )
            phases[ResearchPhase.DATA_COLLECTION].append(spec)
        
        # === Phase 2: Data Validation ===
        for unit in execution_units:
            i = unit["parent_index"]
            aspect = unit["name"]
            agent_index = unit["unit_index"]
            # Data validation agent depends on corresponding data collection agent
            agent_suffix = aspect.lower().replace(" ", "_")
            data_agent_id = self._create_agent_id(ResearchPhase.DATA_COLLECTION, agent_index, agent_suffix)
            agent_id = self._create_agent_id(ResearchPhase.DATA_VALIDATION, agent_index, agent_suffix)
            
            spec = AgentSpec(
                agent_id=agent_id,
                agent_type="validation",
                category="quality-check",
                task_description=f"Validate data accuracy and completeness for {aspect}",
                input_keys=[f"data_{aspect}"],
                output_keys=[f"validated_{aspect}"],
                dependencies=[data_agent_id],
                priority=10 - i,
                parallel_group=0,
                quality_threshold=0.8,
                max_retries=2,
                skills=[],
                system_prompt=self._build_validation_prompt(topic, aspect),
                # Preserve the same section identity across collection,
                # validation and analysis.  output_keys are storage keys and
                # must not be used as a substitute for this identity.
                context={"aspect": aspect, "topic": topic,
                         "section_id": unit["section_id"]},
            )
            phases[ResearchPhase.DATA_VALIDATION].append(spec)
        
        # === Phase 3: Deep Analysis ===
        for unit in execution_units:
            i = unit["parent_index"]
            aspect = unit["name"]
            agent_index = unit["unit_index"]
            agent_suffix = aspect.lower().replace(" ", "_")
            validation_agent_id = self._create_agent_id(ResearchPhase.DATA_VALIDATION, agent_index, agent_suffix)
            agent_id = self._create_agent_id(ResearchPhase.DEEP_ANALYSIS, agent_index, agent_suffix)
            da_matched_spec = section_spec_by_name.get(unit["parent_name"])
            da_template_subs = unit["template_sub_sections"]
            
            # [P0-4] Annual report mode: inject document_context from analysis_framework
            document_context = ""
            document_tables = []
            if annual_report_data:
                section_ids = analysis_framework.get("aspect_to_section_ids", {}).get(unit["parent_name"], [])
                aspect_to_profile = analysis_framework.get("aspect_to_profile", {})
                
                sections = annual_report_data.get("sections", [])
                context_parts = []
                for sid in section_ids:
                    if isinstance(sid, int) and 0 <= sid - 1 < len(sections):
                        section = sections[sid - 1]
                        content = section.get("content", "")
                        if content:
                            context_parts.append(content[:4000])
                
                if context_parts:
                    document_context = "\n\n".join(context_parts)
                
                profile = aspect_to_profile.get(aspect, "")
                if profile in ("financial_analysis", "valuation", "investment"):
                    financial_tables = annual_report_data.get("financial_tables", {})
                    if financial_tables:
                        document_tables = financial_tables
            
            agent_context = {"aspect": aspect, "topic": topic,
                     "section_id": unit["section_id"],
                     "sub_aspects": self._resolve_sub_aspect_names(da_template_subs),
                     "template_sub_sections": da_template_subs}
            if document_context:
                agent_context["document_context"] = document_context
            if document_tables:
                agent_context["document_tables"] = document_tables
            if annual_report_data and (document_context or document_tables):
                agent_context["has_preloaded_data"] = True
            
            spec = AgentSpec(
                agent_id=agent_id,
                agent_type="analysis",
                category="market-analysis",
                task_description=f"Deep analysis of {topic} - {aspect}",
                input_keys=[f"validated_{aspect}"],
                output_keys=[f"analysis_{aspect}"],
                dependencies=[validation_agent_id],
                priority=10 - i,
                parallel_group=0,
                quality_threshold=0.75,
                max_retries=complexity_params["max_retries"],
                skills=get_skills_for_aspect(aspect),
                system_prompt=self._build_analysis_prompt(topic, aspect, framework_config, sub_aspects=self._resolve_sub_aspect_names(da_template_subs) or ([sub.name for sub in da_matched_spec.sub_sections] if da_matched_spec and da_matched_spec.sub_sections else None), template_sub_sections=da_template_subs),
                context=agent_context,
            )
            phases[ResearchPhase.DEEP_ANALYSIS].append(spec)
        
        # === Phase 4: Synthesis ===
        # Synthesis of dependent sections
        all_analysis_agents = [
            self._create_agent_id(
                ResearchPhase.DEEP_ANALYSIS,
                unit["unit_index"],
                unit["name"].lower().replace(" ", "_"),
            )
            for unit in execution_units
        ]
        
        for synthesis_index, (i, aspect) in enumerate(dependent_aspects):
            agent_id = self._create_agent_id(ResearchPhase.SYNTHESIS, i, aspect.lower().replace(" ", "_"))
            
            spec = AgentSpec(
                agent_id=agent_id,
                agent_type="synthesis",
                category="synthesis",
                task_description=f"Synthesis analysis of {topic} - {aspect}",
                input_keys=[f"analysis_{a}" for _, a in normal_aspects],
                output_keys=[f"synthesis_{aspect}"],
                dependencies=all_analysis_agents,
                priority=5,
                parallel_group=1,
                quality_threshold=0.8,
                max_retries=2,
                skills=[],
                system_prompt=self._build_synthesis_prompt(topic, aspect),
                context={"aspect": aspect, "topic": topic, "is_dependent": True,
                         "section_id": f"synthesis_{synthesis_index}"},
            )
            phases[ResearchPhase.SYNTHESIS].append(spec)

        # Freeze the reportable chapter set before execution.  This is the
        # contract consumed by collection, analysis, report assembly and L0;
        # failed results remain visible against this list instead of making a
        # chapter disappear from the actual result set.
        section_manifest: List[Dict[str, Any]] = []
        for unit in execution_units:
            section_manifest.append({
                "section_id": unit["section_id"],
                "parent_section_id": unit["parent_section_id"],
                "sub_section_id": unit["sub_section_id"],
                "title": unit["name"],
                "role": "analysis",
                "required_topics": [unit["name"]],
                "required_metrics": list(unit["data_needs"]),
                "status": "pending",
                "producer_agent_ids": {
                    "data_collection": self._create_agent_id(
                        ResearchPhase.DATA_COLLECTION, unit["unit_index"],
                        unit["name"].lower().replace(" ", "_"),
                    ),
                    "validation": self._create_agent_id(
                        ResearchPhase.DATA_VALIDATION, unit["unit_index"],
                        unit["name"].lower().replace(" ", "_"),
                    ),
                    "analysis": self._create_agent_id(
                        ResearchPhase.DEEP_ANALYSIS, unit["unit_index"],
                        unit["name"].lower().replace(" ", "_"),
                    ),
                },
                "evidence_ids": [],
                "execution_order": len(section_manifest),
            })
        for synthesis_index, (i, aspect) in enumerate(dependent_aspects):
            aspect_lower = str(aspect or "").lower()
            if "摘要" in str(aspect) or "summary" in aspect_lower:
                output_slot = "exec_summary"
            elif "结论" in str(aspect) or "conclusion" in aspect_lower or "总结" in str(aspect):
                output_slot = "conclusion"
            else:
                output_slot = "body"
            section_manifest.append({
                "section_id": f"synthesis_{synthesis_index}",
                "parent_section_id": f"synthesis_{synthesis_index}",
                "sub_section_id": "",
                "title": aspect,
                "role": "synthesis",
                "output_slot": output_slot,
                "required_topics": [aspect],
                "required_metrics": [],
                "status": "pending",
                "producer_agent_ids": {
                    "synthesis": self._create_agent_id(
                        ResearchPhase.SYNTHESIS, i, aspect.lower().replace(" ", "_")
                    ),
                },
                "evidence_ids": [],
                "execution_order": len(section_manifest),
            })
        
        # === Phase 5: Report Generation ===
        all_agents = [
            self._create_agent_id(ResearchPhase.DEEP_ANALYSIS, i, a.lower().replace(" ", "_"))
            for i, a in normal_aspects
        ] + [
            self._create_agent_id(ResearchPhase.SYNTHESIS, i, a.lower().replace(" ", "_"))
            for i, a in dependent_aspects
        ]
        
        report_agent = AgentSpec(
            agent_id="report_generation_final",
            agent_type="report",
            category="report-generation",
            task_description=f"Generate research report for {topic}",
            input_keys=["all_analysis_results"],
            output_keys=["final_report"],
            dependencies=all_agents,
            priority=10,
            parallel_group=2,
            quality_threshold=0.8,
            max_retries=2,
            skills=["docx_skill"],
            system_prompt=self._build_report_prompt(topic, requirement),
            context={"topic": topic, "aspects": aspects,
                     "section_manifest": section_manifest},
        )
        phases[ResearchPhase.REPORT_GENERATION].append(report_agent)
        
        # Build quality gates
        quality_gates = {
            ResearchPhase.DATA_COLLECTION: 0.7,
            ResearchPhase.DATA_VALIDATION: 0.8,
            ResearchPhase.DEEP_ANALYSIS: 0.75,
            ResearchPhase.SYNTHESIS: 0.8,
            ResearchPhase.REPORT_GENERATION: 0.85,
        }
        
        return DecompositionPlan(
            task_id=f"research_{topic[:20]}",
            phases=phases,
            execution_order=self.PHASE_ORDER,
            quality_gates=quality_gates,
            estimated_agents=sum(len(agents) for agents in phases.values()),
            estimated_duration=self._estimate_duration(len(aspects), complexity_value),
            section_data_specs=section_data_specs,
            section_manifest=section_manifest,
        )
    
    def _build_data_collection_prompt(self, topic: str, aspect: str, framework_config: Any, sub_aspects: Optional[List[str]] = None) -> str:
        """Build data collection prompt from external file"""
        focus_areas = framework_config.get_focus_areas() if framework_config else []
        priority_sources = framework_config.get_priority_sources() if framework_config else []
        lang_inst = get_language_instruction()
        
        sub_aspects_section = ""
        if sub_aspects:
            from src.core.i18n import get_language, Language
            lang = get_language()
            if lang == Language.ZH:
                sub_aspects_section = "\n\n## 数据采集子主题\n请按以下子主题分别搜索数据：\n" + "\n".join(f"- {sa}" for sa in sub_aspects)
            else:
                sub_aspects_section = "\n\n## Sub-topics for Data Collection\nPlease collect data separately for each sub-topic:\n" + "\n".join(f"- {sa}" for sa in sub_aspects)
        
        try:
            pm = PromptManager()
            return pm.render(
                category="tasks",
                name="data_collection",
                strip_frontmatter=True,
                topic=topic,
                aspect=aspect,
                focus_areas="\n".join("- " + area for area in focus_areas[:5]) if focus_areas else "Comprehensive data collection",
                priority_sources="\n".join("- " + src for src in priority_sources[:8]) if priority_sources else "Prioritize authoritative data sources",
            ) + sub_aspects_section + '\n' + lang_inst
        except Exception as e:
            logger.warning(f"Failed to load data_collection.md, using fallback: {e}")
            focus_areas_str = "\n".join("- " + area for area in focus_areas[:5]) if focus_areas else "Comprehensive data collection"
            priority_sources_str = "\n".join("- " + src for src in priority_sources[:8]) if priority_sources else "Prioritize authoritative data sources"
            return f"""## Research Topic
{topic}

## Research Dimension
{aspect}

## Data Collection Focus
{focus_areas_str}

## Priority Data Sources
{priority_sources_str}
{sub_aspects_section}

## Collection Requirements
1. Multi-source data collection to ensure comprehensive coverage
2. Annotate each data source
3. Collect both quantitative data and qualitative information
4. Record data time range and geographic scope
{lang_inst}
"""

    def _build_validation_prompt(self, topic: str, aspect: str) -> str:
        """Build data validation prompt from external file"""
        try:
            pm = PromptManager()
            return pm.render(category="tasks", name="data_validation", strip_frontmatter=True, topic=topic, aspect=aspect)
        except Exception as e:
            logger.warning(f"Failed to load data_validation.md, using fallback: {e}")
            return f"""# Data Validation Task

## Research Topic
{topic}

## Research Dimension
{aspect}

## Validation Requirements
1. Check data accuracy and consistency
2. Cross-validate key data points (at least 2 sources)
3. Identify data gaps and uncertainties
4. Label data quality level
"""

    def _build_analysis_prompt(self, topic: str, aspect: str, framework_config: Any, sub_aspects: Optional[List[str]] = None, template_sub_sections: Optional[List] = None) -> str:
        """Build analysis prompt from external file"""
        depth = framework_config.get_analysis_depth() if framework_config else "deep"
        metrics = framework_config.get_key_metrics() if framework_config else []
        lang_inst = get_language_instruction()
        
        require_inline_citations = False
        if framework_config and hasattr(framework_config, 'requires_inline_citations'):
            require_inline_citations = framework_config.requires_inline_citations()
        
        if require_inline_citations:
            citation_instruction = """- Data must be annotated with sources (use [Source X] format, e.g., "2024 sales 12.8 million units [Source 15]")
- Each data point followed immediately by source annotation"""
        else:
            citation_instruction = """- **Strictly no source markers in text** (e.g., "【source:xxx】", "【source15】", "(source:xxx)" formats)
- Present data directly; sources will be listed in "Data Sources" section at report end
- Do not add any form of source explanation after data"""
        
        sub_aspects_section = ""
        if template_sub_sections:
            from src.core.i18n import get_language, Language
            lang = get_language()
            if lang == Language.ZH:
                sub_aspects_section = "\n\n## 输出结构要求（必须严格遵守）\n请按以下结构输出分析内容，每个子章节使用 ### 标题：\n"
            else:
                sub_aspects_section = "\n\n## Output Structure Requirements (MUST follow strictly)\nPlease structure your analysis with ### headings for each sub-section:\n"
            for sub in template_sub_sections:
                sub_name = sub.get("name", "") if hasattr(sub, 'get') else getattr(sub, 'name', "")
                if isinstance(sub_name, dict):
                    sub_name = sub_name.get("zh", sub_name.get("en", "")) if lang == Language.ZH else sub_name.get("en", sub_name.get("zh", ""))
                sub_aspects_section += f"### {sub_name}\n"
                for pt in (sub.get("points", []) if hasattr(sub, 'get') else getattr(sub, 'points', [])):
                    if isinstance(pt, dict):
                        pt_text = pt.get("zh", pt.get("en", "")) if lang == Language.ZH else pt.get("en", pt.get("zh", ""))
                    elif hasattr(pt, 'text'):
                        pt_text = pt.text
                    else:
                        pt_text = str(pt)
                    if pt_text:
                        sub_aspects_section += f"- {pt_text}\n"
        elif sub_aspects:
            from src.core.i18n import get_language, Language
            lang = get_language()
            if lang == Language.ZH:
                sub_aspects_section = "\n\n## 分析子主题（必须按此结构输出分析）\n请按以下子主题分别分析，每个子主题使用 ### 标题：\n" + "\n".join(f"### {sa}" for sa in sub_aspects)
            else:
                sub_aspects_section = "\n\n## Sub-topics (MUST structure your analysis accordingly)\nPlease analyze each sub-topic separately, using ### headings:\n" + "\n".join(f"### {sa}" for sa in sub_aspects)
        
        try:
            pm = PromptManager()
            return pm.render(
                category="tasks",
                name="deep_analysis",
                strip_frontmatter=True,
                topic=topic,
                aspect=aspect,
                metrics="\n".join("- " + m for m in metrics[:10]) if metrics else "Extract key metrics based on research content",
                citation_instruction=citation_instruction,
            ) + sub_aspects_section + '\n' + lang_inst
        except Exception as e:
            logger.warning(f"Failed to load deep_analysis.md, using fallback: {e}")
            return f"""# Deep Analysis Task

## Research Topic
{topic}

## Research Dimension
{aspect}
{sub_aspects_section}

## Analysis Requirements
Provide deep analysis meeting international consulting standards.

### Output Structure
1. Core Judgment statement
2. Logical derivation
3. Data support
4. Counter evidence

### Key Metrics
{chr(10).join('- ' + m for m in metrics[:10]) if metrics else 'Extract key metrics based on research content'}
{lang_inst}
"""

    def _align_section_data_specs_with_tree(self, section_data_specs, sections_tree):
        """Override section_data_specs sub_sections with framework_tree when available.

        Ensures sub-section names and data_needs match the user-confirmed framework.
        """
        if not sections_tree or not section_data_specs:
            return section_data_specs

        for tree_section in sections_tree:
            tree_name = tree_section.get('name', '') if isinstance(tree_section, dict) else ''
            if not tree_name:
                continue
            for spec in section_data_specs:
                if spec.name != tree_name:
                    continue
                tree_subs = tree_section.get('sub_sections', [])
                if not tree_subs:
                    continue
                for j, tree_sub in enumerate(tree_subs):
                    tree_sub_name = tree_sub.get('name', '') if isinstance(tree_sub, dict) else ''
                    if not tree_sub_name:
                        continue
                    tree_points = tree_sub.get('points', []) if isinstance(tree_sub, dict) else []
                    if j < len(spec.sub_sections):
                        spec.sub_sections[j].name = tree_sub_name
                        if tree_points:
                            spec.sub_sections[j].data_needs = tree_points
                    else:
                        spec.sub_sections.append(SubSectionSpec(
                            sub_section_id=f"sub_{spec.section_id}_{j}",
                            name=tree_sub_name,
                            data_needs=tree_points,
                            data_source_type="search"
                        ))
                break
        return section_data_specs

    @staticmethod
    def _resolve_sub_aspect_names(template_sub_sections: List) -> List[str]:
        if not template_sub_sections:
            return []
        names = []
        for sub in template_sub_sections:
            name = sub.get("name", "") if hasattr(sub, 'get') else getattr(sub, 'name', "")
            if isinstance(name, dict):
                name = name.get("zh", name.get("en", ""))
            if name:
                names.append(name)
        return names

    _SYNTHESIS_HARD_CONSTRAINT = """

## ⛔ 硬约束（必须遵守）
- 基于前置研究发现进行分析，**不得自行检索外部数据**
- **不得重新验证前置研究中已确立的结论**
- 只能引用前方章节中已出现的数据，不得引入新的外部数据源
- 每个核心结论必须标注所依赖的前置研究发现

## 📋 输入数据说明
你将收到前置章节 (sections) 的结构化研究发现（JSON 格式），
以及各章节的完整正文。请基于以上输入完成综合分析。
"""

    def _build_synthesis_prompt(self, topic: str, aspect: str) -> str:
        """Build synthesis prompt from external file"""
        is_summary = aspect.lower() in {"summary", "executive summary"}
        is_conclusion = aspect.lower() in {"conclusion", "research conclusion"}
        is_insight = "insight" in aspect.lower()
        lang_inst = get_language_instruction()
        
        constraint = self._SYNTHESIS_HARD_CONSTRAINT + '\n' + lang_inst
        
        try:
            pm = PromptManager()
            
            if is_summary:
                return pm.render(category="tasks", name="synthesis_summary", strip_frontmatter=True, topic=topic) + constraint
            elif is_conclusion:
                return pm.render(category="tasks", name="synthesis_conclusion", strip_frontmatter=True, topic=topic) + constraint
            elif is_insight:
                return pm.render(category="tasks", name="synthesis_insight", strip_frontmatter=True, topic=topic) + constraint
            else:
                return pm.render(category="tasks", name="synthesis_general", strip_frontmatter=True, topic=topic) + constraint
                
        except Exception as e:
            logger.warning(f"Failed to load synthesis task file, using fallback: {e}")
            return f"""# Synthesis Analysis

## Research Topic
{topic}

## Input Data
You will receive analysis content from each section (sections), please conduct synthesis analysis.

## Writing Requirements
Based on the analysis content from each section, conduct comprehensive judgment.

**Important Constraints**:
- ✅ Must be generated based on section contents (sections)
- ❌ Don't mention data sources or raw data
- ✅ Reflect deep understanding and integration of section contents

## ⛔ 硬约束
- 基于前置研究发现进行分析，**不得自行检索外部数据**
- 不得重新验证前置研究中已确立的结论
- 每个核心结论必须标注所依赖的前置研究发现
{lang_inst}
"""

    def _build_report_prompt(self, topic: str, requirement: Any) -> str:
        """Build report generation prompt from external file"""
        aspects = requirement.aspects if hasattr(requirement, 'aspects') else []
        lang_inst = get_language_instruction()
        
        try:
            pm = PromptManager()
            return pm.render(
                category="tasks",
                name="report_generation",
                strip_frontmatter=True,
                topic=topic,
                aspects="\n".join("- " + a for a in aspects),
            ) + '\n' + lang_inst
        except Exception as e:
            logger.warning(f"Failed to load report_generation.md, using fallback: {e}")
            return f"""# Report Generation Task

## Research Topic
{topic}

## Research Dimensions
{chr(10).join('- ' + a for a in aspects)}

## Output Requirements
1. Professional layout and formatting
2. Complete chapter structure
3. Clear data charts
4. Complete source annotations
{lang_inst}
"""

    def _estimate_duration(self, aspects_count: int, complexity: str) -> str:
        """Estimate execution time"""
        base_time = {
            "trivial": 5,
            "single": 10,
            "multi": 20,
            "complex": 40,
        }
        minutes = base_time.get(complexity, 20) * aspects_count
        if minutes < 60:
            return f"{minutes} minutes"
        else:
            return f"{minutes // 60} hours {minutes % 60} minutes"


class CompanyResearchStrategy(TaskDecompositionStrategy):
    """
    Company Research Strategy - Focus on public company deep analysis
    
    Core process:
    1. Basic info collection (company overview, financial data)
    2. Financial model construction
    3. Valuation analysis
    4. Investment logic synthesis
    """
    
    DEPENDENT_SECTIONS = {"summary", "conclusion", "investment_advice"}
    
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """Execute company research task decomposition"""
        # Reuse industry research base logic with company-specific prompts
        base_strategy = IndustryResearchStrategy()
        return base_strategy.decompose(requirement, intent_result, framework_config)


class CompetitorAnalysisStrategy(TaskDecompositionStrategy):
    """
    Competitor Analysis Strategy - Focus on competitive comparison
    
    Core process:
    1. Competitor information collection
    2. Multi-dimensional comparison analysis
    3. Strength/weakness summary
    """
    
    DEPENDENT_SECTIONS = {"summary", "conclusion", "comparison_summary"}
    
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """Execute competitor analysis task decomposition"""
        base_strategy = IndustryResearchStrategy()
        return base_strategy.decompose(requirement, intent_result, framework_config)


class FixTaskStrategy(TaskDecompositionStrategy):
    """
    Fix Task Strategy - For problem diagnosis and repair
    
    Simplified process:
    1. Problem diagnosis
    2. Fix execution
    3. Verification
    """
    
    PHASE_ORDER = [
        ResearchPhase.DATA_COLLECTION,  # Problem diagnosis
        ResearchPhase.DEEP_ANALYSIS,    # Fix execution
        ResearchPhase.DATA_VALIDATION,  # Verification
    ]
    
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """Execute fix task decomposition"""
        
        phases: Dict[ResearchPhase, List[AgentSpec]] = {
            ResearchPhase.DATA_COLLECTION: [],
            ResearchPhase.DATA_VALIDATION: [],
            ResearchPhase.DEEP_ANALYSIS: [],
            ResearchPhase.SYNTHESIS: [],
            ResearchPhase.REPORT_GENERATION: [],
        }
        
        topic = requirement.topic if hasattr(requirement, 'topic') else str(requirement)
        
        # Diagnosis Agent
        diagnosis_agent = AgentSpec(
            agent_id="diagnosis_agent",
            agent_type="diagnosis",
            category="data-collection",
            task_description=f"Diagnose problem: {topic}",
            input_keys=["problem"],
            output_keys=["diagnosis_result"],
            dependencies=[],
            priority=10,
            parallel_group=0,
            quality_threshold=0.7,
            max_retries=3,
            skills=["search_skill"],
            system_prompt=f"Diagnose the following problem: {topic}",
            context={"topic": topic},
        )
        phases[ResearchPhase.DATA_COLLECTION].append(diagnosis_agent)
        
        # Fix Agent
        fix_agent = AgentSpec(
            agent_id="fix_agent",
            agent_type="fix",
            category="market-analysis",
            task_description=f"Fix problem: {topic}",
            input_keys=["diagnosis_result"],
            output_keys=["fix_result"],
            dependencies=["diagnosis_agent"],
            priority=10,
            parallel_group=0,
            quality_threshold=0.8,
            max_retries=3,
            skills=[],
            system_prompt=f"Based on diagnosis results, fix the problem: {topic}",
            context={"topic": topic},
        )
        phases[ResearchPhase.DEEP_ANALYSIS].append(fix_agent)
        
        # Validation Agent
        validation_agent = AgentSpec(
            agent_id="validation_agent",
            agent_type="validation",
            category="quality-check",
            task_description=f"Validate fix result: {topic}",
            input_keys=["fix_result"],
            output_keys=["validation_result"],
            dependencies=["fix_agent"],
            priority=10,
            parallel_group=0,
            quality_threshold=0.9,
            max_retries=2,
            skills=[],
            system_prompt=f"Validate whether the fix was successful: {topic}",
            context={"topic": topic},
        )
        phases[ResearchPhase.DATA_VALIDATION].append(validation_agent)
        
        return DecompositionPlan(
            task_id=f"fix_{topic[:20]}",
            phases=phases,
            execution_order=self.PHASE_ORDER,
            quality_gates={
                ResearchPhase.DATA_COLLECTION: 0.7,
                ResearchPhase.DEEP_ANALYSIS: 0.8,
                ResearchPhase.DATA_VALIDATION: 0.9,
            },
            estimated_agents=3,
            estimated_duration="15 minutes",
        )


class EvaluationTaskStrategy(TaskDecompositionStrategy):
    """
    Evaluation Task Strategy - For comparative assessment
    
    Process:
    1. Collect evaluation target information
    2. Multi-dimensional evaluation
    3. Conclusion output
    """
    
    def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        """Execute evaluation task decomposition"""
        base_strategy = IndustryResearchStrategy()
        return base_strategy.decompose(requirement, intent_result, framework_config)


# Strategy registry
STRATEGY_REGISTRY: Dict[str, type] = {
    "industry_report": IndustryResearchStrategy,
    "company_research": CompanyResearchStrategy,
    "competitor_analysis": CompetitorAnalysisStrategy,
    "research": IndustryResearchStrategy,  # Default research strategy
    "fix": FixTaskStrategy,
    "evaluation": EvaluationTaskStrategy,
}


def get_strategy(output_type: str) -> TaskDecompositionStrategy:
    """
    Get task decomposition strategy
    
    Args:
        output_type: Output type
        
    Returns:
        Corresponding strategy instance
    """
    strategy_class = STRATEGY_REGISTRY.get(output_type, IndustryResearchStrategy)
    return strategy_class()


def register_strategy(output_type: str, strategy_class: type) -> None:
    """
    Register new task decomposition strategy
    
    Args:
        output_type: Output type
        strategy_class: Strategy class
    """
    STRATEGY_REGISTRY[output_type] = strategy_class
    logger.info(f"Registered strategy: {output_type}")
