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
    "Financial Analysis": ["llm_skill", "stock_data", "stock_analysis", "data_analysis"],
    "Valuation Analysis": ["llm_skill", "stock_analysis", "data_analysis"],
    "Company Analysis": ["llm_skill", "stock_data", "stock_analysis", "market_analysis"],
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
    quality_gates: Dict[ResearchPhase, float]  # Quality threshold per phase
    estimated_agents: int
    estimated_duration: str
    
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
        
        # Separate normal sections and dependent sections
        normal_aspects = []
        dependent_aspects = []
        for i, aspect in enumerate(aspects):
            if aspect.lower() in self.DEPENDENT_SECTIONS or any(ds in aspect for ds in self.DEPENDENT_SECTIONS):
                dependent_aspects.append((i, aspect))
            else:
                normal_aspects.append((i, aspect))
        
        # === Phase 1: Data Collection ===
        for i, aspect in normal_aspects:
            agent_id = self._create_agent_id(ResearchPhase.DATA_COLLECTION, i, aspect.lower().replace(" ", "_"))
            
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
                skills=["search_skill", "news_search", "llm_skill"],
                system_prompt=self._build_data_collection_prompt(topic, aspect, framework_config),
                context={"aspect": aspect, "topic": topic},
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
                system_prompt=self._build_analysis_prompt(topic, aspect, framework_config),
                context={"aspect": aspect, "topic": topic},
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
        )
    
    def _build_data_collection_prompt(self, topic: str, aspect: str, framework_config: Any) -> str:
        """Build data collection prompt from external file"""
        focus_areas = framework_config.get_focus_areas() if framework_config else []
        priority_sources = framework_config.get_priority_sources() if framework_config else []
        lang_inst = get_language_instruction()
        
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
            ) + '\n' + lang_inst
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

    def _build_analysis_prompt(self, topic: str, aspect: str, framework_config: Any) -> str:
        """Build analysis prompt from external file"""
        depth = framework_config.get_analysis_depth() if framework_config else "deep"
        metrics = framework_config.get_key_metrics() if framework_config else []
        lang_inst = get_language_instruction()
        
        # Determine if inline citations are needed (academic reports need them)
        require_inline_citations = False
        if framework_config and hasattr(framework_config, 'requires_inline_citations'):
            require_inline_citations = framework_config.requires_inline_citations()
        
        # Generate citation instruction based on requirements
        if require_inline_citations:
            citation_instruction = """- Data must be annotated with sources (use [Source X] format, e.g., "2024 sales 12.8 million units [Source 15]")
- Each data point followed immediately by source annotation"""
        else:
            citation_instruction = """- **Strictly no source markers in text** (e.g., "【source:xxx】", "【source15】", "(source:xxx)" formats)
- Present data directly; sources will be listed in "Data Sources" section at report end
- Do not add any form of source explanation after data"""
        
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
            ) + '\n' + lang_inst
        except Exception as e:
            logger.warning(f"Failed to load deep_analysis.md, using fallback: {e}")
            return f"""# Deep Analysis Task

## Research Topic
{topic}

## Research Dimension
{aspect}

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