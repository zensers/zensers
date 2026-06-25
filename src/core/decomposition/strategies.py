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

# Import PromptManager for external prompt loading
from ..prompt_manager import PromptManager

# Language consistency: instruction to enforce output language
from src.core.i18n import get_language_instruction

logger = logging.getLogger(__name__)


class ResearchPhase(Enum):
    """Research phase - follows professional research methodology"""
    DATA_COLLECTION = "data_collection"      # Data collection
    DATA_VALIDATION = "data_validation"      # Data validation
    DEEP_ANALYSIS = "deep_analysis"          # Deep analysis
    SYNTHESIS = "synthesis"                  # Synthesis
    REPORT_GENERATION = "report_generation"  # Report generation
    CALIBRATION = "calibration"              # Cross-agent numeric calibration


# Dynamically assign Skills by research dimension, avoid all Agents carrying irrelevant skills
ASPECT_SKILL_MAP = {
    # DEEP_ANALYSIS phase skills: search_skill is intentionally excluded.
    # Data collection is handled exclusively by DATA_COLLECTION phase agents (category="research").
    # DEEP_ANALYSIS agents focus on analysis using pre-collected data.
    "Market Size": ["llm_skill", "data_analysis", "lc_python_repl"],
    "Market Share": ["llm_skill", "data_analysis", "lc_python_repl"],
    "Competitive Landscape": ["llm_skill", "market_analysis"],
    "Industry Trends": ["llm_skill", "data_analysis"],
    "Development Trends": ["llm_skill", "data_analysis"],
    "Financial Analysis": ["llm_skill", "stock_analysis", "data_analysis"],
    "Valuation Analysis": ["llm_skill", "stock_analysis", "data_analysis"],
    "Company Analysis": ["llm_skill", "stock_analysis", "market_analysis"],
    "Policy Environment": ["llm_skill", "policy_analysis"],
    "Technology Trends": ["llm_skill", "tech_trend"],
    "Industry Chain": ["llm_skill", "market_analysis"],
    "Risk Analysis": ["llm_skill", "risk_analysis"],
    "Investment Advice": ["llm_skill", "stock_analysis", "data_analysis"],
    "User Analysis": ["llm_skill", "data_analysis", "lc_python_repl"],
    "Regional Distribution": ["llm_skill", "data_analysis"],
    "Growth Analysis": ["llm_skill", "data_analysis"],
    "Sales Analysis": ["llm_skill", "data_analysis", "lc_python_repl"],
    "Data Comparison": ["llm_skill", "data_analysis", "lc_python_repl"],
    "Executive Summary": ["llm_skill"],
    "Research Conclusion": ["llm_skill"],
    "Data Validation": ["llm_skill"],
    "Comprehensive Analysis": ["llm_skill"],
}

# Default skills for fallback when aspect not found in map
# Excludes search_skill since DEEP_ANALYSIS agents should not auto-search
DEFAULT_ASPECT_SKILLS = ["llm_skill"]


def get_skills_for_aspect(aspect: str) -> List[str]:
    """
    Return required Skills list based on research dimension
    
    Args:
        aspect: Research dimension name
        
    Returns:
        Applicable Skills list
    """
    # Exact match
    if aspect in ASPECT_SKILL_MAP:
        return ASPECT_SKILL_MAP[aspect]
    
    # Contains match
    for key, skills in ASPECT_SKILL_MAP.items():
        if key in aspect:
            return skills
    
    # Default: LLM-only, no search_skill (DEEP_ANALYSIS agents use pre-collected data)
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
    "search_skill": "web_search",
    "news_search": "web_search",
    "lc_tavily_search": "web_search",
    "lc_wikipedia": "web_search",
    "llm_skill": "llm",
}

DATA_SOURCE_SKILL_MAP = {
    "financial": ["stock_data"],
    "valuation": ["stock_data"],
    "company": ["stock_data"],
    "market_size": ["stock_data"],
    "competitive": [],
    "policy": [],
    "technology": [],
    "risk": [],
    "财务": ["stock_data"],
    "估值": ["stock_data"],
    "公司": ["stock_data"],
    "盈利": ["stock_data"],
    "营收": ["stock_data"],
    "市值": ["stock_data"],
    "市场规模": ["stock_data"],
    "利润": ["stock_data"],
    "资产负债": ["stock_data"],
    "roe": ["stock_data"],
    "pe": ["stock_data"],
    "pb": ["stock_data"],
    "增长": ["stock_data"],
    "投资": ["stock_data"],
}


