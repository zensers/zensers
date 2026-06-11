"""
Intelligent Routing Adapter

Integrates the new intelligent routing components into the existing ResearchOrchestrator workflow.

Responsibilities:
- Coordinate SemanticIntentAnalyzer, TaskStructureAnalyzer, DynamicPhaseOrchestrator
- Provide interface compatible with existing DecompositionStrategy
- Manage ContentLockManager lifecycle
- Support progressive migration (new and old systems in parallel)

Design Doc: .sisyphus/plans/intelligent_routing_system_design.md
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .semantic_intent import SemanticIntentAnalyzer, DeepIntentResult
from .task_structure import TaskStructureAnalyzer, TaskStructure, SectionSpec, SectionRole
from .dynamic_orchestrator import (
    DynamicPhaseOrchestrator,
    ExecutionPlan,
    ExecutionPhase,
    AgentSpec,
    ContentLockRule,
    PhaseType,
)
from .content_lock import ContentLockManager, SectionState
# Type definitions imported from intent_types.py (Phase 1 type separation)
from .intent_types import IntentType, TaskComplexity, IntentAnalysisResult

if TYPE_CHECKING:
    from .decomposition.strategies import DecompositionPlan

logger = logging.getLogger(__name__)


@dataclass
class IntelligentRoutingResult:
    """
    Intelligent Routing Result

    Contains complete routing analysis results for use by ResearchOrchestrator.
    """
    # Original input
    user_request: str
    requirement: Dict[str, Any]

    # Analysis results
    intent_result: DeepIntentResult
    task_structure: TaskStructure
    execution_plan: ExecutionPlan

    # Compatibility output
    decomposition_plan: Optional["DecompositionPlan"] = None

    # Incremental analysis
    skip_phases: List[str] = field(default_factory=list)  # Phase IDs that can be skipped

    # Metadata
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    used_intelligent_routing: bool = True
    fallback_used: bool = False
    fallback_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "user_request": self.user_request,
            "intent": {
                "primary_intent": self.intent_result.primary_intent.value,
                "confidence": self.intent_result.intent_confidence,
                "complexity": self.intent_result.complexity.value,
                "hidden_requirements": self.intent_result.hidden_requirements,
            },
            "task_structure": self.task_structure.to_dict(),
            "execution_plan": (
                self.execution_plan.to_dict()
                if hasattr(self.execution_plan, 'to_dict')
                else {"phases": [], "total_agents": 0}
            ),
            "used_intelligent_routing": self.used_intelligent_routing,
            "fallback_used": self.fallback_used,
        }


class IntelligentRoutingAdapter:
    """
    Intelligent Routing Adapter

    Coordinates integration of new components with existing system.

    Usage:
    ```python
    adapter = IntelligentRoutingAdapter()
    result = adapter.analyze(user_request, requirement)

    # Use compatible DecompositionPlan
    plan = result.decomposition_plan

    # Or use new ExecutionPlan
    exec_plan = result.execution_plan
    ```
    """

    def __init__(
        self,
        use_llm: bool = True,
        fallback_to_keyword: bool = True,
        enable_content_lock: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize adapter

        Args:
            use_llm: Whether to use LLM for semantic analysis
            fallback_to_keyword: Whether to fallback to keyword matching when LLM fails
            enable_content_lock: Whether to enable content lock management
            max_retries: Maximum retry count
        """
        self._use_llm = use_llm
        self._fallback_to_keyword = fallback_to_keyword
        self._enable_content_lock = enable_content_lock
        self._max_retries = max_retries

        # Initialize components
        self._intent_analyzer = SemanticIntentAnalyzer(
            use_llm=use_llm,
            fallback_to_keyword=fallback_to_keyword,
        )
        self._structure_analyzer = TaskStructureAnalyzer()
        self._phase_orchestrator = DynamicPhaseOrchestrator()

        # ContentLockManager created at execution time
        self._lock_manager: Optional[ContentLockManager] = None
        
        # Lazy initialize LLM Skill
        self._llm_skill = None

        # Keyword matching fallback (uses existing IntentGate)
        self._keyword_analyzer = None
        
        logger.info(
            f"IntelligentRoutingAdapter initialized: "
            f"use_llm={use_llm}, fallback={fallback_to_keyword}, "
            f"content_lock={enable_content_lock}"
        )
    
    def analyze_incremental(
        self,
        user_request: str,
        requirement: Dict[str, Any],
        completed_aspects: Optional[List[str]] = None,
        topic: Optional[str] = None,
        existing_intent_result: Optional['DeepIntentResult'] = None,
    ) -> IntelligentRoutingResult:
        """
        R-FIX-2: Incremental analysis with intent fusion.

        Args:
            existing_intent_result: Existing intent result for fusion
        """
        full_result = self.analyze(user_request, requirement, topic)

        if existing_intent_result is not None:
            new_intent = full_result.intent_result
            if new_intent.used_fallback and not existing_intent_result.used_fallback:
                logger.info(
                    f"[IntelligentRouting] Incremental: new intent used fallback "
                    f"(conf={new_intent.intent_confidence:.2f}), keeping existing "
                    f"(intent={existing_intent_result.primary_intent.value}, "
                    f"conf={existing_intent_result.intent_confidence:.2f})"
                )
                full_result.intent_result = existing_intent_result
            elif (new_intent.primary_intent != existing_intent_result.primary_intent
                  and new_intent.intent_confidence < existing_intent_result.intent_confidence):
                logger.info(
                    f"[IntelligentRouting] Incremental: intent changed but lower confidence "
                    f"({new_intent.primary_intent.value}:{new_intent.intent_confidence:.2f} "
                    f"vs {existing_intent_result.primary_intent.value}:{existing_intent_result.intent_confidence:.2f}), "
                    f"keeping existing"
                )
                full_result.intent_result = existing_intent_result
            else:
                if new_intent.primary_intent != existing_intent_result.primary_intent:
                    logger.info(
                        f"[IntelligentRouting] Incremental: intent changed with sufficient confidence "
                        f"({existing_intent_result.primary_intent.value} → {new_intent.primary_intent.value}, "
                        f"conf={new_intent.intent_confidence:.2f})"
                    )

        if not completed_aspects:
            return full_result

        # 3. Compare analysis to determine skippable phases
        skip_phases = []
        for phase in full_result.execution_plan.phases:
            phase_should_skip = True
            for section_id in phase.section_ids:
                # Extract name from section_id (e.g., "section_0_market_size" → "market_size")
                section_name = self._extract_section_name(section_id)

                # Check if all sections are covered
                if not self._is_covered_by_completed(section_name, completed_aspects):
                    phase_should_skip = False
                    break

            if phase_should_skip:
                skip_phases.append(phase.phase_id)

        # 4. Mark result
        full_result.skip_phases = skip_phases

        if skip_phases:
            logger.info(
                f"[IntelligentRouting] Incremental: {len(skip_phases)} phases will be skipped "
                f"(already covered by completed aspects: {completed_aspects})"
            )

        return full_result

    def _extract_section_name(self, section_id: str) -> str:
        """Extract section name from section_id"""
        # section_id format: "section_0_market_size" or "data_collection_0_competitive_landscape"
        parts = section_id.split("_")
        # Try to extract Chinese name (last part is usually Chinese name)
        for part in reversed(parts):
            if any('\u4e00' <= c <= '\u9fff' for c in part):
                return part
        return parts[-1] if parts else section_id

    def _is_covered_by_completed(self, section_name: str, completed_aspects: List[str]) -> bool:
        """
        Determine if section is covered by completed work

        Exact match + keyword fuzzy match
        """
        # 1. Exact match
        if section_name in completed_aspects:
            return True

        # 2. Keyword containment match
        for completed in completed_aspects:
            # Completed section contains current section name
            if completed in section_name or section_name in completed:
                return True
            # Shared keywords (e.g., "competitive_landscape" and "company_research" share "competitive")
            # But not fully covered - only mark as skip when explicitly contained
            common_kw = self._get_common_keywords(completed, section_name)
            if len(common_kw) >= 2:  # Sharing 2+ keywords counts as coverage
                return True

        return False

    @staticmethod
    def _get_common_keywords(a: str, b: str) -> set:
        """
        Extract shared keywords from two section name phrases.
        
        Supports both English and Chinese keywords for cross-language matching.
        Used by _is_covered_by_completed() to determine if phases can be skipped.
        """
        # English keyword units
        en_units = {
            "market", "size", "competition", "landscape", "development", "trend",
            "technology", "policy", "regulation", "industry", "chain", "enterprise",
            "company", "sector", "user", "consumer", "brand",
            "financial", "valuation", "investment", "risk", "analysis",
        }
        
        # Chinese keyword units (paired with English equivalents)
        zh_units = {
            "市场", "规模", "竞争", "格局", "发展", "趋势",
            "技术", "政策", "监管", "行业", "产业链", "企业",
            "公司", "细分", "用户", "消费者", "品牌",
            "财务", "估值", "投资", "风险", "分析",
        }
        
        zh_to_en_mapping = {
            "市场": "market", "规模": "size", "竞争": "competition", "格局": "landscape",
            "发展": "development", "趋势": "trend", "技术": "technology", "政策": "policy",
            "监管": "regulation", "行业": "industry", "产业链": "chain", "企业": "enterprise",
            "公司": "company", "细分": "sector", "用户": "user", "消费者": "consumer",
            "品牌": "brand", "财务": "financial", "估值": "valuation", "投资": "investment",
            "风险": "risk", "分析": "analysis",
        }
        
        def extract_normalized_keywords(text: str) -> set:
            """Extract and normalize keywords from text to canonical English form."""
            text_lower = text.lower()
            keywords = set()
            
            # Extract English keywords
            for kw in en_units:
                if kw in text_lower:
                    keywords.add(kw)
            
            # Extract Chinese keywords and map to English
            for zh_kw, en_kw in zh_to_en_mapping.items():
                if zh_kw in text:
                    keywords.add(en_kw)
            
            return keywords
        
        keywords_a = extract_normalized_keywords(a)
        keywords_b = extract_normalized_keywords(b)
        return keywords_a & keywords_b
    
    def analyze(
        self,
        user_request: str,
        requirement: Dict[str, Any],
        topic: Optional[str] = None,
    ) -> IntelligentRoutingResult:
        """
        Execute complete intelligent routing analysis

        Args:
            user_request: User's original request
            requirement: Parsed requirement dictionary
            topic: Report topic (optional, inferred from requirement)

        Returns:
            IntelligentRoutingResult: Complete routing result
        """
        logger.info(f"[IntelligentRouting] Starting analysis for: {user_request[:100]}...")

        # Step 1: Semantic intent analysis
        intent_result = self._analyze_intent(user_request, requirement)

        # Step 2: Task structure analysis
        task_structure = self._analyze_structure(requirement, intent_result, topic)

        # Step 3: Dynamic phase orchestration
        execution_plan = self._orchestrate_phases(task_structure, intent_result, topic)

        # Step 4: Convert to compatible format
        decomposition_plan = self._to_decomposition_plan(execution_plan)

        # Step 5: Initialize ContentLockManager
        if self._enable_content_lock:
            self._lock_manager = ContentLockManager(
                execution_plan=execution_plan,
                max_retries=self._max_retries,
            )
        
        result = IntelligentRoutingResult(
            user_request=user_request,
            requirement=requirement,
            intent_result=intent_result,
            task_structure=task_structure,
            execution_plan=execution_plan,
            decomposition_plan=decomposition_plan,
        )
        
        logger.info(
            f"[IntelligentRouting] Analysis complete: "
            f"{len(task_structure.sections)} sections, "
            f"{len(execution_plan.phases)} phases, "
            f"{execution_plan.total_agents} agents"
        )
        
        return result
    
    def _analyze_intent(
        self,
        user_request: str,
        requirement: Dict[str, Any],
    ) -> DeepIntentResult:
        """Execute semantic intent analysis"""
        try:
            result = self._intent_analyzer.analyze(
                user_request=user_request,
                requirement=requirement,
            )

            logger.info(
                f"[Intent] Primary: {result.primary_intent.value}, "
                f"Confidence: {result.intent_confidence:.2f}, "
                f"Complexity: {result.complexity.value}"
            )

            return result

        except Exception as e:
            logger.error(f"[Intent] Analysis failed: {e}")
            # Return default result
            return DeepIntentResult(
                primary_intent=IntentType.RESEARCH,
                intent_confidence=0.5,
                intent_reasoning=f"Fallback due to error: {e}",
                complexity=TaskComplexity.SINGLE,
                used_fallback=True,
            )

    def _analyze_structure(
        self,
        requirement: Dict[str, Any],
        intent_result: DeepIntentResult,
        topic: Optional[str],
    ) -> TaskStructure:
        """Execute task structure analysis"""
        # Extract section info from requirement
        aspects = requirement.get("aspects", [])
        topic = topic or requirement.get("topic", "Research Report")

        # Convert to aspect string list
        aspect_names = []
        for aspect in aspects:
            if isinstance(aspect, str):
                aspect_names.append(aspect)
            elif isinstance(aspect, dict):
                aspect_names.append(aspect.get("name", aspect.get("id", "Unknown")))

        # Use TaskStructureAnalyzer for deep analysis
        task_structure = self._structure_analyzer.analyze(
            intent=intent_result,
            aspects=aspect_names,
            topic=topic,
        )

        logger.info(
            f"[Structure] {len(task_structure.sections)} sections, "
            f"{len(task_structure.dependencies)} dependencies"
        )

        return task_structure

    def _orchestrate_phases(
        self,
        task_structure: TaskStructure,
        intent_result: DeepIntentResult,
        topic: Optional[str],
    ) -> ExecutionPlan:
        """Execute dynamic phase orchestration"""
        execution_plan = self._phase_orchestrator.plan(
            task_structure=task_structure,
            intent=intent_result,
            topic=topic,
        )

        logger.info(
            f"[Phases] {len(execution_plan.phases)} phases generated, "
            f"{len(execution_plan.content_lock_rules)} lock rules"
        )

        return execution_plan

    def _to_decomposition_plan(
        self,
        execution_plan: ExecutionPlan,
    ) -> Optional["DecompositionPlan"]:
        """Convert to compatible DecompositionPlan"""
        try:
            return execution_plan.to_decomposition_plan()
        except Exception as e:
            logger.warning(f"[Compat] Failed to convert to DecompositionPlan: {e}")
            return None

    def get_lock_manager(self, task_id: Optional[str] = None) -> Optional[ContentLockManager]:
        """Get ContentLockManager instance (task_id reserved for per-task expansion)"""
        return self._lock_manager

    def can_execute_section(self, section_id: str) -> Tuple[bool, str]:
        """
        Check if section can be executed

        Args:
            section_id: Section ID

        Returns:
            (can_execute, reason): Whether executable and reason
        """
        if not self._lock_manager:
            return True, "Content lock not enabled"

        return self._lock_manager.can_execute(section_id)

    def try_unlock_section(self, section_id: str) -> Tuple[bool, str]:
        """
        Try to unlock section

        Args:
            section_id: Section ID

        Returns:
            (unlocked, reason): Whether unlocked and reason
        """
        if not self._lock_manager:
            return True, "Content lock not enabled"

        return self._lock_manager.try_unlock(section_id)

    def mark_section_running(self, section_id: str) -> bool:
        """Mark section as started execution"""
        if not self._lock_manager:
            return True

        return self._lock_manager.mark_running(section_id)

    def mark_section_completed(
        self,
        section_id: str,
        quality_score: float = 0.8,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Mark section as completed

        Returns:
            List of unlocked section IDs
        """
        if not self._lock_manager:
            return []

        return self._lock_manager.mark_completed(
            section_id=section_id,
            quality_score=quality_score,
            output_data=output_data,
        )

    def mark_section_failed(
        self,
        section_id: str,
        error_message: str = "",
    ) -> bool:
        """Mark section as failed"""
        if not self._lock_manager:
            return True

        return self._lock_manager.mark_failed(
            section_id=section_id,
            error_message=error_message,
        )

    def get_execution_progress(self) -> Dict[str, Any]:
        """Get execution progress"""
        if not self._lock_manager:
            return {"enabled": False}

        return self._lock_manager.get_progress()

    def get_blocked_sections(self) -> List[Tuple[str, str]]:
        """Get blocked section list"""
        if not self._lock_manager:
            return []

        return self._lock_manager.get_blocked_sections()

    # ========================================
    # Phase 3: Compatibility layer methods (compatible with traditional routing interface)
    # ========================================

    def analyze_simple(
        self,
        user_request: str,
        requirement: Optional[Dict[str, Any]] = None,
    ) -> "IntentAnalysisResult":
        """
        Simplified intent analysis (compatible with IntentGate.analyze interface)

        Provides same interface signature as traditional IntentGate for seamless replacement.

        Args:
            user_request: User's original request text
            requirement: Structured requirement (optional)

        Returns:
            IntentAnalysisResult: Analysis result compatible with traditional routing
        """
        # Call complete analysis
        full_requirement = requirement or {}
        result = self.analyze(user_request, full_requirement)

        # Convert to compatible format
        from .intent_types import AgentCreationStrategy

        # Build Agent creation strategy
        strategy = AgentCreationStrategy(
            intent=result.intent_result.primary_intent,
            complexity=result.intent_result.complexity,
            recommended_agents=[spec.agent_type for spec in result.execution_plan.get_all_agents()[:5]],
            agent_count_estimate=result.execution_plan.total_agents,
            parallel_execution=len(result.execution_plan.phases) > 1,  # Multi-phase implies parallel possible
            skill_requirements=[],  # Extract from agent_specs
            creation_mode="dynamic",
            priority="medium",
            context_requirements={},
            clarification_needed=False,
            clarification_questions=None,
        )
        
        return IntentAnalysisResult(
            intent=result.intent_result.primary_intent,
            complexity=result.intent_result.complexity,
            strategy=strategy,
            confidence=result.intent_result.intent_confidence,
            keywords_matched=[],
            reasoning=result.intent_result.intent_reasoning,
        )
    
    def get_template_for_intent(
        self,
        intent_type: IntentType,
    ) -> Dict[str, Any]:
        """
        Get capability template for intent (compatible with CategoryRouter.route_to_template interface)

        Args:
            intent_type: Intent type

        Returns:
            Capability template dictionary
        """
        # Intent-to-capability template mapping.
        # CRITICAL: recommended_skills MUST use actual SkillRegistry names
        # (see src/skills/registry.py:register_core_skills for the canonical list).
        # Skill name aliases (e.g. "search") will NOT resolve at runtime.
        #
        # Core research skills: search_skill (multi-engine search), web_scraper (page fetch),
        #                       llm_skill (reasoning/analysis), news_search (news-specific)
        intent_to_capability = {
            IntentType.RESEARCH: {
                "primary_capability": "research",
                "secondary_capabilities": ["data_collection", "analysis"],
                "recommended_skills": ["search_skill", "web_scraper", "llm_skill"],
                "model_preference": "reasoning",
            },
            IntentType.IMPLEMENTATION: {
                "primary_capability": "implementation",
                "secondary_capabilities": ["coding", "generation"],
                "recommended_skills": ["llm_skill", "docx_skill"],
                "model_preference": "coding",
            },
            IntentType.INVESTIGATION: {
                "primary_capability": "investigation",
                "secondary_capabilities": ["debugging", "verification"],
                "recommended_skills": ["search_skill", "llm_skill"],
                "model_preference": "reasoning",
            },
            IntentType.EVALUATION: {
                "primary_capability": "evaluation",
                "secondary_capabilities": ["comparison", "assessment"],
                "recommended_skills": ["llm_skill", "search_skill"],
                "model_preference": "reasoning",
            },
            IntentType.FIX: {
                "primary_capability": "fix",
                "secondary_capabilities": ["debugging", "correction"],
                "recommended_skills": ["llm_skill"],
                "model_preference": "coding",
            },
            IntentType.OPEN_ENDED: {
                "primary_capability": "exploration",
                "secondary_capabilities": ["research", "analysis"],
                "recommended_skills": ["search_skill", "llm_skill"],
                "model_preference": "reasoning",
            },
            IntentType.CLARIFICATION: {
                "primary_capability": "clarification",
                "secondary_capabilities": ["questioning"],
                "recommended_skills": ["llm_skill"],
                "model_preference": "chat",
            },
        }
        
        return intent_to_capability.get(intent_type, intent_to_capability[IntentType.RESEARCH])


# Convenience function
def create_intelligent_routing_result(
    user_request: str,
    requirement: Dict[str, Any],
    topic: Optional[str] = None,
) -> IntelligentRoutingResult:
    """
    Convenience function to create intelligent routing result

    Args:
        user_request: User request
        requirement: Requirement dictionary
        topic: Report topic

    Returns:
        IntelligentRoutingResult
    """
    adapter = IntelligentRoutingAdapter()
    return adapter.analyze(user_request, requirement, topic)


__all__ = [
    "IntelligentRoutingAdapter",
    "IntelligentRoutingResult",
    "create_intelligent_routing_result",
]