def _get_data_collection_skills(aspect: str, topic: str = "", intent_result: Any = None) -> List[str]:
    db_skills: List[str] = []
    web_skills: List[str] = []
    llm_skills: List[str] = []

    base_skills = ["search_skill", "news_search", "llm_skill"]
    aspect_skills: List[str] = []
    aspect_lower = aspect.lower()
    for keyword, extra_skills in DATA_SOURCE_SKILL_MAP.items():
        if keyword in aspect_lower:
            aspect_skills.extend(extra_skills)
    if intent_result:
        primary_type = getattr(intent_result, 'primary_research_type', None)
        if primary_type and getattr(primary_type, 'value', '') in (
            "company_research", "investment", "competitive_analysis"
        ):
            if "stock_data" not in aspect_skills:
                aspect_skills.append("stock_data")

    all_unique = list(dict.fromkeys(aspect_skills + base_skills))
    for skill in all_unique:
        tier = SKILL_PRIORITY_MAP.get(skill, "web_search")
        if tier == "structured_db":
            db_skills.append(skill)
        elif tier == "llm":
            llm_skills.append(skill)
        else:
            web_skills.append(skill)
    return db_skills + web_skills + llm_skills


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
    
    def get_agents_for_phase(self, phase: ResearchPhase) -> List[AgentSpec]:
        """Get Agent list for specified phase"""
        return self.phases.get(phase, [])
    
    def get_total_agents(self) -> int:
        """Get total Agent count"""
        return sum(len(agents) for agents in self.phases.values())


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
    }
    
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
        
        section_data_specs = getattr(intent_result, 'section_data_specs', []) or []
        if section_data_specs and isinstance(section_data_specs[0], dict):
            section_data_specs = _convert_specs_from_dicts(section_data_specs)

        # P0 alignment: override section_data_specs with framework_tree when available
        sections_tree = None
        if hasattr(requirement, 'dynamic_fields') and requirement.dynamic_fields and requirement.dynamic_fields.get('sections_tree'):
            sections_tree = requirement.dynamic_fields['sections_tree']
        elif hasattr(requirement, 'section_details') and requirement.section_details:
            for sd in requirement.section_details:
                if isinstance(sd, dict) and sd.get('sub_sections'):
                    sections_tree = requirement.section_details
                    break
        if sections_tree and section_data_specs:
            section_data_specs = self._align_section_data_specs_with_tree(section_data_specs, sections_tree)

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
        
        # === Phase 1: Data Collection ===
        for seq_idx, (i, aspect) in enumerate(normal_aspects):
            agent_id = self._create_agent_id(ResearchPhase.DATA_COLLECTION, i, aspect.lower().replace(" ", "_"))
            section_id = f"section_{seq_idx}"
            matched_spec = section_spec_by_id.get(section_id) or section_spec_by_name.get(aspect)
            
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
                system_prompt=self._build_data_collection_prompt(topic, aspect, framework_config, sub_aspects=[sub.name for sub in matched_spec.sub_sections] if matched_spec and matched_spec.sub_sections else None),
                context={"aspect": aspect, "topic": topic,
                         "section_id": section_id,
                         "data_needs": matched_spec.all_data_needs if matched_spec else [aspect],
                         "search_data_needs": matched_spec.search_data_needs if matched_spec else [aspect],
                         "sub_aspects": [sub.name for sub in matched_spec.sub_sections] if matched_spec and matched_spec.sub_sections else []},
            )
            phases[ResearchPhase.DATA_COLLECTION].append(spec)
        
        # === Phase 2: Data Validation ===
        for i, aspect in normal_aspects:
            # Data validation agent depends on corresponding data collection agent
            data_agent_id = self._create_agent_id(ResearchPhase.DATA_COLLECTION, i, aspect.lower().replace(" ", "_"))
            agent_id = self._create_agent_id(ResearchPhase.DATA_VALIDATION, i, aspect.lower().replace(" ", "_"))
            
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
                skills=["llm_skill"],
                system_prompt=self._build_validation_prompt(topic, aspect),
                context={"aspect": aspect, "topic": topic},
            )
            phases[ResearchPhase.DATA_VALIDATION].append(spec)
        
        # === Phase 3: Deep Analysis ===
        for i, aspect in normal_aspects:
            validation_agent_id = self._create_agent_id(ResearchPhase.DATA_VALIDATION, i, aspect.lower().replace(" ", "_"))
            agent_id = self._create_agent_id(ResearchPhase.DEEP_ANALYSIS, i, aspect.lower().replace(" ", "_"))
            da_matched_spec = section_spec_by_name.get(aspect)
            
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
                system_prompt=self._build_analysis_prompt(topic, aspect, framework_config, sub_aspects=[sub.name for sub in da_matched_spec.sub_sections] if da_matched_spec and da_matched_spec.sub_sections else None),
                context={"aspect": aspect, "topic": topic,
                         "sub_aspects": [sub.name for sub in da_matched_spec.sub_sections] if da_matched_spec and da_matched_spec.sub_sections else []},
            )
            phases[ResearchPhase.DEEP_ANALYSIS].append(spec)
        
        # === Phase 4: Synthesis ===
        # Synthesis of dependent sections
        all_analysis_agents = [
            self._create_agent_id(ResearchPhase.DEEP_ANALYSIS, i, a.lower().replace(" ", "_"))
            for i, a in normal_aspects
        ]
        
        for i, aspect in dependent_aspects:
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
                skills=["llm_skill"],
                system_prompt=self._build_synthesis_prompt(topic, aspect),
                context={"aspect": aspect, "topic": topic, "is_dependent": True},
            )
            phases[ResearchPhase.SYNTHESIS].append(spec)
        
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
            skills=["llm_skill", "docx_skill"],
            system_prompt=self._build_report_prompt(topic, requirement),
            context={"topic": topic, "aspects": aspects},
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

    def _build_analysis_prompt(self, topic: str, aspect: str, framework_config: Any, sub_aspects: Optional[List[str]] = None) -> str:
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
        if sub_aspects:
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
            skills=["search_skill", "llm_skill"],
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
            skills=["llm_skill"],
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
            skills=["llm_skill"],
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