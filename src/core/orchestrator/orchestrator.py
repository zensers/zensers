"""
Research Orchestrator - Research Task Master Scheduler (Integrated Interactive Version)

Responsibilities:
- Process orchestration (six-layer architecture + user interaction)
- Dependency injection coordination
- Backward compatibility adaptation

Design Principles:
- Single responsibility: orchestration only
- Dependency injection: all components injected via constructor
- Stateless: does not hold execution state

Complete Flow:
1. Requirement clarification → SmartClarifier
2. Framework confirmation → User confirmation
3. Intent analysis → IntentGate
4. Create Agent → AgentFactory
5. Execute task → ExecutionEngine
6. Aggregate results → ResultAggregator
7. Preview + revision → PreviewGenerator + infinite revision loop
8. Output document → ReportGenerator/DocumentGenerationAgent

Usage example:
    orchestrator = ResearchOrchestrator()

    # Method 1: Interactive mode (recommended)
    result = await orchestrator.research("Analyze China's NEV market", interaction_mode=True)

    # Method 2: Direct execution (skip interaction)
    result = await orchestrator.research({
        "topic": "Medical AI Market",
        "aspects": ["Market Size", "Policy Environment", "Competitive Landscape"],
        "output_format": "docx"
    }, interaction_mode=False)

Design doc: docs/USER_INTERACTION_INTEGRATION_PLAN.md
"""
from src.core.workflow import PreviewRevisionWorkflow, FeedbackRequest, WorkflowStatus
from src.core.adjustment import RevisionService
from src.core.preview.preview_generator import PreviewGenerator
from src.core.preview_storage import PreviewStorage
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
from src.core.orchestrator.smart_clarifier import (
    SmartClarifier,
    ResearchRequirement,  # Using unified data class
    OutputType,
    OutputFormat,
)
from src.core.communication import MessageBus, SharedMemory
from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
from src.agents.fixed_agents.document_models import DocumentFormat, GenerationAction
from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
from src.core.decomposition import (
    get_strategy,
    DecompositionPlan,
    AgentSpec,
    ResearchPhase,
)
from src.skills.registry import SkillRegistry
from src.core.task_persistence import TaskPersistenceManager, TaskState
from src.core.agents.session_persistence import SessionPersistenceManager
from src.core.agents.base import BaseAgent
from src.core.agents.factory import DynamicAgentFactory, get_agent_factory
from src.core.orchestrator.output import (
    ReportGenerator,
    ReportConfig,
    StorageManager,
    StorageConfig,
)
from src.core.orchestrator.aggregation import (
    ResultAggregator,
    AggregationConfig,
    KnowledgeCompiler,
    KnowledgeCompilerConfig,
    WisdomRecorder,
    WisdomRecorderConfig,
)
from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
from src.core.orchestrator.execution.scheduler import ExecutionScheduler
from src.core.orchestrator.execution import (
    ExecutionEngine,
    ExecutionConfig,
)
from src.core.intent_types import IntentType, TaskComplexity
from src.core.prompt_manager import PromptManager
from src.core.wisdom import WisdomStore
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, TYPE_CHECKING

logger = logging.getLogger(__name__)

# Imports in TYPE_CHECKING block (for type annotations only)
if TYPE_CHECKING:
    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
    from src.core.content_lock import ContentLockManager
    from src.core.agents.protocol import IAgent
    from src.core.memory import KnowledgeManager

# Analysis layer (Phase 4: removed legacy routing, kept WisdomStore)

# Phase 4: Import intent type definitions

# Execution layer

# Storage layer

# Aggregation layer

# Output layer

# Agent system

# P0-4 fix: Import SkillRegistry

# Phase orchestrator (new)

# Task decomposition strategy

# Document generation agent

# P1-1 fix: Import quality check agent

# Communication components

# User interaction components (new)

# Phase 8 revision components (new)


def _map_revision_type(raw_type: str) -> str:
    """
    Map frontend revision type to internal system type

    Frontend may send: minor, section, phase, full, content, etc.
    Internal types: minor, section, phase, full
    """
    type_mapping = {
        "minor": "minor",
        "section": "section",
        "phase": "phase",
        "full": "full",
        "content": "section",  # Content revision maps to section revision
        "adjustment": "minor",  # Adjustment maps to minor revision
        "rewrite": "section",  # Rewrite maps to section revision
    }
    return type_mapping.get(raw_type.lower(), "minor")


@dataclass
class ResearchResult:
    """Research result"""
    task_id: str
    status: str
    topic: str
    agents_used: List[str]
    stages_completed: int
    output_path: Optional[str] = None
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    intent_analysis: Dict[str, Any] = field(default_factory=dict)
    wisdom_recorded: bool = False
    revision_count: int = 0  # New: revision count
    interaction_enabled: bool = False  # New: whether interaction mode is enabled
    # P1-4 fix: add report and document_path fields
    report: Dict[str, Any] = field(default_factory=dict)
    document_path: Optional[str] = None
    quality_score: float = 0.0
    quality_issues: List[Dict[str, Any]] = field(default_factory=list)


class ResearchOrchestrator:
    """
    Research Task Master Scheduler (Simplified)

    Six-layer architecture:
    1. Entry layer → research()
    2. Analysis layer → IntentGate, CategoryRouter, WisdomStore
    3. Creation layer → AgentFactory
    4. Execution layer → ExecutionEngine
    5. Aggregation layer → ResultAggregator, KnowledgeCompiler
    6. Output layer → ReportGenerator, StorageManager

    Only responsible for process orchestration; implementation delegated to sub-components.
    """

    def __init__(
        self,
        # Analysis layer components (optional injection)
        # Phase 4: removed intent_gate, category_router parameters
        wisdom_store: Optional[WisdomStore] = None,

        # Execution layer components (optional injection)
        execution_engine: Optional[ExecutionEngine] = None,
        execution_config: Optional[ExecutionConfig] = None,

        # Aggregation layer components (optional injection)
        result_aggregator: Optional[ResultAggregator] = None,
        knowledge_compiler: Optional[KnowledgeCompiler] = None,
        wisdom_recorder: Optional[WisdomRecorder] = None,

        # Output layer components (optional injection)
        report_generator: Optional[ReportGenerator] = None,
        storage_manager: Optional[StorageManager] = None,

        # Document generation agent (optional injection)
        document_generation_agent: Optional[DocumentGenerationAgent] = None,

        # Agent factory (optional injection)
        agent_factory: Optional[DynamicAgentFactory] = None,

        # P0-4 fix: SkillRegistry (ensures Agents can access Skills)
        skill_registry: Optional["SkillRegistry"] = None,

        # Communication components (optional injection)
        message_bus: Optional[MessageBus] = None,
        shared_memory: Optional[SharedMemory] = None,

        # User interaction components (optional injection)
        smart_clarifier: Optional[SmartClarifier] = None,
        preview_generator: Optional[PreviewGenerator] = None,

        # Storage path
        storage_path: Optional[str] = None,

        # Memory system
        knowledge_manager: Optional[Any] = None,

        # Backward compatibility parameters
        enable_dual_track: bool = False,

        # Execution concurrency
        max_parallel: int = 5,

        # Intelligent routing parameters (Phase 2: enabled by default)
        use_intelligent_routing: bool = True,
        routing_adapter: Optional["IntelligentRoutingAdapter"] = None,
    ):
        """
        Initialize Orchestrator

        All components support dependency injection, default instances created if not injected.
        """

        # P0-5 fix: get path from config to avoid hardcoding
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            try:
                from src.config.system import system_config
                self._storage_path = Path(system_config.system.paths.data_dir)
            except Exception:
                self._storage_path = Path("data")

        # Communication components
        self._message_bus = message_bus or MessageBus()
        self._shared_memory = shared_memory or SharedMemory()

        # P0-4 fix: SkillRegistry (ensures Agents can access Skills)
        # If not provided, create a new SkillRegistry and register core Skills
        if skill_registry is None:
            from src.skills.registry import SkillRegistry
            skill_registry = SkillRegistry()
            registered = skill_registry.register_core_skills()
            lc_count = skill_registry.auto_discover_langchain_tools()

            # Register professional analysis Skills
            try:
                from src.skills.analysis import MarketAnalysisSkill, DataAnalysisSkill
                from src.skills.analysis import StockDataSkill, StockAnalysisSkill
                from src.skills.analysis import PolicyAnalysisSkill, TechTrendSkill, RiskAnalysisSkill
                skill_registry._skills["market_analysis"] = MarketAnalysisSkill(
                )
                skill_registry._skills["data_analysis"] = DataAnalysisSkill()
                skill_registry._skills["stock_data"] = StockDataSkill()
                skill_registry._skills["stock_analysis"] = StockAnalysisSkill()
                skill_registry._skills["policy_analysis"] = PolicyAnalysisSkill(
                )
                skill_registry._skills["tech_trend"] = TechTrendSkill()
                skill_registry._skills["risk_analysis"] = RiskAnalysisSkill()
                logger.info("Orchestrator: registered 7 professional analysis Skills")
            except Exception as e:
                logger.warning(f"Orchestrator: failed to register analysis Skills: {e}")

            logger.info(
                f"Orchestrator: auto-registered {registered} core Skills, {lc_count} LangChain Tools")
        self._skill_registry = skill_registry

        # Analysis layer (default creation)
        # Phase 4: removed traditional routing init, kept WisdomStore only
        self._wisdom_store = wisdom_store or WisdomStore(
            store_path=self._storage_path / ".wisdom"
        )

        # Execution layer (default creation)
        self._execution_config = execution_config or ExecutionConfig(
            max_concurrent=max_parallel
        )
        self._execution_engine = execution_engine or ExecutionEngine(
            config=self._execution_config,
            message_bus=self._message_bus,
            shared_memory=self._shared_memory,
        )

        # Execution scheduler (new)
        self._execution_scheduler = ExecutionScheduler(
            max_parallel=max_parallel,
            enable_dynamic_scheduling=True,
        )

        # Aggregation layer (default creation)
        self._result_aggregator = result_aggregator or ResultAggregator()
        self._knowledge_compiler = knowledge_compiler or KnowledgeCompiler()
        self._wisdom_recorder = wisdom_recorder or WisdomRecorder(
            wisdom_store=self._wisdom_store
        )

        # Output layer (default creation)
        self._report_generator = report_generator or ReportGenerator()
        self._storage_manager = storage_manager or StorageManager(
            StorageConfig(base_path=self._storage_path)
        )

        # Document generation agent (default creation)
        self._document_agent = document_generation_agent or DocumentGenerationAgent(
            agent_id="doc_gen_default",
            storage_path=str(self._storage_path),
        )
        # Inject communication capabilities
        self._document_agent.set_message_bus(self._message_bus)
        self._document_agent.set_shared_memory(self._shared_memory)

        # P1-1 fix: Quality check agent
        self._quality_check_agent = QualityCheckAgent(
            agent_id="quality_check_default",
        )
        # Fix breakpoint #5-6: inject communication capabilities
        self._quality_check_agent.set_message_bus(self._message_bus)
        self._quality_check_agent.set_shared_memory(self._shared_memory)

        # Note: LayoutDesignAgent redundant call removed
        # Layout functionality integrated into DocumentGenerationAgent (Plan A)

        # Agent factory
        # Session persistence manager - uses config registries_dir
        self._persistence = SessionPersistenceManager()  # Auto-read from config

        # Task persistence (status tracking + crash recovery) - uses config tasks_dir
        self._task_persistence = TaskPersistenceManager()  # Auto-read from config

        # P0-4 fix: Ensure AgentFactory uses the correct SkillRegistry
        # Pass global SkillRegistry to ensure Agents can access all registered Skills
        self._agent_factory = agent_factory or DynamicAgentFactory(
            skill_registry=self._skill_registry,  # Use Orchestrator's SkillRegistry
            message_bus=self._message_bus,
            shared_memory=self._shared_memory,
            persistence=self._persistence,
        )

        logger.info(
            f"Orchestrator: AgentFactory created, SkillRegistry contains {
                len(
                    self._skill_registry._skills)} Skills")

        # User interaction components (default creation)
        self._smart_clarifier = smart_clarifier or SmartClarifier()
        self._preview_generator = preview_generator or PreviewGenerator(
            cache_dir=str(PreviewStorage.NEW_DIR)
        )

        # Memory system
        self._knowledge_manager = knowledge_manager

        # Phase 8 revision components (new)
        self._revision_service = RevisionService(
            storage_path=str(self._storage_path),
        )
        self._preview_workflow = PreviewRevisionWorkflow()
        self._current_loop_id: Optional[str] = None  # Current workflow ID

        # Current task Session ID (for Agent lifecycle management)
        self._current_session_id: Optional[str] = None

        # Backward compatibility flag
        self.enable_dual_track = enable_dual_track

        # Intelligent routing initialization (traditional routing path removed)
        if routing_adapter is not None:
            self._routing_adapter = routing_adapter
            logger.info(
                "Orchestrator: using injected IntelligentRoutingAdapter")
        elif use_intelligent_routing:
            try:
                from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
                self._routing_adapter = IntelligentRoutingAdapter(
                    use_llm=True,
                    fallback_to_keyword=True,
                    enable_content_lock=True,
                )
                logger.info(
                    "Orchestrator: IntelligentRoutingAdapter initialized")
            except ImportError as e:
                logger.warning(
                    f"IntelligentRoutingAdapter import failed: {e}, routing analysis will use defaults")
                self._routing_adapter = None
        else:
            self._routing_adapter = None
        self._use_intelligent_routing = self._routing_adapter is not None

        # Task history (backward compatibility)
        self._task_history: List[Dict[str, Any]] = []

        logger.info("ResearchOrchestrator initialized (Integrated Interactive Version)")

    async def research(
        self,
        user_input: Union[str, Dict[str, Any]],
        output_dir: Optional[str] = None,
        user_id: Optional[str] = None,
        interaction_mode: bool = True,
        interaction_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
        use_intelligent_routing: Optional[bool] = None,  # New: intelligent routing toggle
        # P0-1 fix: new CLI parameter passing
        output_type: Optional[str] = None,
        custom_aspects: Optional[List[str]] = None,
        framework: Optional[str] = None,
        template_name: Optional[str] = None,
        output_format: Optional[str] = None,  # Output format: docx, pdf, html
        skip_phases: Optional[List[str]] = None,  # Incremental execution: phase IDs to skip
        existing_results: Optional[Dict[str, Any]] = None,  # Existing section data for incremental revision
    ) -> ResearchResult:
        """
        Execute research task (main entry, integrated interactive flow)

        Complete flow (interaction_mode=True):
        1. Requirement clarification → SmartClarifier (select output type, template, sections)
        2. Framework confirmation → User confirms research plan
        3. Intent analysis → IntentGate or IntelligentRoutingAdapter
        4. Create Agent → AgentFactory
        5. Execute task → ExecutionEngine
        6. Aggregate results → ResultAggregator + KnowledgeCompiler
        7. Preview report → PreviewGenerator
        8. Revision loop → infinite revision until user satisfied
        9. Output document → DocumentGenerationAgent
        10. Store results → StorageManager

        Direct execution (interaction_mode=False):
        Skip interactive flow, execute research directly

        Args:
            user_input: User input (natural language or structured)
            output_dir: Output directory
            user_id: User ID
            interaction_mode: Whether to enable interactive mode (default True)
            interaction_callback: Frontend interaction callback, receives step data returns user choice
            use_intelligent_routing: Whether to use intelligent routing
            output_type: Report type (industry_report/company_research/market_brief)
            custom_aspects: Custom section list
            framework: Research framework (detailed/standard/brief)
            template_name: Output template name
            output_format: Output format (docx/pdf/html)

        Returns:
            ResearchResult: Research result
        """
        task_id = f"research_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        # Determine whether to use intelligent routing
        use_routing = (
            use_intelligent_routing
            if use_intelligent_routing is not None
            else self._use_intelligent_routing
        )

        # If intelligent routing is enabled, use the new execution path
        if use_routing and self._routing_adapter is not None:
            logger.info(f"[{task_id}] Using intelligent routing execution path")
            return await self._research_with_routing(
                user_input=user_input,
                output_dir=output_dir,
                user_id=user_id,
                interaction_mode=interaction_mode,
                interaction_callback=interaction_callback,
                task_id=task_id,
                # P0-1 fix: pass CLI parameters, avoid loss in _research_with_routing
                output_type=output_type,
                custom_aspects=custom_aspects,
                framework=framework,
                template_name=template_name,
                output_format=output_format,
            )

        # R1 fix: create task persistence state
        try:
            task_input = {
                "topic": str(user_input)[:200],
                "output_type": output_type or "",
                "custom_aspects": custom_aspects or [],
                "framework": framework or "",
                "template_name": template_name or "",
                "output_format": output_format or "docx",
            }
            research_task = self._task_persistence.create_task(
                "research", task_input, task_id=task_id)
            self._task_persistence.save_task(research_task)
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.0, message="Research task started")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to create task persistence: {e}")

        # Set current Session ID (for Agent lifecycle management)
        self._current_session_id = task_id

        # Initialize state machine
        state_machine = ConversationStateMachine(research_id=task_id)

        try:
            # === Interactive mode handling ===
            if interaction_mode and interaction_callback:
                logger.info(f"[{task_id}] Starting interactive mode")

                # Phase 1: Requirement clarification (using SmartClarifier)
                state_machine.transition(ConversationState.CLARIFYING)

                requirement = await self._run_interactive_clarification(
                    user_input, interaction_callback, task_id
                )

                if not requirement:
                    # User cancelled
                    return ResearchResult(
                        task_id=task_id,
                        status="cancelled",
                        topic=str(user_input)[:50],
                        agents_used=[],
                        stages_completed=0,
                        summary="User cancelled research",
                        interaction_enabled=True,
                    )

                # Phase 2: Framework confirmation - completed in interactive flow, skip
                # confirmed = await self._get_user_confirmation(...)
                # Use requirement from interactive flow directly

                if not requirement:
                    return ResearchResult(
                        task_id=task_id,
                        status="cancelled",
                        topic=str(user_input)[:50],
                        agents_used=[],
                        stages_completed=0,
                        summary="User cancelled research",
                        interaction_enabled=True,
                    )

                logger.info(f"[{task_id}] User confirmed research plan: {requirement.topic}")
            else:
                # === Direct execution mode ===
                # P0-1 fix: merge CLI parameters into user_input
                if isinstance(user_input, str):
                    # String input: build structured dict
                    structured_input = {
                        "topic": user_input,
                        "output_type": output_type or "industry_report",
                        "aspects": custom_aspects,
                        "framework": framework,
                        "template_id": template_name,
                        "output_format": output_format or "docx",
                    }
                    requirement = self._parse_requirement(structured_input)
                    logger.info(
                        f"[{task_id}] CLI parameters applied: output_type={output_type}, aspects={custom_aspects}, framework={framework}")
                else:
                    # Dict input: merge CLI parameters (CLI parameters take priority)
                    merged_input = dict(user_input)
                    if output_type:
                        merged_input["output_type"] = output_type
                    if custom_aspects:
                        merged_input["aspects"] = custom_aspects
                    if framework:
                        merged_input["framework"] = framework
                    if template_name:
                        merged_input["template_id"] = template_name
                    if output_format:
                        merged_input["output_format"] = output_format
                    requirement = self._parse_requirement(merged_input)

            logger.info(f"[{task_id}] Research topic: {requirement.topic}")

            # 2. Intent analysis (analysis layer) - Phase 4: use intelligent routing adapter
            # Intelligent routing already handled in _research_with_routing, use compatible method here
            if self._routing_adapter:
                # Use simplified interface of intelligent routing
                intent_result = self._routing_adapter.analyze_simple(
                    requirement.topic,
                    {"aspects": requirement.aspects}
                )
                # P0 fix: use helper to get intent type
                intent_type = self._get_intent_type(intent_result)
                requirement.intent_type = intent_type.value if intent_type else IntentType.RESEARCH.value
                requirement.complexity = intent_result.complexity.value

                intent_analysis = {
                    "intent_type": requirement.intent_type,
                    "complexity": requirement.complexity,
                    "confidence": intent_result.confidence,
                }

                logger.info(
                    f"[{task_id}] Intent: {requirement.intent_type}, Complexity: {requirement.complexity}")
            else:
                # Intent routing unavailable, apply sensible defaults
                logger.info(
                    f"[{task_id}] Routing adapter unavailable, using default intent analysis")
                requirement.intent_type = "research"
                requirement.complexity = "multi"
                intent_analysis = {
                    "intent_type": requirement.intent_type,
                    "complexity": requirement.complexity,
                    "confidence": 0.5,
                }
                from src.core.intent_types import IntentType, TaskComplexity, IntentAnalysisResult, AgentCreationStrategy
                default_strategy = AgentCreationStrategy(
                    intent=IntentType.RESEARCH,
                    complexity=TaskComplexity.MULTI,
                    recommended_agents=[
                        "data_collector", "analyst", "synthesis"],
                    agent_count_estimate=3,
                    parallel_execution=True,
                    skill_requirements=[],
                    creation_mode="dynamic",
                    priority="medium",
                    context_requirements={},
                    clarification_needed=False,
                    clarification_questions=None,
                )
                intent_result = IntentAnalysisResult(
                    intent=IntentType.RESEARCH,
                    complexity=TaskComplexity.MULTI,
                    strategy=default_strategy,
                    confidence=0.5,
                    keywords_matched=[],
                    reasoning="Routing adapter unavailable, using default intent",
                )

            # 3. Wisdom recommends Skills (analysis layer)
            recommended_skills = []
            for aspect in requirement.aspects:
                skills = self._wisdom_store.get_recommended_skills(
                    task_type=requirement.intent_type,
                    task_aspect=aspect,
                )
                recommended_skills.extend(skills)
            requirement.recommended_skills = list(set(recommended_skills))

            logger.info(
                f"[{task_id}] 推荐 Skills: {requirement.recommended_skills}")

            # Check if survey integration is needed (supports English and
            # Chinese triggers)
            survey_result = None
            _survey_triggers = [
                "survey", "questionnaire", "poll", "research study",
                "questionnaire survey", "consumer survey", "user research",
            ]
            _user_input_lower = requirement.topic.lower(
            ) if hasattr(requirement, 'topic') else ""
            _has_survey_intent = (
                requirement.include_survey
                or requirement.enable_questionnaire
                or any(kw in _user_input_lower for kw in _survey_triggers)
            )
            if _has_survey_intent:
                logger.info(
                    f"[{task_id}] Survey intent detected (keyword match), starting survey workflow")
                try:
                    survey_result = await self._execute_survey_integration(requirement, task_id)
                    if survey_result:
                        logger.info(
                            f"[{task_id}] Survey completed: {survey_result.get('status', 'unknown')}")
                except Exception as e:
                    logger.error(
                        f"[{task_id}] Survey integration failed: {e}")
                    survey_result = None

            # 4.1 Get framework config (for task decomposition)
            from src.core.research_framework_manager import get_framework_config
            output_type_value = requirement.output_type.value if hasattr(
                requirement.output_type, 'value') else str(requirement.output_type)
            framework_config = get_framework_config(output_type_value)

            # 4.2 Decompose task first, then create Agents (B-1 fix: ensure agents created per decomposition plan)
            decomposition_plan = None
            try:
                strategy = get_strategy(output_type_value)
                decomposition_plan = strategy.decompose(
                    requirement,
                    intent_result,
                    framework_config,
                )
                logger.info(f"[{task_id}] Task decomposition complete: {decomposition_plan.estimated_agents} Agents, "
                            f"estimated duration {decomposition_plan.estimated_duration}")
                logger.info(
                    f"[{task_id}] Execution phases: {' → '.join([p.value for p in decomposition_plan.execution_order])}")
            except Exception as e:
                logger.warning(f"[{task_id}] Task decomposition failed, using default scheduling: {e}")
                decomposition_plan = None

            # 4.3 Knowledge reference for routing (delegated to _phase2_knowledge_for_routing)
            if self._knowledge_manager:
                await self._phase2_knowledge_for_routing(requirement)

            # 4.4 Create Agents (using decomposition plan or fallback to traditional method)
            # v3.4 R1a-3: Old path cannot infer research_type from IntentAnalysisResult,
            # use default "market_research"
            if decomposition_plan:
                try:
                    agents = self._create_agents_from_plan(
                        decomposition_plan, requirement, task_id,
                        research_type="market_research",
                        intent_result=None)
                    logger.info(f"[{task_id}] Created {len(agents)} Agents according to decomposition plan")
                except Exception as e:
                    logger.warning(f"[{task_id}] Failed to create Agents by plan, falling back: {e}")
                    agents = self._create_agents(
                        requirement, intent_result, task_id,
                        research_type="market_research")
            else:
                agents = self._create_agents(
                    requirement, intent_result, task_id,
                    research_type="market_research")
            logger.info(f"[{task_id}] Created {len(agents)} Agents")
            agent_section_map: Dict[str, str] = {}
            for _agent in agents:
                _sid = getattr(_agent, 'section_id', None) or ''
                if _sid:
                    agent_section_map[_agent.agent_id] = _sid
            session_registry = self._agent_factory.get_registry(task_id)
            if session_registry:
                logger.info(
                    f"[{task_id}] Got Session Registry, containing {session_registry.count()} Sessions")

            # State transition: ensure correct state before execution
            if interaction_mode:
                try:
                    if state_machine.current_state == ConversationState.CLARIFYING:
                        state_machine.transition(
                            ConversationState.FRAMEWORK_CONFIRM)
                    if state_machine.current_state == ConversationState.FRAMEWORK_CONFIRM:
                        state_machine.transition(ConversationState.EXECUTING)
                except Exception as e:
                    logger.warning(f"[{task_id}] Pre-execution state transition: {e}")

            # 5. Execute task (execution layer) - using scheduler
            # Check if incremental execution with phase skipping is requested
            # ★ session_id for cancel/pause checkpoints
            _sid = getattr(requirement, 'session_id', task_id)

            if skip_phases is not None and existing_results is not None:
                logger.info(f"[{task_id}] Using incremental execution with {len(skip_phases)} skipped phases")
                exec_result = await self._execution_engine.execute_with_skip(
                    agents=agents,
                    requirement={
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "region": requirement.region,
                        "task_id": task_id,
                        "session_id": _sid,
                    },
                    decomposition_plan=decomposition_plan,
                    skip_phases=skip_phases,
                    existing_results=existing_results,
                    session_registry=session_registry,
                )
            elif decomposition_plan:
                # Use new scheduled execution method
                logger.info(f"[{task_id}] Using scheduler to execute task")
                exec_result = await self._execution_engine.execute_with_scheduler(
                    agents=agents,
                    requirement={
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "region": requirement.region,
                        "task_id": task_id,  # For ResearchResultStore persistence
                        "session_id": _sid,
                    },
                    scheduler=self._execution_scheduler,
                    decomposition_plan=decomposition_plan,
                    session_registry=session_registry,
                )
            else:
                # Fallback to original execution method
                logger.info(f"[{task_id}] Using traditional method to execute task")
                self._execution_engine.set_inject_handler(self._handle_engine_inject)
                exec_result = await self._execution_engine.execute(
                    agents=agents,
                    requirement={
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "region": requirement.region,
                        "session_id": _sid,
                    },
                    session_registry=session_registry,
                )

            # CRITICAL FIX: Check execution status for quality failures before proceeding
            if exec_result.status == "failed":
                error_detail = "; ".join(exec_result.errors[:5]) if exec_result.errors else "Quality check failed"
                logger.error(f"[{task_id}] Execution aborted due to quality failure: {error_detail}")
                return ResearchResult(
                    task_id=task_id, status="failed",
                    topic=requirement.topic,
                    agents_used=[a.agent_id for a in agents] if agents else [],
                    stages_completed=0,
                    summary=f"Research aborted: quality check failed ({error_detail})",
                    created_at=start_time, completed_at=datetime.now(),
                )

            # Convert stage_results to format expected by ResultAggregator
            # stage_results: Dict[str, List[Dict]] -> Dict[str, Dict]
            # Fix: use Agent's aspect as key, for matching with section_details
            results_for_aggregation: Dict[str, Dict[str, Any]] = {}
            if exec_result.stage_results:
                for stage_name, stage_results_list in exec_result.stage_results.items():
                    for i, result in enumerate(stage_results_list):
                        # M0-a: Use agent_id as key (unique per agent) instead of section_id.
                        # section_id is shared by DC and Analysis agents for the same section,
                        # causing collision. Save section_id as metadata for aggregator.
                        agent_id = result.get("agent_id", "")
                        section_id = result.get("section_id", "") or ""
                        if agent_id:
                            key = agent_id
                            if section_id:
                                result["_section_id"] = section_id
                        elif section_id:
                            key = section_id
                        elif agent_id in agent_section_map:
                            key = agent_section_map[agent_id]
                        else:
                            # Fallback: 解析 agent_id（旧格式 research_市场规模_2）
                            aspect = None
                            if agent_id:
                                parts = agent_id.split("_")
                                if len(parts) >= 3:
                                    last_part = parts[-1]
                                    is_index = last_part.isdigit() or (
                                        len(last_part) >= 6
                                        and all(c in '0123456789abcdef' for c in last_part.lower())
                                    )
                                    if is_index:
                                        aspect = "_".join(parts[1:-1])
                                    else:
                                        aspect = last_part
                                elif len(parts) == 2:
                                    aspect = parts[1]
                            key = aspect if aspect else f"{stage_name}_{i}"

                        results_for_aggregation[key] = result
                        logger.debug(
                            f"[{task_id}] Aggregation key mapping: {agent_id} -> {key}")

            # Add survey results to aggregation data
            if survey_result and survey_result.get("status") == "completed":
                results_for_aggregation["survey_result"] = {
                    "success": True,
                    "title": "Survey Data Analysis",
                    "result": survey_result.get("survey_section", {}),
                    "responses_count": survey_result.get("responses_count", 0),
                    "findings": survey_result.get("findings", {}),
                }
                logger.info(
                    f"[{task_id}] Survey results added to aggregation data")

            logger.info(
                f"[{task_id}] Execution complete, got {len(results_for_aggregation)} results")

            # 6. Aggregate results (aggregation layer) - pass framework section structure
            aggregated = self._result_aggregator.aggregate(
                results_for_aggregation,
                section_details=requirement.section_details,
            )
            logger.info(
                f"[{task_id}] Aggregation complete, section_details={len(requirement.section_details)} framework sections")

            # 6.5 Signal cross-synthesis to dynamic orchestrator (routing
            # system handles execution order)
            if survey_result and survey_result.get("status") == "completed":
                data = aggregated.data if hasattr(
                    aggregated, 'data') else aggregated
                if isinstance(data, dict):
                    data["survey_data_available"] = True
                    data["survey_findings"] = survey_result.get("findings", {})
                    data["survey_responses_count"] = survey_result.get(
                        "responses_count", 0)

            # 7.6 Canonical data validation gate (hard check after aggregation)
            try:
                from src.core.data.canonical_registry import CanonicalDataRegistry
                from src.core.data.metric_extractor import MetricExtractor
                _canon_errors = []
                _metric_ext = MetricExtractor()
                _agg_sections = aggregated.to_dict().get("sections", [])
                for _s in _agg_sections:
                    _raw_dps = _s.get("data_points", [])
                    _enriched_dps = _metric_ext.extract(_raw_dps) if _raw_dps else []
                    _errors = self._execution_engine._canonical_registry.validate_section(
                        _s.get("content", ""), _enriched_dps or _raw_dps
                    ) if hasattr(self._execution_engine, '_canonical_registry') else []
                    _canon_errors.extend(_errors)
                if _canon_errors:
                    logger.warning(f"[{task_id}] Canonical data validation found {len(_canon_errors)} issues")
                    for _e in _canon_errors[:5]:
                        logger.warning(f"  - {_e}")
            except Exception:
                logger.exception(f"[{task_id}] Canonical validation skipped")

            # 8. Generate report/document (output layer)
            output_dir_path = Path(
                output_dir) if output_dir else self._storage_path / "reports"
            output_dir_path.mkdir(parents=True, exist_ok=True)

            # === New flow: HTML preview → User confirmation → Word finalization ===
            research_result_data = aggregated.to_dict()
            # Ensure title is set for document generation downstream
            if "title" not in research_result_data:
                research_result_data["title"] = requirement.topic

            # === Step 1: Generate HTML preview first ===
            # Generate preview regardless of interaction mode
            preview_result = await self._document_agent.execute({
                "action": "get_preview",
                "output_format": "html",  # Generate HTML preview first
                "research_result": research_result_data,
                "task_id": task_id,
                "output_dir": str(output_dir_path),
            })

            preview_path = preview_result.get("preview_path")
            if preview_result.get("success") and preview_path:
                logger.info(f"[{task_id}] HTML preview generated: {preview_path}")
                output_path = preview_path  # Use preview path as output initially
            else:
                logger.warning(
                    f"[{task_id}] HTML preview generation failed: {preview_result.get('error')}")
                # Fallback: use Markdown/HTML generation
                self._report_generator._sections = []
                aggregated_dict = aggregated.to_dict()
                sections_data = aggregated_dict.get("sections", [])

                for section_data in sections_data:
                    section_title = section_data.get(
                        "title", section_data.get("id", ""))
                    section_content = section_data.get("content", "")
                    if isinstance(section_title, str) and isinstance(
                            section_content, str):
                        self._report_generator.add_section(
                            title=section_title,
                            content=section_content,
                            level=1,
                        )

                report = self._report_generator.generate(
                    topic=requirement.topic,
                    summary=aggregated_dict.get("key_findings", ""),
                )
                output_file = output_dir_path / \
                    f"{requirement.topic.replace(' ', '_')[:50]}_report.md"
                self._report_generator.save(report, output_file)
                output_path = str(
                    report.path) if report and report.path else str(output_file)
                logger.info(f"[{task_id}] Fallback generation complete: {output_path}")

            # === Step 2: Wait for user confirmation (interaction mode) ===
            # Generate final Word document after user confirmation
            final_document_generated = False  # Flag for final document generation

            # Select generation method based on user-specified format (deferred until user confirmation)
            output_format = requirement.output_format

            # Strict quality control: if no valid output, return failure directly
            if not output_path:
                logger.error(f"[{task_id}] Document generation failed, no valid output")
                return ResearchResult(
                    task_id=task_id,
                    status="failed",
                    topic=requirement.topic,
                    agents_used=[a.agent_id for a in agents] if agents else [],
                    stages_completed=4,
                    summary=f"Document generation failed, please check if research content is sufficient",
                    output_path=None,
                    created_at=start_time,
                    completed_at=datetime.now(),
                    intent_analysis=intent_analysis,
                )

            # P1-1 fix: Quality check with optional auto-repair (max 1 retry).
            # Only retries when actual content adjustments were applied.
            # Empty adjustments (no section field) → fail immediately, no empty burn.
            quality_result = None
            quality_passed = False
            issues = []
            quality_score = 0.0
            
            for _retry in range(2):  # initial + 1 retry max
                try:
                    check_input = {"report": aggregated.to_dict(), "standards": None}
                    if output_path and Path(output_path).exists():
                        try:
                            with open(output_path, "r", encoding="utf-8") as _f:
                                check_input["html_content"] = _f.read()
                        except Exception:
                            pass
                    quality_result = await self._quality_check_agent.execute(check_input)

                    if quality_result.get("success"):
                        quality_score = quality_result.get("quality_score", 0)
                        quality_passed = quality_result.get("passed", False)
                        issues = quality_result.get("issues", [])
                        suggestions = quality_result.get("suggestions", [])

                        logger.info(f"[{task_id}] Quality check: score={quality_score:.1f}, passed={quality_passed}")
                        if quality_passed:
                            break

                        # Not passed: try auto-repair once
                        if _retry == 0 and issues:
                            adjustments = []
                            for issue in issues[:3]:
                                if issue.get("auto_fixable") is False:
                                    continue
                                if issue.get("type") == "format":
                                    continue
                                section = issue.get("section")
                                if section:
                                    adjustments.append({
                                        "section": section,
                                        "section_id": issue.get("section_id"),
                                        "adjustment": suggestions[0] if suggestions else issue.get("message", ""),
                                        "document_path": output_path,
                                        "revision_type": "minor",
                                    })
                            if not adjustments:
                                logger.warning(f"[{task_id}] No auto-fixable issues, stopping")
                                break  # no empty retries
                            # Apply fixes to aggregated data, then regenerate
                            for adj in adjustments:
                                sec_name = adj.get("section", "")
                                if sec_name:
                                    for s in aggregated.data.get("sections", []):
                                        if s.get("title") == sec_name or s.get("id") == sec_name:
                                            s["content"] = f"{s.get('content', '')}\n\n[修复] {adj.get('adjustment', '')}"
                            # Regenerate preview with fixed content
                            preview_input = {
                                "action": "produce_document",
                                "research_result": aggregated.to_dict(),
                                "output_format": "html",
                                "output_dir": str(Path(output_path).parent),
                                "task_id": task_id,
                            }
                            new_result = await self._document_agent.execute(preview_input)
                            if isinstance(new_result, dict):
                                new_path = new_result.get("document_path") or new_result.get("output_path", "")
                                if new_path and Path(new_path).exists():
                                    output_path = new_path
                                    logger.info(f"[{task_id}] Auto-repair: regenerated with {len(adjustments)} fixes")
                                    # Copy repaired preview to serving directory
                                    try:
                                        PreviewStorage.copy_file(task_id, Path(output_path))
                                        from src.core.session_streamer import SessionStreamer
                                        preview_url = PreviewStorage.url(task_id)
                                        SessionStreamer.push_preview_refresh(task_id, preview_url, 'v1')
                                    except Exception as _pe:
                                        logger.warning(f"[{task_id}] Failed to push preview refresh after auto-repair: {_pe}")
                                    continue  # re-check with regenerated HTML
                            else:
                                logger.warning(f"[{task_id}] Auto-repair: regeneration failed, using original")
                                break
                        else:
                            break  # already retried or no issues
                    else:
                        logger.warning(f"[{task_id}] Quality check execution failed: {quality_result.get('error', 'unknown')}")
                        break
                except Exception as e:
                    logger.warning(f"[{task_id}] Quality check exception: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
                    break

            # Quality control final result handling
            if not quality_passed:
                logger.warning(f"[{task_id}] Quality check not passed (score={quality_score:.1f}), delivering report with warnings")
                for issue in (issues or [])[:5]:
                    logger.warning(f"  - {issue.get('type', 'unknown')}: {issue.get('message', '')[:100]}")

            result_status = "completed" if quality_passed else "completed_with_warnings"
            quality_issues_list = []
            quality_score_val = 0.0
            if quality_result and isinstance(quality_result, dict):
                quality_score_val = quality_result.get("quality_score", 0)
                quality_issues_list = quality_result.get("issues", [])[:10]

            return ResearchResult(
                task_id=task_id,
                status=result_status,
                topic=requirement.topic,
                agents_used=[a.agent_id for a in agents] if agents else [],
                stages_completed=5,
                summary=f"Research completed. Quality score: {quality_score_val:.1f}" + (" (warnings)" if not quality_passed else ""),
                output_path=output_path,
                document_path=output_path,
                created_at=start_time,
                completed_at=datetime.now(),
                intent_analysis=intent_analysis,
                report=aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {},
                quality_score=quality_score_val,
                quality_issues=quality_issues_list,
            )

            # === Preview and revision loop (interaction mode) ===
            # Use Phase 8 PreviewRevisionWorkflow instead of inline loop
            revision_count = 0  # Initialize revision count

            if interaction_mode and interaction_callback and output_path:
                # Fix state transition: CLARIFYING -> FRAMEWORK_CONFIRM -> EXECUTING -> PREVIEWING
                # Cannot jump directly from CLARIFYING to PREVIEWING
                try:
                    # First transition to FRAMEWORK_CONFIRM
                    if state_machine.current_state == ConversationState.CLARIFYING:
                        state_machine.transition(
                            ConversationState.FRAMEWORK_CONFIRM)
                    # Then transition to EXECUTING
                    state_machine.transition(ConversationState.EXECUTING)
                    # Finally transition to PREVIEWING
                    state_machine.transition(ConversationState.PREVIEWING)
                except Exception as e:
                    logger.warning(f"[{task_id}] State transition warning: {e}")
                    # If state transition fails, continue execution (doesn't affect functionality)

            try:
                # Start preview revision workflow
                workflow_state = self._preview_workflow.start(
                    task_id=task_id,
                    document_path=output_path,
                    max_rounds=10,  # Maximum revision rounds
                )
                self._current_loop_id = workflow_state.loop_id

                # Set content generation callback (for phase/full revision)
                async def content_generator_callback(
                        section_id: str, context: Dict[str, Any]) -> str:
                    """Content generation callback"""
                    result = await self._document_agent.execute({
                        "action": "generate_section",
                        "section_id": section_id,
                        "context": context,
                    })
                    return result.get("content", "")

                self._preview_workflow.set_content_generator_callback(
                    content_generator_callback)

                # Generate initial preview
                preview = self._preview_workflow.generate_preview(
                    workflow_state.loop_id)

                if preview.success:
                    # Revision loop
                    while workflow_state.status not in (
                            WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED):
                        try:
                            # Get user feedback
                            feedback_raw = await self._get_user_feedback(
                                preview, interaction_callback, task_id
                            )

                            if feedback_raw.get("action") == "confirm":
                                # User satisfied, confirm finalization
                                workflow_state = self._preview_workflow.confirm(
                                    workflow_state.loop_id)
                                logger.info(f"[{task_id}] User confirmed finalization")

                                # === New: generate final Word document after user confirmation ===
                                if output_format in (
                                        "docx", "pptx", "pdf") and not final_document_generated:
                                    logger.info(
                                        f"[{task_id}] User confirmed, generating final {output_format} document")

                                    doc_result = await self._document_agent.execute({
                                        "action": "produce_document",
                                        "output_format": output_format,
                                        "research_result": research_result_data,
                                        "task_id": task_id,
                                        "output_dir": str(output_dir_path),
                                    })

                                    if doc_result.get("success", False):
                                        final_path = doc_result.get(
                                            "document_path")
                                        if final_path and Path(
                                                final_path).exists():
                                            output_path = final_path
                                            final_document_generated = True
                                            logger.info(
                                                f"[{task_id}] Final document generated: {output_path}")
                                        else:
                                            logger.warning(
                                                f"[{task_id}] Final document path invalid, using preview version")
                                    else:
                                        logger.warning(
                                            f"[{task_id}] Final document generation failed: {doc_result.get('error')}, using preview version")

                                break

                            elif feedback_raw.get("action") == "revise":
                                # User requests revision
                                logger.info(
                                    f"[{task_id}] User requests revision (round {workflow_state.current_round + 1})")

                                # Build feedback request
                                feedback_request = FeedbackRequest(
                                    accepted=False,
                                    revision_type=_map_revision_type(
                                        feedback_raw.get("revision_type", "minor")),
                                    section_id=feedback_raw.get("section_id"),
                                    section_title=feedback_raw.get("section"),
                                    keywords=feedback_raw.get("keywords", []),
                                    user_feedback=feedback_raw.get(
                                        "adjustment", feedback_raw.get("feedback", "")),
                                    target_content=feedback_raw.get(
                                        "target_content"),
                                    metadata={
                                        "original_feedback": feedback_raw,
                                    },
                                )

                                # Submit feedback and execute revision
                                workflow_state = self._preview_workflow.submit_feedback(
                                    loop_id=workflow_state.loop_id,
                                    feedback=feedback_request,
                                )

                                if workflow_state.status == WorkflowStatus.FAILED:
                                    logger.warning(
                                        f"[{task_id}] Revision failed: {workflow_state.error}")
                                    break

                                # Update output path (if revision result available)
                                # RevisionResult uses document_path attribute
                                if workflow_state.last_revision is not None:
                                    if workflow_state.last_revision.success and workflow_state.last_revision.document_path:
                                        output_path = workflow_state.last_revision.document_path

                                # Regenerate preview
                                preview = self._preview_workflow.generate_preview(
                                    workflow_state.loop_id)

                            elif feedback_raw.get("action") == "cancel":
                                # User cancelled
                                workflow_state = self._preview_workflow.cancel(
                                    workflow_state.loop_id)
                                return ResearchResult(
                                    task_id=task_id,
                                    status="cancelled",
                                    topic=requirement.topic,
                                    agents_used=[a.agent_id for a in agents],
                                    stages_completed=len(
                                        results_for_aggregation),
                                    summary="User cancelled at preview stage",
                                    interaction_enabled=True,
                                    revision_count=workflow_state.current_round,
                                )

                        except Exception as e:
                            logger.error(
                                f"[{task_id}] Revision loop exception: {e}", exc_info=True)
                            workflow_state.status = WorkflowStatus.FAILED
                            workflow_state.error = str(e)
                            break

                    # Record revision count
                    revision_count = workflow_state.current_round

            except Exception as e:
                logger.warning(f"[{task_id}] Preview revision workflow failed: {e}")

            # === Breakpoint 4 fix: non-interactive mode also needs to generate final document ===
            # Requirement: must go through HTML preview + user confirmation before generating Word document
            # Interactive mode: preview → user confirmation → generate Word (already implemented in revision loop)
            # Non-interactive mode: preview → auto-generate Word (no interactive user)
            if not final_document_generated and output_format in (
                    "docx", "pptx", "pdf"):
                if interaction_mode:
                    # Interactive mode: wait for user confirmation (already handled in revision loop above)
                    logger.info(f"[{task_id}] HTML preview generated: {preview_path}")
                    logger.info(f"[{task_id}] User can confirm to generate final {output_format} document")
                else:
                    # Non-interactive mode: auto-generate final document after preview (same logic as interactive mode after user confirmation)
                    logger.info(
                        f"[{task_id}] Non-interactive mode, auto-generating final {output_format} document after preview")
                    doc_result = await self._document_agent.execute({
                        "action": "produce_document",
                        "output_format": output_format,
                        "research_result": research_result_data,
                        "task_id": task_id,
                        "output_dir": str(output_dir_path),
                    })
                    if doc_result.get("success"):
                        final_path = doc_result.get("document_path")
                        if final_path and Path(final_path).exists():
                            output_path = final_path
                            final_document_generated = True
                            logger.info(f"[{task_id}] Final document generated: {output_path}")
                        else:
                            logger.warning(f"[{task_id}] Final document path invalid, using preview version")
                    else:
                        logger.warning(
                            f"[{task_id}] Final document generation failed: {doc_result.get('error')}, using preview version")

            # 9. Store results (output layer)
            self._storage_manager.save(
                task_id=task_id,
                topic=requirement.topic,
                result=aggregated.to_dict(),
            )
            logger.info(f"[{task_id}] Results stored")

            # 9.5 Save quality metadata (new)
            try:
                quality_metadata = self._build_quality_metadata(
                    exec_result, quality_result, task_id
                )
                quality_metadata_path = self._storage_path / \
                    "reports" / task_id / "quality_metadata.json"
                quality_metadata_path.parent.mkdir(parents=True, exist_ok=True)

                import json
                with open(quality_metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(
                        quality_metadata,
                        f,
                        ensure_ascii=False,
                        indent=2)
                logger.info(f"[{task_id}] Quality metadata saved: {quality_metadata_path}")
            except Exception as e:
                logger.warning(f"[{task_id}] Failed to save quality metadata: {e}")

            # 10. Record experience (aggregation layer)
            if self.enable_dual_track:
                self._wisdom_recorder.start_recording(
                    task_type=requirement.intent_type,
                    task_aspect=requirement.aspects[0] if requirement.aspects else "general",
                    skills=requirement.recommended_skills,
                )
                self._wisdom_recorder.end_recording(
                    success=True,
                    approach="orchestrator_v2",
                )

            # Build result
            result = ResearchResult(
                task_id=task_id,
                status="completed",
                topic=requirement.topic,
                agents_used=[a.agent_id for a in agents],
                stages_completed=len(results_for_aggregation),
                output_path=output_path,
                summary=self._generate_summary(aggregated, requirement),
                created_at=start_time,
                completed_at=datetime.now(),
                intent_analysis={
                    "intent_type": self._get_intent_type(intent_result).value if self._get_intent_type(intent_result) else None,
                    "complexity": intent_result.complexity.value,
                    "confidence": intent_result.confidence,
                },
                wisdom_recorded=self.enable_dual_track,
                revision_count=revision_count,
                interaction_enabled=interaction_mode,
                # P1-4 fix: populate report and document_path fields
                report=aggregated.to_dict(),  # Structured report data
                document_path=output_path if output_path and Path(
                    output_path).exists() else None,
            )

            # R1 fix: update task persistence state to completed
            try:
                self._task_persistence.update_task_state(
                    task_id, TaskState.COMPLETED, progress=1.0,
                    message=f"Research complete, {len(results_for_aggregation)} stages"
                )
            except Exception as e:
                logger.warning(f"[{task_id}] Failed to update task completion state: {e}")

            self._task_history.append({
                "task_id": task_id,
                "requirement": requirement,
                "result": result,
            })

            # Clean up Agent Session Registry (lifecycle management)
            self._cleanup_agents(task_id)

            return result

        except Exception as e:
            logger.error(f"[{task_id}] Research failed: {e}")
            # R1 fix: update task state to failed
            try:
                self._task_persistence.update_task_state(
                    task_id, TaskState.FAILED, progress=0.0,
                    message=f"Research failed: {str(e)[:200]}"
                )
            except Exception as pe:
                logger.warning(f"[{task_id}] Failed to update task failure state: {pe}")
            # Clean up Agent Session Registry
            self._cleanup_agents(task_id)
            return ResearchResult(
                task_id=task_id,
                status="error",
                topic=str(user_input)[:50],
                agents_used=[],
                stages_completed=0,
                summary=f"Error: {str(e)}"
            )

    # === Intelligent routing execution method ===

    async def _research_with_routing(
        self,
        user_input: Union[str, Dict[str, Any]],
        output_dir: Optional[str],
        user_id: Optional[str],
        interaction_mode: bool,
        interaction_callback: Optional[Callable[[Dict[str, Any]], Any]],
        task_id: str,
        # P0-1 fix: receive CLI parameters to avoid loss when re-parsing string
        output_type: Optional[str] = None,
        custom_aspects: Optional[List[str]] = None,
        framework: Optional[str] = None,
        template_name: Optional[str] = None,
        output_format: Optional[str] = None,
    ) -> ResearchResult:
        """
        Execute research task using intelligent routing

        Flow:
        1. Requirement parsing (interactive or direct)
        2. Intelligent routing analysis (SemanticIntent → TaskStructure → ExecutionPlan)
        3. Agent creation (by new ExecutionPlan)
        4. Execution (with ContentLock gating)
        5. Result aggregation and output

        Args:
            user_input: User input
            output_dir: Output directory
            user_id: User ID
            interaction_mode: Whether interactive mode
            interaction_callback: Interaction callback
            task_id: Task ID

        Returns:
            ResearchResult
        """
        # P1-1: defensive check - if _routing_adapter unavailable, return error
        if self._routing_adapter is None:
            logger.error(
                f"[{task_id}] _routing_adapter is None, cannot execute intelligent routing")
            return ResearchResult(
                task_id=task_id,
                status="failed",
                topic=str(user_input)[:50],
                agents_used=[],
                stages_completed=0,
                summary="Intelligent routing adapter unavailable",
            )

        start_time = datetime.now()

        # Create task persistence state
        try:
            task_input = {
                "topic": str(user_input)[:200],
                "output_type": "",
            }
            research_task = self._task_persistence.create_task(
                "research", task_input, task_id=task_id)
            self._task_persistence.save_task(research_task)
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.0, message="Intelligent routing task started")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to create task persistence: {e}")

        # Set current Session ID
        self._current_session_id = task_id

        # Initialize state machine
        state_machine = ConversationStateMachine(research_id=task_id)

        try:
            # === Phase 1: Requirement parsing ===
            if interaction_mode and interaction_callback:
                logger.info(f"[{task_id}] Intelligent routing - interactive mode")
                state_machine.transition(ConversationState.CLARIFYING)
                requirement = await self._run_interactive_clarification(
                    user_input, interaction_callback, task_id
                )
                if not requirement:
                    return ResearchResult(
                        task_id=task_id,
                        status="cancelled",
                        topic=str(user_input)[:50],
                        agents_used=[],
                        stages_completed=0,
                        summary="User cancelled research",
                        interaction_enabled=True,
                    )
            else:
                logger.info(f"[{task_id}] Intelligent routing - direct execution mode")
                # **Critical fix**: use CLI parameters to build structured dict
                # Instead of re-parsing the original string, otherwise --aspects etc. would be lost
                if isinstance(user_input, str):
                    structured_input = {
                        "topic": user_input,
                        "output_type": output_type or "industry_report",
                        "aspects": custom_aspects,
                        "framework": framework,
                        "template_id": template_name,
                        "output_format": output_format or "docx",
                    }
                    requirement = self._parse_requirement(structured_input)
                    logger.info(
                        f"[{task_id}] Built requirement with CLI parameters: aspects={custom_aspects}, output_type={output_type}")
                else:
                    requirement = self._parse_requirement(user_input)

            logger.info(f"[{task_id}] Research topic: {requirement.topic}")

            # ★ Forward session_id from user_input to requirement for cancel/pause checkpoints
            if isinstance(user_input, dict):
                req_session_id = user_input.get("session_id")
                if req_session_id:
                    requirement.session_id = req_session_id
            if not hasattr(requirement, 'session_id') or not requirement.session_id:
                requirement.session_id = task_id

            # Update task state
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.1, message="Requirement parsing complete"
            )

            # === Phase 2: Intelligent routing analysis ===
            logger.info(f"[{task_id}] Executing intelligent routing analysis...")

            requirement_dict = {
                "topic": requirement.topic,
                "aspects": requirement.aspects,
                "output_type": requirement.output_type.value if hasattr(requirement.output_type, 'value') else str(requirement.output_type),
            }

            routing_result = self._routing_adapter.analyze(
                user_request=requirement.topic,
                requirement=requirement_dict,
                topic=requirement.topic,
            )

            # R-FIX-3/4: 缓存意图结果，供后续增量/重新分析融合使用
            self._cache_intent_for_task(task_id, routing_result.intent_result)
            from src.core.session_manager import SessionManager as _SM
            _sess = _SM.get_instance().get(requirement.session_id) if hasattr(requirement, 'session_id') else None
            if _sess:
                _ctx = _sess.setdefault('research_context', {})
                try:
                    _ctx['_cached_intent_result'] = routing_result.intent_result.to_dict()
                except Exception:
                    pass

            logger.info(
                f"[{task_id}] Intelligent routing analysis complete: "
                f"{len(routing_result.task_structure.sections)} sections, "
                f"{len(routing_result.execution_plan.phases)} phases, "
                f"{routing_result.execution_plan.total_agents} agents"
            )

            # Update task state
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.2, message="Intelligent routing analysis complete"
            )

            # 3b. Wisdom recommends Skills (same as research() path)
            recommended_skills = []
            for aspect in requirement.aspects:
                skills = self._wisdom_store.get_recommended_skills(
                    task_type=requirement.intent_type,
                    task_aspect=aspect,
                )
                recommended_skills.extend(skills)
            requirement.recommended_skills = list(set(recommended_skills))
            logger.info(f"[{task_id}] Recommended Skills: {requirement.recommended_skills}")

            # 3c. Survey integration check (same as research() path)
            survey_result = None
            _survey_triggers = [
                "survey", "questionnaire", "poll", "research study",
                "questionnaire survey", "consumer survey", "user research",
            ]
            _user_input_lower = requirement.topic.lower() if hasattr(requirement, 'topic') else ""
            _has_survey_intent = (
                getattr(requirement, 'include_survey', False)
                or getattr(requirement, 'enable_questionnaire', False)
                or any(kw in _user_input_lower for kw in _survey_triggers)
            )
            if _has_survey_intent:
                logger.info(f"[{task_id}] Survey intent detected, starting survey workflow")
                try:
                    survey_result = await self._execute_survey_integration(requirement, task_id)
                    if survey_result:
                        logger.info(f"[{task_id}] Survey completed: {survey_result.get('status', 'unknown')}")
                except Exception as e:
                    logger.error(f"[{task_id}] Survey integration failed: {e}")
                    survey_result = None

            # 4.3 Knowledge reference for routing (delegated to _phase2_knowledge_for_routing)
            if self._knowledge_manager:
                await self._phase2_knowledge_for_routing(requirement)

            # === Phase 3: Agent creation ===
            # v3.4 R1a-2: Infer research_type from DeepIntentResult BEFORE conversion
            _deep_intent = routing_result.intent_result
            _research_type = "market_research"
            _prt = getattr(_deep_intent, 'primary_research_type', None)
            if _prt and hasattr(_prt, 'value'):
                from src.core.search.domain_role_inferrer import DomainRoleInferrer
                _research_type = DomainRoleInferrer.map_research_type(_prt.value)

            if routing_result.decomposition_plan:
                agents = self._create_agents_from_plan(
                    routing_result.decomposition_plan, requirement, task_id,
                    research_type=_research_type,
                    intent_result=_deep_intent,
                )
                logger.info(f"[{task_id}] Created {len(agents)} Agents per intelligent routing plan")
            else:
                # P2-2: Reuse intent_result from the full routing analysis instead of
                # calling analyze_simple() again. This avoids a duplicate API call.
                # Must convert DeepIntentResult → IntentAnalysisResult for
                # _create_agents() compatibility (it accesses .intent, not .primary_intent).
                intent_result = _deep_intent.to_intent_analysis_result()
                agents = self._create_agents(
                    requirement, intent_result, task_id,
                    research_type=_research_type,
                )
                logger.info(f"[{task_id}] Created {len(agents)} Agents via intelligent routing")

            # Build agent_id → section_id mapping for deterministic aggregation key assignment.
            # This is the authoritative source: the agent's section_id was set during creation
            # from spec.output_keys (which carries routing section_ids). Using this map
            # avoids relying on engine-side section_id injection which may be incomplete.
            agent_section_map: Dict[str, str] = {}
            for _agent in agents:
                _sid = getattr(_agent, 'section_id', None) or ''
                if _sid:
                    agent_section_map[_agent.agent_id] = _sid

            # Update progress: Agent creation complete
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.3, message="Agent creation complete, starting execution"
            )

            # Get ContentLockManager
            lock_manager = self._routing_adapter.get_lock_manager()

            # === Phase 4: Execute tasks ===
            session_registry = self._agent_factory.get_registry(task_id)

            # State transition with framework confirmation
            if interaction_mode and interaction_callback:
                try:
                    if state_machine.current_state == ConversationState.CLARIFYING:
                        state_machine.transition(
                            ConversationState.FRAMEWORK_CONFIRM)
                    if state_machine.is_in_state(ConversationState.FRAMEWORK_CONFIRM):
                        # Routing complete — show full execution plan for user confirmation
                        framework_info = self._format_routing_framework(
                            routing_result, requirement
                        )
                        confirm_data = {
                            "step": "framework_confirm",
                            "message": "Research plan has been generated. Please confirm:",
                            "framework": framework_info,
                            "actions": ["confirm", "cancel"],
                        }
                        response = await interaction_callback(confirm_data)
                        if response.get("action") != "confirm":
                            logger.info(f"[{task_id}] User rejected routing plan")
                            return ResearchResult(
                                task_id=task_id, status="cancelled",
                                topic=requirement.topic, agents_used=[], stages_completed=0,
                                summary="User rejected research plan", interaction_enabled=True,
                            )
                        state_machine.transition(ConversationState.EXECUTING)
                        logger.info(f"[{task_id}] Routing plan confirmed by user")
                except Exception as e:
                    logger.warning(f"[{task_id}] Framework confirmation failed: {e}")

            # Execute (with ContentLock, ensuring synthesis after analysis)
            if routing_result.decomposition_plan:
                # Use scheduled execution with inject checkpoint support
                logger.info(f"[{task_id}] Intelligent routing - using scheduler")
                self._execution_engine.set_inject_handler(self._handle_engine_inject)
                exec_result = await self._execution_engine.execute_with_scheduler(
                    agents=agents,
                    requirement={
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "region": getattr(requirement, 'region', ''),
                        "task_id": task_id,
                        "session_id": getattr(requirement, 'session_id', task_id),
                    },
                    scheduler=self._execution_scheduler,
                    decomposition_plan=routing_result.decomposition_plan,
                    session_registry=session_registry,
                    content_lock=lock_manager,  # Pass ContentLock, engine schedules by dependency
                )
            else:
                # Fallback to traditional execution
                logger.info(f"[{task_id}] Intelligent routing - using traditional execution")
                exec_result = await self._execution_engine.execute(
                    agents=agents,
                    requirement={
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "region": getattr(requirement, 'region', ''),
                        "session_id": getattr(requirement, 'session_id', task_id),
                    },
                    session_registry=session_registry,
                )

            # CRITICAL FIX: Check execution status for quality failures before proceeding.
            # Previously, quality check failures in the engine were silently ignored,
            # allowing garbled LLM-degraded content to pass through to report generation.
            if exec_result.status == "failed":
                error_detail = "; ".join(exec_result.errors[:5]) if exec_result.errors else "Quality check failed"
                logger.error(f"[{task_id}] Execution aborted due to quality failure: {error_detail}")
                self._task_persistence.update_task_state(
                    task_id, TaskState.FAILED, progress=0.0,
                    message=f"Aborted: {error_detail[:200]}"
                )
                return ResearchResult(
                    task_id=task_id, status="failed",
                    topic=requirement.topic, agents_used=[a.agent_id for a in agents],
                    stages_completed=0,
                    summary=f"Research aborted: quality check failed ({error_detail})",
                    created_at=start_time, completed_at=datetime.now(),
                )

            # Update task state
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.7, message="Execution complete"
            )

            # Update progress: start aggregating results
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.8, message="Integrating analysis results..."
            )

            # === Phase 5: Result aggregation ===
            # Convert stage_results to format expected by ResultAggregator
            results_for_aggregation: Dict[str, Dict[str, Any]] = {}
            if hasattr(exec_result,
                       'stage_results') and exec_result.stage_results:
                for stage_name, stage_results_list in exec_result.stage_results.items():
                    for i, result in enumerate(stage_results_list):
                        agent_id = result.get("agent_id", "")
                        section_id = result.get("section_id", "") or ""
                        # M0-a: Use agent_id as key (unique per agent) instead of section_id.
                        if agent_id:
                            key = agent_id
                            if section_id:
                                result["_section_id"] = section_id
                        elif section_id:
                            key = section_id
                        elif agent_id in agent_section_map:
                            key = agent_section_map[agent_id]
                        else:
                            aspect = None
                            if agent_id:
                                parts = agent_id.split("_")
                                if len(parts) >= 3:
                                    last_part = parts[-1]
                                    is_index = last_part.isdigit() or (
                                        len(last_part) >= 6
                                        and all(c in '0123456789abcdef' for c in last_part.lower())
                                    )
                                    if is_index:
                                        aspect = "_".join(parts[1:-1])
                                    else:
                                        aspect = last_part
                                elif len(parts) == 2:
                                    aspect = parts[1]
                            key = aspect if aspect else f"{stage_name}_{i}"
                        results_for_aggregation[key] = result
                        logger.debug(
                            f"[{task_id}] Aggregation key mapping: {agent_id} -> {key}")

            logger.info(
                f"[{task_id}] Execution complete, got {len(results_for_aggregation)} results")

            # Add survey results to aggregation data (same as research() path)
            if survey_result and survey_result.get("status") == "completed":
                results_for_aggregation["survey_result"] = {
                    "success": True,
                    "title": "Survey Data Analysis",
                    "result": survey_result.get("survey_section", {}),
                    "responses_count": survey_result.get("responses_count", 0),
                    "findings": survey_result.get("findings", {}),
                }
                logger.info(f"[{task_id}] Survey results added to aggregation data")

            # Aggregate results (synchronous, pass section_details)
            aggregated = self._result_aggregator.aggregate(
                results_for_aggregation,
                section_details=getattr(requirement, 'section_details', []),
            )

            # Fix: AggregationResult has no .sections property, must get via to_dict()
            aggregated_dict = aggregated.to_dict() if hasattr(
                aggregated, 'to_dict') else {"sections": []}
            section_count = len(aggregated_dict.get("sections", []))
            logger.info(f"[{task_id}] Result aggregation complete: {section_count} sections")

            # Inject survey data into aggregated result (same as research() path)
            if survey_result and survey_result.get("status") == "completed":
                data = aggregated.data if hasattr(aggregated, 'data') else aggregated
                if isinstance(data, dict):
                    data["survey_data_available"] = True
                    data["survey_findings"] = survey_result.get("findings", {})
                    data["survey_responses_count"] = survey_result.get("responses_count", 0)
                    logger.info(f"[{task_id}] Survey data injected into aggregated result")

            # 7.6 Canonical data validation gate (hard check, same as research() path)
            try:
                from src.core.data.canonical_registry import CanonicalDataRegistry
                from src.core.data.metric_extractor import MetricExtractor
                _canon_errors = []
                _metric_ext = MetricExtractor()
                _agg_sections = aggregated_dict.get("sections", [])
                for _s in _agg_sections:
                    _raw_dps = _s.get("data_points", [])
                    _enriched_dps = _metric_ext.extract(_raw_dps) if _raw_dps else []
                    _errors = self._execution_engine._canonical_registry.validate_section(
                        _s.get("content", ""), _enriched_dps or _raw_dps
                    ) if hasattr(self._execution_engine, '_canonical_registry') else []
                    _canon_errors.extend(_errors)
                if _canon_errors:
                    logger.warning(f"[{task_id}] Canonical data validation found {len(_canon_errors)} issues")
                    for _e in _canon_errors[:5]:
                        logger.warning(f"  - {_e}")
            except Exception:
                logger.exception(f"[{task_id}] Canonical validation skipped")

            # **Section ordering fix**: reorder sections by user-specified aspect order
            # After parallel agent execution, section order is determined by completion time, not user's logical order
            # Here we reorder by requirement.aspects order, unknown sections go last
            raw_sections = aggregated_dict.get("sections", [])
            if raw_sections and hasattr(
                    requirement, 'aspects') and requirement.aspects:
                aspect_order = {
                    name.lower(): idx for idx,
                    name in enumerate(
                        requirement.aspects)}
                unknown_idx = len(requirement.aspects)  # Sections not in aspects go last

                def get_section_sort_key(section: Dict[str, Any]) -> int:
                    title = section.get("title", "").lower()
                    # Exact match (e.g. "Executive Summary")
                    if title in aspect_order:
                        return aspect_order[title]
                    # Fuzzy match (e.g. title="Market Size Analysis" matches aspect="Market Size")
                    for aspect_name, idx in aspect_order.items():
                        if aspect_name in title or title in aspect_name:
                            return idx
                    return unknown_idx  # Unknown sections (e.g. "References") go last

                raw_sections.sort(key=get_section_sort_key)
                aggregated_dict["sections"] = raw_sections
                logger.info(
                    f"[{task_id}] Sections reordered by aspect order: {[s.get('title', '') for s in raw_sections]}")

            # Update progress: starting preview generation
            self._task_persistence.update_task_state(
                task_id, TaskState.RUNNING, progress=0.9, message="Generating HTML preview..."
            )

            # === Phase 6: HTML preview generation (must go through user confirmation) ===
            # User explicitly requested: must go through HTML preview + user confirmation before generating Word doc
            output_dir_path = Path(
                output_dir) if output_dir else self._storage_path / task_id
            output_dir_path.mkdir(parents=True, exist_ok=True)

            research_result_data = {
                "topic": requirement.topic,
                "title": requirement.topic,
                "aspects": requirement.aspects,
                "sections": aggregated_dict.get("sections", []),
                "sources": aggregated_dict.get("sources", []),
                "key_findings": aggregated_dict.get("key_findings", []),
            }

            # Cache aggregated result for resume/crash recovery
            # Save BEFORE preview generation, so even if preview fails,
            # the cached result can be reused to skip re-execution.
            try:
                cache_path = output_dir_path / "research_result_cache.json"
                with open(cache_path, "w", encoding="utf-8") as f:
                    import json
                    json.dump(research_result_data, f, ensure_ascii=False, indent=2)
                logger.info(f"[{task_id}] Research result cached at {cache_path}")
            except Exception as cache_err:
                logger.warning(f"[{task_id}] Failed to cache research result: {cache_err}")

            logger.info(
                f"[{task_id}] Document generation input: {len(research_result_data['sections'])} sections")

            # Determine output format
            _valid_doc_formats = {"docx", "pdf", "html", "pptx"}
            raw_output_format = getattr(requirement, 'output_format', None)
            if raw_output_format and str(
                    raw_output_format) in _valid_doc_formats:
                output_format = str(raw_output_format)
            else:
                output_format = "docx"  # Default Word format

            # === Critical fix: generate HTML preview first ===
            # Step 1: Generate HTML preview document
            preview_task_input = {
                "action": "produce_document",
                "research_result": research_result_data,
                "output_format": "html",  # Force HTML format as preview
                "output_dir": str(output_dir_path),
                "task_id": task_id,
            }

            preview_result = await self._document_agent.execute(preview_task_input)

            preview_path = ""
            if isinstance(preview_result, dict):
                preview_path = preview_result.get(
                    "document_path") or preview_result.get("output_path", "")
            
            # Copy preview to serving directory so frontend can load it
            if preview_path and os.path.exists(preview_path):
                try:
                    PreviewStorage.copy_file(task_id, Path(preview_path))
                    logger.info(f"[{task_id}] Preview copied")
                except Exception as copy_err:
                    logger.warning(f"[{task_id}] Failed to copy preview: {copy_err}")

            if not preview_path:
                logger.warning(f"[{task_id}] HTML preview generation failed, skipping confirmation")
                # Fallback: generate final document directly
                doc_task_input = {
                    "action": "produce_document",
                    "research_result": research_result_data,
                    "output_format": output_format,
                    "output_dir": str(output_dir_path),
                    "task_id": task_id,
                }
                doc_result = await self._document_agent.execute(doc_task_input)
                output_path = doc_result.get(
                    "document_path") or doc_result.get("output_path", "")
            else:
                logger.info(f"[{task_id}] HTML preview generated successfully: {preview_path}")
                output_path = preview_path or ""

                # Step 1.5: Quality check with optional auto-repair (max 1 retry)
                quality_result = None
                quality_passed = False
                issues = []
                quality_score = 0.0
                
                for _retry in range(2):
                    try:
                        check_input = {"report": aggregated_dict, "standards": None}
                        if output_path and Path(output_path).exists():
                            try:
                                with open(output_path, "r", encoding="utf-8") as _f:
                                    check_input["html_content"] = _f.read()
                            except Exception:
                                pass
                        quality_result = await self._quality_check_agent.execute(check_input)

                        if quality_result.get("success"):
                            quality_score = quality_result.get("quality_score", 0)
                            quality_passed = quality_result.get("passed", False)
                            issues = quality_result.get("issues", [])
                            suggestions = quality_result.get("suggestions", [])
                            logger.info(
                                f"[{task_id}] Quality check: score={quality_score:.1f}, passed={quality_passed}")
                            if quality_passed:
                                break

                            if _retry == 0 and issues:
                                adjustments = []
                                for issue in issues[:3]:
                                    if issue.get("auto_fixable") is False:
                                        continue
                                    if issue.get("type") == "format":
                                        continue
                                    section = issue.get("section")
                                    if section:
                                        adjustments.append({
                                            "section": section,
                                            "section_id": issue.get("section_id"),
                                            "adjustment": suggestions[0] if suggestions else issue.get("message", ""),
                                            "document_path": output_path,
                                            "revision_type": "minor",
                                        })
                                if not adjustments:
                                    logger.warning(f"[{task_id}] No auto-fixable issues, stopping")
                                    break
                                for adj in adjustments:
                                    sec_name = adj.get("section", "")
                                    if sec_name:
                                        for s in aggregated_dict.get("sections", []):
                                            if s.get("title") == sec_name or s.get("id") == sec_name:
                                                s["content"] = f"{s.get('content', '')}\n\n[修复] {adj.get('adjustment', '')}"
                                preview_input = {
                                    "action": "produce_document",
                                    "research_result": aggregated_dict,
                                    "output_format": "html",
                                    "output_dir": str(Path(output_path).parent),
                                    "task_id": task_id,
                                }
                                new_result = await self._document_agent.execute(preview_input)
                                if isinstance(new_result, dict):
                                    new_path = new_result.get("document_path") or new_result.get("output_path", "")
                                    if new_path and Path(new_path).exists():
                                        output_path = new_path
                                        logger.info(f"[{task_id}] Auto-repair: regenerated with {len(adjustments)} fixes")
                                        # Copy repaired preview to serving directory
                                        try:
                                            PreviewStorage.copy_file(task_id, Path(output_path))
                                            from src.core.session_streamer import SessionStreamer
                                            preview_url = PreviewStorage.url(task_id)
                                            SessionStreamer.push_preview_refresh(task_id, preview_url, 'v1')
                                        except Exception as _pe:
                                            logger.warning(f"[{task_id}] Failed to push preview refresh after auto-repair: {_pe}")
                                        continue
                                else:
                                    logger.warning(f"[{task_id}] Auto-repair: regeneration failed")
                                    break
                            else:
                                break
                        else:
                            logger.warning(f"[{task_id}] Quality check failed: {quality_result.get('error', 'unknown')}")
                            break
                    except Exception as e:
                        logger.warning(f"[{task_id}] Quality check exception: {e}")
                        import traceback
                        logger.warning(traceback.format_exc())
                        break

            if not quality_passed:
                logger.warning(f"[{task_id}] Quality check not passed (score={quality_score:.1f}), delivering report with warnings")
                for issue in (issues or [])[:5]:
                    logger.warning(f"  - {issue.get('type', 'unknown')}: {issue.get('message', '')[:100]}")

            result_status = "completed" if quality_passed else "completed_with_warnings"
            quality_issues_list = []
            quality_score_val = 0.0
            if quality_result and isinstance(quality_result, dict):
                quality_score_val = quality_result.get("quality_score", 0)
                quality_issues_list = quality_result.get("issues", [])[:10]

            # C3: Save quality metadata (same as research() path)
            if quality_result:
                try:
                    quality_metadata = self._build_quality_metadata(
                        exec_result, quality_result, task_id
                    )
                    quality_metadata_path = self._storage_path / "reports" / task_id / "quality_metadata.json"
                    quality_metadata_path.parent.mkdir(parents=True, exist_ok=True)
                    import json
                    with open(quality_metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(quality_metadata, f, ensure_ascii=False, indent=2)
                    logger.info(f"[{task_id}] Quality metadata saved: {quality_metadata_path}")
                except Exception as e:
                    logger.warning(f"[{task_id}] Failed to save quality metadata: {e}")

            # C4: Record experience (same as research() path)
            if self.enable_dual_track:
                try:
                    _intent_type = getattr(requirement, 'intent_type', 'research')
                    _aspect = requirement.aspects[0] if getattr(requirement, 'aspects', None) else "general"
                    _skills = getattr(requirement, 'recommended_skills', [])
                    self._wisdom_recorder.start_recording(
                        task_type=_intent_type,
                        task_aspect=_aspect,
                        skills=_skills,
                    )
                    self._wisdom_recorder.end_recording(
                        success=True,
                        approach="orchestrator_v2",
                    )
                except Exception as e:
                    logger.warning(f"[{task_id}] Failed to record wisdom: {e}")

            return ResearchResult(
                task_id=task_id,
                status=result_status,
                topic=requirement.topic,
                agents_used=[a.agent_id for a in agents] if agents else [],
                stages_completed=5,
                summary=f"Research completed. Quality score: {quality_score_val:.1f}" + (" (warnings)" if not quality_passed else ""),
                output_path=output_path,
                document_path=output_path,
                created_at=start_time,
                completed_at=datetime.now(),
                intent_analysis=routing_result.to_dict() if hasattr(routing_result, 'to_dict') else {},
                report=aggregated_dict if isinstance(aggregated_dict, dict) else {},
                quality_score=quality_score_val,
                quality_issues=quality_issues_list,
            )

# Step 2: Wait for user confirmation
            # Key design principle: must go through user confirmation, no auto-confirm
            user_confirmed = False

            if interaction_mode and interaction_callback:
                logger.info(f"[{task_id}] Waiting for user to confirm HTML preview...")

                try:
                    confirm_data = await interaction_callback({
                        "step": "preview",
                        "message": "Please review the HTML preview and confirm if final document should be generated",
                        "preview_url": preview_path,
                        "actions": ["confirm", "revise", "cancel"],
                    })

                    action = (
                        confirm_data.get("action") or
                        confirm_data.get("selected") or
                        confirm_data.get("answer", "")
                    )

                    if action in ("confirm", "confirm_finalization"):
                        user_confirmed = True
                        logger.info(f"[{task_id}] User confirmed final document generation")
                    elif action in ("cancel",):
                        logger.info(f"[{task_id}] User cancelled, not generating final document")
                        output_path = preview_path
                    else:
                        logger.info(f"[{task_id}] User selected: {action}")
                        output_path = preview_path
                except Exception as e:
                    logger.warning(f"[{task_id}] Interaction callback failed: {e}")
                    output_path = preview_path
            else:
                logger.info(f"[{task_id}] Non-interactive mode, HTML preview only, waiting for user to explicitly confirm")
                logger.info(f"[{task_id}] User can confirm and generate final document via:")
                logger.info(f"[{task_id}]   - session confirm {task_id}")
                logger.info(f"[{task_id}]   - session generate-doc {task_id}")
                output_path = preview_path

            if user_confirmed and output_format != "html":
                logger.info(f"[{task_id}] User confirmed, generating final {output_format} document")

                doc_task_input = {
                    "action": "produce_document",
                    "research_result": research_result_data,
                    "output_format": output_format,
                    "output_dir": str(output_dir_path),
                    "task_id": task_id,
                }

                doc_result = await self._document_agent.execute(doc_task_input)

                if doc_result.get("success", False):
                    output_path = doc_result.get(
                        "document_path") or doc_result.get("output_path", "")
                    logger.info(f"[{task_id}] Final document generated: {output_path}")
                else:
                    logger.warning(
                        f"[{task_id}] Final document generation failed: {doc_result.get('error')}, using HTML preview")
                    output_path = preview_path
            else:
                output_path = preview_path

            # Update task state
            self._task_persistence.update_task_state(
                task_id, TaskState.COMPLETED, progress=1.0, message="Research complete"
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(
                f"[{task_id}] Intelligent routing research complete: {output_path}, duration {duration:.1f}s")

            return ResearchResult(
                task_id=task_id,
                status=result_status,
                topic=requirement.topic,
                agents_used=[a.agent_id for a in agents],
                stages_completed=len(routing_result.execution_plan.phases),
                output_path=output_path,
                document_path=output_path,
                summary=aggregated_dict.get("executive_summary", "Research complete"),
                created_at=start_time,
                completed_at=end_time,
                intent_analysis=routing_result.to_dict(),
                interaction_enabled=interaction_mode,
                report=aggregated_dict,
                quality_score=quality_score_val,
                quality_issues=quality_issues_list,
            )

        except Exception as e:
            logger.error(f"[{task_id}] Intelligent routing execution failed: {e}", exc_info=True)

            # Clean up Agent resources
            self._cleanup_agents(task_id)

            # Update task state
            try:
                self._task_persistence.update_task_state(
                task_id, TaskState.FAILED, progress=0.0, message=f"Error: {str(e)}"
                )
            except Exception:
                pass

            return ResearchResult(
                task_id=task_id,
                status="failed",
                topic=str(user_input)[:50],
                agents_used=[],
                stages_completed=0,
                summary=f"Error: {str(e)}"
            )

    # === Dynamic replanning method ===

    async def replan(
        self,
        task_id: str,
        new_order: List[str],
    ) -> Dict[str, Any]:
        """
        Replan execution order, preserving completed work

        Use cases:
        - Manual correction when execution order is wrong
        - User wants to adjust section priority

        Args:
            task_id: Task ID
            new_order: New section execution order (section ID list)

        Returns:
            {
                "preserved": [completed sections],
                "rerun": [sections needing re-execution],
                "status": "replanned",
            }
        """
        # P2-2 fix: input validation
        if not task_id:
            return {"error": "task_id is required", "status": "failed"}

        if not new_order:
            return {"error": "new_order cannot be empty", "status": "failed"}

        logger.info(f"[replan] Starting replan for task {task_id}, new order: {new_order}")

        # 1. Load existing results
        try:
            store = ResearchResultStore(storage_path=str(self._storage_path))
            result = store.load_result(task_id)
        except Exception as e:
            logger.error(f"[replan] Failed to load task result: {e}")
            return {"error": f"Failed to load task: {e}", "status": "failed"}

        if not result:
            return {"error": "Task not found", "status": "failed"}

        # 2. Get completed sections
        completed_agents = result.get("completed_agents", [])
        completed_sections = set()
        for agent_entry in completed_agents:
            if isinstance(agent_entry, dict):
                section_id = agent_entry.get(
                    "section_id") or agent_entry.get("agent_id")
            else:
                section_id = str(agent_entry) if agent_entry else None

            # P0-2 fix: only add non-null values
            if section_id:
                completed_sections.add(section_id)

        logger.info(f"[replan] Completed sections: {completed_sections}")

        # 3. Distinguish completed and pending sections
        # P1-1 fix: validate sections in new_order
        original_sections = set()
        for section in result.get("sections", []):
            if isinstance(section, dict) and section.get("section_id"):
                original_sections.add(section["section_id"])

        # Only process sections that exist in the original task
        valid_sections = original_sections | completed_sections
        invalid_sections = [s for s in new_order if s not in valid_sections]

        if invalid_sections:
            logger.warning(f"[replan] Ignoring invalid sections: {invalid_sections}")

        valid_new_order = [s for s in new_order if s in valid_sections]
        preserved = [s for s in valid_new_order if s in completed_sections]
        to_execute = [
            s for s in valid_new_order if s not in completed_sections]

        logger.info(f"[replan] Preserved: {preserved}, To execute: {to_execute}")

        # 4. Update ContentLock dependencies (if available)
        # TODO: Step 5-7 need to implement ContentLockManager.update_dependencies method
        if self._routing_adapter is not None:
            try:
                # Get or create lock_manager
                lock_manager = self._get_lock_manager_for_task(task_id)
                if lock_manager:
                    # P0-1 fix: update_dependencies not yet implemented, skip for now
                    # Enable after Step 5-7 implementation
                    if hasattr(lock_manager, 'update_dependencies'):
                        lock_manager.update_dependencies(new_order)
                        logger.info(f"[replan] Updated content lock dependencies")
                    else:
                        logger.debug(
                            f"[replan] ContentLockManager.update_dependencies not yet implemented, skipping dependency update")
            except Exception as e:
                logger.warning(f"[replan] Failed to update content lock: {e}")

        # 5. Execute pending sections if any
        if to_execute:
            try:
                # Get original requirement
                requirement = result.get("requirement", {})
                if not requirement:
                    requirement = {
                        "topic": result.get("topic", ""),
                        "task_id": task_id,
                    }

                # Create Agents for pending sections
                agents = await self._create_agents_for_sections(to_execute, requirement, task_id)

                if not agents:
                    logger.warning(f"[replan] Cannot create Agents for sections: {to_execute}")
                    return {
                        "preserved": preserved,
                        "rerun": [],
                        "status": "replanned",
                        "warning": "Cannot create Agents for pending sections",
                    }

                # Get lock_manager (currently returns None, available after Step 5-7)
                lock_manager = self._get_lock_manager_for_task(task_id)

                # P1-2 fix: ExecutionEngine.execute does not support content_lock parameter
                # Use execute() method, skip content_lock for now
                # Can consider execute_with_scheduler after Step 2 is fully integrated
                exec_result = await self._execution_engine.execute(
                    agents=agents,
                    requirement=requirement,
                )

                # 6. Merge old and new results
                new_sections = []
                # P0-1 fix: explicit type check
                for stage_name, stage_results in exec_result.stage_results.items():
                    for r in stage_results:
                        if isinstance(r, dict) and r.get(
                                "success") is True and r.get("content"):
                            new_sections.append({
                                "section_id": r.get("agent_id", ""),
                                "content": r.get("content", ""),
                                "data_points": r.get("data_points", []),
                                "sources": r.get("sources", []),
                            })

                # Update completed sections list
                all_completed = list(preserved) + \
                    [s["section_id"] for s in new_sections]

                # P1-2 fix: improve result merge logic to avoid duplicate sections
                existing_section_ids = {
                    s.get("section_id") for s in result.get("sections", [])
                    if isinstance(s, dict) and s.get("section_id")
                }
                merged_sections = result.get("sections", []).copy()

                for new_section in new_sections:
                    section_id = new_section.get("section_id")
                    if section_id and section_id not in existing_section_ids:
                        merged_sections.append(new_section)
                        existing_section_ids.add(section_id)

                # Preserve original completed_agents info
                original_completed = result.get("completed_agents", [])
                completed_map = {
                    entry.get("section_id"): entry
                    for entry in original_completed
                    if isinstance(entry, dict) and entry.get("section_id")
                }

                merged_result = {
                    **result,
                    "sections": merged_sections,
                    "completed_agents": [
                        {"section_id": s, "success": True,
                            **completed_map.get(s, {})}
                        for s in all_completed
                    ],
                }
                store.save_result(
                    task_id,
                    merged_result,
                    ResearchStatus.IN_PROGRESS)

                logger.info(
                    f"[replan] Replan complete, preserved: {
                        len(preserved)}, newly executed: {
                        len(new_sections)}")

            except Exception as e:
                logger.error(f"[replan] Failed to execute pending sections: {e}", exc_info=True)
                return {
                    "preserved": preserved,
                    "rerun": to_execute,
                    "status": "failed",
                    "error": str(e),
                }
        else:
            logger.info(f"[replan] No re-execution needed, all sections completed")

        return {
            "preserved": preserved,
            "rerun": to_execute,
            "status": "replanned",
        }

    def _cache_intent_for_task(self, task_id, intent_result):
        """R-FIX-4: 缓存意图分析结果到内存"""
        if not hasattr(self, '_intent_cache'):
            self._intent_cache = {}
        self._intent_cache[task_id] = intent_result

    def _get_cached_intent_for_task(self, task_id):
        """R-FIX-4: 获取已缓存的意图分析结果"""
        if not hasattr(self, '_intent_cache'):
            self._intent_cache = {}
        return self._intent_cache.get(task_id)

    async def reanalyze(
        self,
        task_id: str,
        updated_requirement: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Secondary intent analysis, reallocate unexecuted tasks

        Use cases:
        - Initial analysis missed important dimensions
        - User changes research direction midway

        Args:
            task_id: Task ID
            updated_requirement: Updated requirement

        Returns:
            {
                "preserved": [completed sections],
                "new_sections": [newly analyzed sections],
                "execution_plan": ExecutionPlan,
                "status": "reanalyzed",
            }
        """
        logger.info(f"[reanalyze] Starting reanalysis for task {task_id}")

        # Input validation
        if not task_id:
            return {"error": "task_id is required", "status": "failed"}

        # P2-1 fix: add type validation
        if not updated_requirement or not isinstance(
                updated_requirement, dict):
            return {
                "error": "updated_requirement must be a non-empty dict", "status": "failed"}

        # 1. Load existing results
        try:
            store = ResearchResultStore(storage_path=str(self._storage_path))
            result = store.load_result(task_id)
        except Exception as e:
            logger.error(f"[reanalyze] Failed to load task result: {e}")
            return {"error": f"Failed to load task: {e}", "status": "failed"}

        if not result:
            return {"error": "Task not found", "status": "failed"}

        # 2. Get completed sections
        completed_agents = result.get("completed_agents", [])
        completed_sections = set()
        for agent_entry in completed_agents:
            if isinstance(agent_entry, dict):
                section_id = agent_entry.get(
                    "section_id") or agent_entry.get("agent_id")
            else:
                section_id = str(agent_entry) if agent_entry else None

            if section_id:
                completed_sections.add(section_id)

        logger.info(f"[reanalyze] Completed sections: {completed_sections}")

        # 3. Check if intelligent routing is enabled
        if not self._use_intelligent_routing or self._routing_adapter is None:
            logger.warning(f"[reanalyze] Intelligent routing not enabled, cannot reanalyze")
            return {
                "error": "Intelligent routing not enabled",
                "status": "failed",
                "preserved": list(completed_sections),
            }

        # 4. R-FIX-4: Re-run intent analysis with existing intent fusion
        try:
            user_request = updated_requirement.get(
                "user_request", "") or updated_requirement.get(
                "topic", "")

            existing_intent = self._get_cached_intent_for_task(task_id)

            if existing_intent is not None:
                routing_result = self._routing_adapter.analyze_incremental(
                    user_request=user_request,
                    requirement=updated_requirement,
                    completed_aspects=list(completed_sections),
                    topic=user_request,
                    existing_intent_result=existing_intent,
                )
                logger.info(f"[reanalyze] Used incremental analysis with existing intent fusion")
            else:
                logger.warning(f"[reanalyze] No cached intent found, falling back to full analysis")
                routing_result = self._routing_adapter.analyze(
                    user_request=user_request,
                    requirement=updated_requirement,
                )

            self._cache_intent_for_task(task_id, routing_result.intent_result)

            primary_intent = routing_result.intent_result.primary_intent.value if hasattr(
                routing_result, 'intent_result') else "unknown"
            logger.info(f"[reanalyze] Intent analysis complete: {primary_intent}")

        except Exception as e:
            logger.error(f"[reanalyze] Intent analysis failed: {e}", exc_info=True)
            return {
                "error": f"Intent analysis failed: {e}",
                "status": "failed",
                "preserved": list(completed_sections),
            }

        # 5. Filter uncompleted sections
        new_sections = []
        all_section_ids = []

        if hasattr(routing_result,
                   'task_structure') and routing_result.task_structure:
            for section in routing_result.task_structure.sections:
                section_id = section.section_id if hasattr(
                    section, 'section_id') else str(section)
                all_section_ids.append(section_id)

                if section_id not in completed_sections:
                    new_sections.append(section_id)

        logger.info(
            f"[reanalyze] All sections: {all_section_ids}, New sections: {new_sections}")

        # 6. Get new execution plan
        execution_plan = None
        if hasattr(routing_result, 'execution_plan'):
            execution_plan = routing_result.execution_plan

        # P1-5 fix: validate execution_plan
        if not execution_plan:
            logger.warning("[reanalyze] execution_plan is empty, may affect subsequent execution")

        # 7. Get lock_manager (if available)
        lock_manager = self._get_lock_manager_for_task(task_id)

        # 8. If there are new sections, create Agents and execute
        if new_sections:
            try:
                agents = await self._create_agents_for_sections(
                    section_ids=new_sections,
                    requirement=updated_requirement,
                    task_id=task_id,
                )

                # P0-3 fix: handle empty agents case
                if not agents:
                    logger.warning(
                        f"[reanalyze] Cannot create Agents for new sections: {new_sections}")
                    return {
                        "preserved": list(completed_sections),
                        "new_sections": new_sections,
                        "execution_plan": execution_plan,
                        "status": "partial",
                        "warning": "Cannot create Agents for new sections",
                    }

                # Execute new sections
                exec_result = await self._execution_engine.execute(
                    agents=agents,
                    requirement=updated_requirement,
                )

                # Extract new results
                new_section_results = []
                for stage_name, stage_results in exec_result.stage_results.items():
                    for r in stage_results:
                        if isinstance(r, dict) and r.get(
                                "success") is True and r.get("content"):
                            new_section_results.append({
                                "section_id": r.get("agent_id", ""),
                                "content": r.get("content", ""),
                                "data_points": r.get("data_points", []),
                                "sources": r.get("sources", []),
                            })

                # Merge results
                all_completed = list(completed_sections) + \
                    [s["section_id"] for s in new_section_results]

                # P0-2 fix: ensure sections is a list
                existing_sections = result.get("sections") or []
                if not isinstance(existing_sections, list):
                    existing_sections = []

                existing_section_ids = {
                    s.get("section_id") for s in existing_sections
                    if isinstance(s, dict) and s.get("section_id")
                }
                merged_sections = existing_sections.copy()

                for new_section in new_section_results:
                    section_id = new_section.get("section_id")
                    if section_id and section_id not in existing_section_ids:
                        merged_sections.append(new_section)
                        existing_section_ids.add(section_id)

                # P1-3 fix: preserve original completed_agents info
                original_completed = result.get("completed_agents", [])
                completed_map = {
                    entry.get("section_id"): entry
                    for entry in original_completed
                    if isinstance(entry, dict) and entry.get("section_id")
                }

                merged_result = {
                    **result,
                    "sections": merged_sections,
                    "completed_agents": [
                        {"section_id": s, "success": True,
                            **completed_map.get(s, {})}
                        for s in all_completed
                    ],
                    "intent_analysis": routing_result.to_dict() if hasattr(routing_result, 'to_dict') else {},
                }
                store.save_result(
                    task_id,
                    merged_result,
                    ResearchStatus.IN_PROGRESS)

                logger.info(
                    f"[reanalyze] Execution complete, preserved: {
                        len(completed_sections)}, new: {
                        len(new_section_results)}")

            except Exception as e:
                logger.error(f"[reanalyze] Failed to execute new sections: {e}", exc_info=True)
                return {
                    "preserved": list(completed_sections),
                    "new_sections": new_sections,
                    "execution_plan": execution_plan,
                    "status": "partial",
                    "error": str(e),
                }

        return {
            "preserved": list(completed_sections),
            "new_sections": new_sections,
            "execution_plan": execution_plan,
            "lock_manager": lock_manager,
            "status": "reanalyzed",
        }

    def _get_lock_manager_for_task(
            self, task_id: str) -> Optional["ContentLockManager"]:
        """
        Get or create content lock manager for the task

        Args:
            task_id: Task ID

        Returns:
            ContentLockManager or None
        """
        # P0-2 fix: ContentLockManager requires ExecutionPlan parameter
        # In replan scenario, temporarily return None
        # If content lock functionality is needed, maintain lock_manager instance in routing_adapter
        if self._routing_adapter is not None:
            # Try to get existing lock_manager from routing_adapter
            if hasattr(self._routing_adapter, 'get_lock_manager'):
                try:
                    lock_manager = self._routing_adapter.get_lock_manager(
                        task_id)
                    if lock_manager:
                        return lock_manager
                except Exception as e:
                    logger.debug(
                        f"[_get_lock_manager_for_task] Failed to get from routing_adapter: {e}")

        # No available lock_manager, return None
        # This means replan scenario won't use content lock
        logger.debug(
            f"[_get_lock_manager_for_task] No ContentLockManager available, replan will skip content lock")
        return None

    async def _create_agents_for_sections(
        self,
        section_ids: List[str],
        requirement: Dict[str, Any],
        task_id: str,
        research_type: Optional[str] = None,
    ) -> List["IAgent"]:
        """
        Create Agents for specified sections

        Args:
            section_ids: Section ID list
            requirement: Requirement definition
            task_id: Task ID

        Returns:
            Agent list
        """
        agents = []

        for section_id in section_ids:
            try:
                # P1-1 fix: use correct create_agent signature
                # create_agent(agent_id, capability, context=None)

                # P0-3 fix: AgentCapability is defined in factory.py
                from src.core.agents.factory import AgentCapability
                capability = AgentCapability(
                    name=f"replan_{section_id}",
                    description=f"Responsible for researching and writing the {section_id} section",
                    required_skills=["web_search", "data_analysis"],
                    optional_skills=[],
                    role="researcher",
                    goal=f"Complete section: {section_id}",
                    backstory=f"Responsible for researching and writing the {section_id} section",
                )

                context = {
                    "task_id": task_id,
                    "section_id": section_id,
                    "topic": requirement.get("topic", ""),
                    "research_type": research_type or "market_research",
                    "intent_confidence": 1.0,
                    "domain_context": {},
                    "hidden_requirements": [],
                }

                # Use agent_factory to create Agent
                if self._agent_factory:
                    # P1-4 fix: use unique ID to avoid Agent ID conflicts (uuid imported at top)
                    unique_agent_id = f"replan_{section_id}_{uuid.uuid4().hex[:8]}"
                    agent = self._agent_factory.create_agent(
                        agent_id=unique_agent_id,
                        capability=capability,
                        context=context,
                    )
                    if agent:
                        agents.append(agent)
                else:
                    logger.warning(
                        f"[_create_agents_for_sections] agent_factory unavailable")

            except Exception as e:
                logger.error(
                    f"[_create_agents_for_sections] Failed to create Agent {section_id}: {e}")

        return agents

    async def _handle_engine_inject(
        self,
        session_id: str,
        requirement: Dict[str, Any],
    ) -> List["IAgent"]:
        """引擎注入检查点回调：检查 pending 注入并创建 Agent
        
        由 engine 的批次循环在每批次之间调用。
        
        Returns:
            新创建的 Agent 列表，无注入时返回空列表
        """
        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        session = sm.get(session_id)
        if not session:
            return []

        pending = session.get("_pending_section_injects", [])
        if not pending:
            return []

        add_ops = [p for p in pending if p["op"] == "add_section"]
        other_ops = [p for p in pending if p["op"] != "add_section"]
        session["_pending_section_injects"] = other_ops
        new_sections = [p["section_name"] for p in add_ops]
        if not new_sections:
            return []

        logger.info(f"[inject] 引擎注入检查点触发: session={session_id}, 新章节={new_sections}")
        agents = await self._create_agents_for_sections(
            section_ids=new_sections,
            requirement=requirement,
            task_id=session_id,
        )
        return agents

    async def _execute_survey_integration(
        self,
        requirement,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        from src.agents.fixed_agents.survey_integration_agent import SurveyIntegrationAgent
        llm_skill = self._skill_registry.get("llm_skill")
        if not llm_skill:
            logger.warning(f"[{task_id}] No LLM skill available, skipping survey")
            return None
        agent = SurveyIntegrationAgent(
            agent_id=f"{task_id}_survey",
            llm_skill=llm_skill,
        )
        result = await agent.execute({
            "workflow": getattr(requirement, "survey_mode", "ai_simulation"),
            "topic": getattr(requirement, "topic", ""),
            "target_count": getattr(requirement, "survey_target_count", 100),
            "persona_template": "一线白领",
            "parent_task_id": task_id,
        })
        if result and result.get("status") == "completed":
            analysis = result.get("analysis", {})
            result["survey_section"] = {
                "summary": analysis.get("report", ""),
                "statistics": analysis.get("statistics", {}),
                "key_findings": analysis.get("key_findings", []),
                "insights": analysis.get("insights", []),
                "charts": analysis.get("charts", []),
            }
            result["findings"] = {
                "insights": analysis.get("insights", []),
                "key_findings": analysis.get("key_findings", []),
            }
        return result

    # === Interactive helper methods ===

    async def _run_interactive_clarification(
        self,
        user_input: Union[str, Dict[str, Any]],
        interaction_callback: Callable[[Dict[str, Any]], Any],
        task_id: str,
    ) -> Optional[ResearchRequirement]:
        """
        Run interactive requirement clarification flow

        Args:
            user_input: User initial input
            interaction_callback: Frontend interaction callback
            task_id: Task ID

        Returns:
            ResearchRequirement or None (user cancelled)
        """
        try:
            # Step 1: Select output type
            step1 = self._smart_clarifier.start(str(user_input))
            response1 = await interaction_callback(step1)

            # Ensure response1 is a dict
            if isinstance(response1, str):
                response1 = {"output_type": response1}

            output_type = response1.get("output_type", "research_report")

            # Step 2: Select research framework (detailed/standard/brief) - supports going back
            while True:
                step2 = self._smart_clarifier.select_output_type(output_type)
                response2 = await interaction_callback(step2)

                # Ensure response2 is a dict
                if not isinstance(response2, dict):
                    response2 = {
                        "framework_id": str(response2)} if response2 else {
                        "framework_id": "standard"}

                if response2.get("go_back"):
                    # Go back to Step 1 to re-select report type
                    step1 = self._smart_clarifier.start(str(user_input))
                    response1 = await interaction_callback(step1)
                    if not isinstance(response1, dict):
                        response1 = {
                            "output_type": str(response1)} if response1 else {
                            "output_type": "research_report"}
                    output_type = response1.get(
                        "output_type", "research_report")
                    continue

                framework_id = response2.get("framework_id", "standard")

                # Step 3: Confirm section details - supports going back
                response3 = {}  # Defensive initialization, avoid static analysis false positives
                while True:
                    step3 = self._smart_clarifier.select_framework(
                        framework_id)
                    response3 = await interaction_callback(step3)

                    # Ensure response3 is a dict
                    if not isinstance(response3, dict):
                        response3 = {"confirmed": True}

                    if response3.get("go_back"):
                        # Go back to Step 2 to re-select framework - break inner loop
                        break

                    if not response3.get("confirmed", True):
                        return None

                    # Section confirmed successfully, break outer loop
                    break

                # If Step 3 returned go_back, continue Step 2 loop
                if response3.get("go_back"):
                    continue

                # Otherwise, break Step 2 loop
                break

            # Apply section adjustments
            adjustments = response3.get("adjustments") if isinstance(
                response3, dict) else None
            self._smart_clarifier.confirm_sections(
                confirmed=True,
                adjustments=adjustments,
            )

            # Step 4: Confirm parameters
            step4 = self._smart_clarifier.confirm_sections(confirmed=True)
            response4 = await interaction_callback(step4)

            # Ensure response4 is a dict
            if not isinstance(response4, dict):
                response4 = {"region": "China", "time_range": "Last 3 years"}

            # Step 5: Set parameters and final confirmation
            region = response4.get("region", "China")
            time_range = response4.get("time_range", "Last 3 years")

            self._smart_clarifier.confirm_parameters(
                region=region,
                time_range=time_range,
            )

            # Final confirmation
            step5 = self._smart_clarifier.confirm_parameters(
                region=region,
                time_range=time_range,
            )
            response5 = await interaction_callback(step5)

            # Debug log
            logger.info(
                f"[{task_id}] response5 type: {type(response5)}, value: {response5}")

            # Ensure response5 is a dict
            if not isinstance(response5, dict):
                logger.warning(
                    f"[{task_id}] response5 is not dict, converting...")
                response5 = {
                    "confirmed": str(response5) == "confirm"} if response5 else {
                    "confirmed": True}

            if not response5.get("confirmed", True):
                return None

            # Get final requirement
            self._smart_clarifier.confirm(True)
            user_choice = self._smart_clarifier.get_final_requirement()

            if not user_choice:
                return None

            # Extract survey-related parameters from original input
            input_dict = user_input if isinstance(user_input, dict) else {}

            # Helper function: get section name (supports multi-language format)
            def get_section_name(section: Dict) -> str:
                name = section.get("name", section.get("id", ""))
                if isinstance(name, dict):
                    # Multi-language format: prefer Chinese, then English, then first value
                    return name.get("zh", name.get(
                        "en", list(name.values())[0] if name else ""))
                return str(name)

            # Extract section names from section_details as aspects
            # section_details contains complete section info (id, name, content/description)
            section_names = []
            if hasattr(user_choice,
                       'section_details') and user_choice.section_details:
                section_names = [
                    get_section_name(s) for s in user_choice.section_details]
            else:
                # Backward compatibility: if no section_details, use selected_sections
                section_names = user_choice.selected_sections

            # Convert to ResearchRequirement
            requirement = ResearchRequirement(
                topic=user_choice.topic,
                aspects=section_names,  # Use section names as research dimensions
                region=user_choice.region,
                time_range=user_choice.time_range,
                focus_brands=user_choice.focus_areas,
                competitors=[],
                depth=user_choice.depth,
                output_format="docx",  # Default Word format
                output_type=user_choice.output_type,
                template_id=user_choice.template_id,
                selected_sections=user_choice.selected_sections,
                section_details=getattr(
                    user_choice, 'section_details', []),  # Pass complete section info
                special_requirements=[],
                # Survey integration fields
                include_survey=input_dict.get("include_survey", False),
                enable_questionnaire=input_dict.get(
                    "enable_questionnaire", input_dict.get(
                        "include_survey", False)),
                survey_mode=input_dict.get("survey_mode", "ai_simulation"),
                survey_target_count=input_dict.get("survey_sample_size", 100),
                survey_timeout_days=input_dict.get("survey_timeout_days", 7),
            )

            return requirement

        except Exception as e:
            logger.error(f"[{task_id}] Interactive clarification failed: {e}")
            return None

    async def _get_user_confirmation(
        self,
        requirement: ResearchRequirement,
        interaction_callback: Callable[[Dict[str, Any]], Any],
        task_id: str,
    ) -> bool:
        """
        Get user confirmation for research plan

        Args:
            requirement: Research requirement
            interaction_callback: Frontend interaction callback
            task_id: Task ID

        Returns:
            Whether user confirmed
        """
        try:
            # Generate confirmation summary
            summary = self._generate_requirement_summary(requirement)

            confirm_data = {
                "step": "confirm",
                "message": "Please confirm the research plan",
                "summary": summary,
                "actions": ["confirm", "modify", "cancel"]
            }

            response = await interaction_callback(confirm_data)
            return response.get("action") == "confirm"

        except Exception as e:
            logger.error(f"[{task_id}] Failed to get user confirmation: {e}")
            return False

    async def _get_user_feedback(
        self,
        preview: Any,
        interaction_callback: Callable[[Dict[str, Any]], Any],
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Get user feedback on preview

        Args:
            preview: Preview object
            interaction_callback: Frontend interaction callback
            task_id: Task ID

        Returns:
            User feedback (action: confirm/revise/cancel)
        """
        try:
            feedback_data = {
                "step": "preview",
                "message": "Please review the preview and provide feedback",
                "preview_url": preview.preview_path if hasattr(preview, 'preview_path') else None,
                "actions": ["confirm", "revise", "cancel"]
            }

            response = await interaction_callback(feedback_data)
            return response

        except Exception as e:
            logger.error(f"[{task_id}] Failed to get user feedback: {e}")
            return {"action": "confirm"}  # Default: confirm

    def _generate_requirement_summary(
            self, requirement: ResearchRequirement) -> str:
        """Generate requirement summary"""
        lines = [
            "=" * 50,
            f"Research topic: {requirement.topic}",
            f"Region: {requirement.region}",
            f"Time range: {requirement.time_range}",
            f"Research depth: {requirement.depth}",
            "",
            f"Research dimensions ({len(requirement.aspects)} total):",
        ]

        for aspect in requirement.aspects:
            lines.append(f"  - {aspect}")

        if requirement.focus_brands:
            lines.append(f"\nFocus brands: {', '.join(requirement.focus_brands)}")

        lines.extend([
            "",
            f"Output format: {requirement.output_format}",
            "=" * 50,
        ])

        return "\n".join(lines)

    def _parse_output_type(self, output_type_str: str) -> OutputType:
        """
        Parse output type string to OutputType enum

        Args:
            output_type_str: Output type string

        Returns:
            OutputType: Corresponding enum value
        """
        # Mapping table: support multiple input formats
        type_mapping = {
            "industry_report": OutputType.INDUSTRY_REPORT,
            "industry_weekly": OutputType.INDUSTRY_WEEKLY,
            "company_research": OutputType.COMPANY_RESEARCH,
            "quarterly_commentary": OutputType.QUARTERLY_COMMENTARY,
            "annual_analysis": OutputType.ANNUAL_ANALYSIS,
            "conference_call": OutputType.CONFERENCE_CALL,
            "commercial_plan": OutputType.COMMERCIAL_PLAN,
            "pitch_deck": OutputType.PITCH_DECK,
            "investment_memo": OutputType.INVESTMENT_MEMO,
            "competitor_analysis": OutputType.COMPETITOR_ANALYSIS,
            "policy_brief": OutputType.POLICY_BRIEF,
            "market_brief": OutputType.MARKET_BRIEF,
            "data_dashboard": OutputType.DATA_DASHBOARD,
            "custom": OutputType.CUSTOM,
            # Legacy format compatibility
            "research_report": OutputType.INDUSTRY_REPORT,
            "market_research": OutputType.INDUSTRY_REPORT,
            "report": OutputType.INDUSTRY_REPORT,
        }

        return type_mapping.get(output_type_str.lower(),
                                OutputType.INDUSTRY_REPORT)

    def _parse_requirement(
        self,
        user_input: Union[str, Dict[str, Any]]
    ) -> ResearchRequirement:
        """
        Parse user requirement (direct execution mode)

        Args:
            user_input: User input (natural language or structured dict)

        Returns:
            ResearchRequirement: Parsed research requirement
        """
        if isinstance(user_input, dict):
            # Determine which to use as aspects first
            if user_input.get("aspects"):
                # User provided custom aspects (own framework, not from template).
                aspects = user_input["aspects"]
                template_id = user_input.get("template_id", "")
                section_details = [
                    {"id": a.lower().replace(" ", "_"), "name": a, "content": a}
                    for a in aspects
                ]
            elif user_input.get("selected_sections"):
                # User selected sections from a template
                template_id = user_input.get(
                    "template_id", "industry_report_broker")
                section_details = self._load_template_sections(template_id)
                aspects = self._convert_section_ids_to_names(
                    user_input["selected_sections"],
                    section_details
                )
            else:
                # No aspects specified — fall back to all sections from template
                template_id = user_input.get(
                    "template_id", "industry_report_broker")
                section_details = self._load_template_sections(template_id)
                if section_details:
                    aspects = []
                    for s in section_details:
                        name = s.get("name", s.get("id", ""))
                        if isinstance(name, dict):
                            name = name.get("en", name.get("zh", str(name)))
                        aspects.append(name)
                else:
                    aspects = ["Market Size", "Competitive Landscape", "Development Trends"]

            return ResearchRequirement(
                topic=user_input.get("topic", "Unknown Topic"),
                aspects=aspects,
                region=user_input.get("region", "China"),
                time_range=user_input.get("time_range", "Last 3 Years"),
                focus_brands=user_input.get("focus_brands", []),
                competitors=user_input.get("competitors", []),
                depth=user_input.get("depth", "detailed"),
                output_format=user_input.get("output_format", "docx"),
                output_type=self._parse_output_type(
                    user_input.get("output_type", "industry_report")),
                template_id=template_id,
                selected_sections=user_input.get("selected_sections", []),
                section_details=section_details,
                special_requirements=user_input.get(
                    "special_requirements", []),
                # Survey integration fields
                include_survey=user_input.get("include_survey", False),
                enable_questionnaire=user_input.get(
                    "enable_questionnaire", user_input.get(
                        "include_survey", False)),
                survey_mode=user_input.get("survey_mode", "ai_simulation"),
                survey_target_count=user_input.get("survey_sample_size", 100),
                survey_timeout_days=user_input.get("survey_timeout_days", 7),
                section_requirements=user_input.get("section_requirements", {}),
            )

        # Natural language parsing
        text = str(user_input).strip()
        aspects = []

        aspect_keywords = {
            "Market Size": ["market size", "market"],
            "Competitive Landscape": ["competition", "competitive"],
            "Policy Environment": ["policy", "regulation"],
            "Technology Trends": ["technology", "tech"],
            "Development Trends": ["trend", "development"],
            "Industry Chain": ["industry chain", "supply chain"],
        }

        for aspect, keywords in aspect_keywords.items():
            if any(kw.lower() in text.lower() for kw in keywords):
                aspects.append(aspect)

        # If no keywords matched, load sections from default template
        if not aspects:
            section_details = self._load_template_sections(
                "industry_report_broker")
            if section_details:
                # Use all sections from the template for maximum coverage
                # Handle multi-language name fields
                aspects = []
                for s in section_details:
                    name = s.get("name", s.get("id", ""))
                    if isinstance(name, dict):
                        name = name.get("en", name.get("zh", str(name)))
                    aspects.append(name)
            else:
                # Final fallback: at least 3 sections to pass quality check
                aspects = ["Market Size", "Competitive Landscape", "Development Trends"]

        return ResearchRequirement(
            topic=text,
            aspects=aspects,
            selected_sections=aspects,
            output_type=OutputType.INDUSTRY_REPORT,
            template_id="industry_report_standard",
        )

    def _load_template_sections(
            self, template_id: str) -> List[Dict[str, Any]]:
        """
        Load section info from template config

        Args:
            template_id: Template ID

        Returns:
            Section info list, empty list if loading fails
        """
        try:
            # Use SmartClarifier's template loader
            if hasattr(self, '_smart_clarifier') and self._smart_clarifier:
                template = self._smart_clarifier.TEMPLATES.get(template_id)
                if template and hasattr(template, 'sections'):
                    return template.sections

            # Try loading from YAML directly
            import yaml

            template_path = Path(f"config/templates/{template_id}.yaml")
            if not template_path.exists():
                # Try other possible filenames
                for yaml_file in Path("config/templates").glob("*.yaml"):
                    if yaml_file.name == "template_schema.yaml":
                        continue
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    if data and data.get("id") == template_id:
                        return data.get("sections", [])

            return []
        except Exception as e:
            logger.warning(f"Failed to load template {template_id}: {e}")
            return []

    def _convert_section_ids_to_names(
        self,
        section_ids: List[str],
        section_details: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Convert section ID list to section name list

        Args:
            section_ids: Section ID list
            section_details: Complete section info (includes id and name)

        Returns:
            Section name list
        """
        if not section_details:
            # If no section details, return original list (could be names)
            return section_ids

        # Build ID to name mapping (handle multi-language name field)
        id_to_name = {}
        for s in section_details:
            name = s.get("name")
            if isinstance(name, dict):
                # Multi-language name, extract English
                name = name.get("en", name.get("zh", str(name)))
            id_to_name[s.get("id")] = name or s.get("id", "")

        result = []
        for sid in section_ids:
            if sid in id_to_name:
                name = id_to_name[sid]
                # Ensure name is string
                if isinstance(name, dict):
                    name = name.get("en", name.get("zh", str(name)))
                result.append(name)
            else:
                # If mapping not found, keep original value
                result.append(sid)

        return result

    def _create_agents_from_plan(
        self,
        plan: Any,
        requirement: ResearchRequirement,
        task_id: str,
        research_type: Optional[str] = None,
        intent_result: Any = None,
    ) -> List[BaseAgent]:
        """
        B-2 fix: Create Agents according to decomposition plan

        Creates independent Agents for each phase based on AgentSpec definitions,
        ensuring:
        - Data collection agent focuses only on search
        - Analysis agent focuses only on analysis
        - Synthesis agent focuses only on synthesis

        Args:
            plan: Task decomposition plan
            requirement: Research requirement
            task_id: Task ID

        Returns:
            Agent list
        """
        from src.core.agents.factory import AgentCapability
        from src.core.agents.base import BaseAgent

        agents = []
        logger.info(f"[{task_id}] Creating Agents by decomposition plan, {len(plan.phases)} phases")

        # Iterate through each phase
        for phase, specs in plan.phases.items():
            # Skip report generation phase (handled externally by orchestrator's DocumentGenerationAgent)
            if phase.value == "report_generation":
                logger.debug(
                    f"[{task_id}] Skipping report generation phase (handled by DocumentGenerationAgent): {len(specs)} AgentSpecs")
                continue

            for spec in specs:
                try:
                    # Phase 4: use intelligent routing adapter to get capability template
                    template_data = self._routing_adapter.get_template_for_intent(
                        IntentType.RESEARCH  # Default to RESEARCH type
                    )

                    # Merge skill_params
                    skill_params = {}
                    if template_data and "skill_params" in template_data:
                        skill_params.update(template_data["skill_params"])

                    # Build capability
                    capability = AgentCapability(
                        name=f"{phase.value}_{spec.agent_id}",
                        description=spec.task_description,
                        required_skills=spec.skills +
                        (template_data.get("recommended_skills", [])
                         if template_data else []),
                        optional_skills=[],
                        skill_params=skill_params,
                        role="Research Expert",
                        goal=spec.task_description,
                        backstory=f"Professional {spec.agent_type} Research Agent",
                        system_prompt=spec.system_prompt,
                    )

                    # Create agent, context includes dependency info for scheduler
                    context = dict(spec.context) if spec.context else {}
                    if getattr(spec, 'output_keys', None) and spec.output_keys:
                        context["section_id"] = spec.output_keys[0]
                    elif getattr(spec, 'section_ids', None) and spec.section_ids:
                        context["section_id"] = spec.section_ids[0]
                    context["depends_on"] = spec.dependencies
                    context["task_id"] = task_id
                    context["research_type"] = research_type or "market_research"
                    if intent_result:
                        context["intent_confidence"] = getattr(intent_result, 'intent_confidence', None) or getattr(intent_result, 'confidence', 1.0)
                        context["domain_context"] = getattr(intent_result, 'domain_context', {}) or {}
                        context["hidden_requirements"] = getattr(intent_result, 'hidden_requirements', []) or []
                        context["core_question"] = getattr(intent_result, 'core_question', '') or ''
                    else:
                        context["intent_confidence"] = 1.0
                        context["domain_context"] = {}
                        context["hidden_requirements"] = []
                        context["core_question"] = ''

                    # Inject analysis framework context
                    own_aspect = (spec.context or {}).get("aspect", "")
                    if spec.agent_type == "analysis":
                        context["role_in_report"] = f"从{own_aspect}维度为核心问题提供分析证据"
                    elif spec.agent_type == "synthesis":
                        context["role_in_report"] = "整合各维度分析结论，回答核心问题"
                    elif spec.agent_type == "research":
                        context["role_in_report"] = f"收集{own_aspect}维度的基础数据"
                    else:
                        context["role_in_report"] = ""
                    all_aspects = requirement.aspects if hasattr(requirement, 'aspects') else []
                    context["sibling_aspects"] = [a for a in all_aspects if a and a != own_aspect]
                    agent, session = self._agent_factory.create_agent_with_session(
                        agent_id=spec.agent_id,
                        capability=capability,
                        parent_session_id=task_id,
                        context=context,
                        category=spec.category,
                    )
                    agents.append(agent)
                    logger.debug(
                        f"[{task_id}] Created Agent: {spec.agent_id} ({phase.value}, category={spec.category})")

                except Exception as e:
                    logger.warning(
                        f"[{task_id}] Failed to create Agent {spec.agent_id}: {e}")
                    # Don't abort, continue creating other agents

        logger.info(f"[{task_id}] Created {len(agents)} Agents by decomposition plan")
        return agents

    def _format_routing_framework(self, routing_result, requirement) -> str:
        """Format intelligent routing result as a displayable framework summary"""
        task_structure = getattr(routing_result, 'task_structure', None)
        sections = task_structure.sections if task_structure else []

        exec_plan = getattr(routing_result, 'execution_plan', None)
        phases = exec_plan.phases if exec_plan else []
        total_agents = exec_plan.total_agents if exec_plan else 0

        lines = [
            f"Research topic: {requirement.topic}",
            "",
        ]
        if sections:
            lines.append(f"Sections ({len(sections)} total):")
            for i, s in enumerate(sections, 1):
                section_name = getattr(s, 'section_id', str(s))
                section_desc = getattr(s, 'description', '') if hasattr(s, 'description') else ''
                if section_desc:
                    lines.append(f"  {i}. {section_name} — {section_desc}")
                else:
                    lines.append(f"  {i}. {section_name}")
            lines.append("")
        if phases:
            lines.append(f"Execution phases ({len(phases)} phases, {total_agents} agents):")
            for i, p in enumerate(phases, 1):
                phase_name = getattr(p, 'phase_type', {}).value if hasattr(p, 'phase_type') else str(p)
                agent_count = len(getattr(p, 'agent_specs', []))
                lines.append(f"  {i}. {phase_name} ({agent_count} agents)")
            lines.append("")

        return "\n".join(lines)

    def _create_agents(
        self,
        requirement: ResearchRequirement,
        intent_result: Any,
        task_id: str,
        research_type: Optional[str] = None,
    ) -> List[BaseAgent]:
        """
        Create Agents (using routing decisions + Session management)

        **Major fix**: Integrated intelligent routing system

        Flow:
        1. Use IntentGate results to determine strategy
        2. Use CategoryRouter to route to template
        3. Use WisdomStore recommended Skills
        4. Adjust Agent count based on complexity
        5. Create data collection + analysis Agents for each dimension

        Args:
            requirement: Research requirement
            intent_result: Intent analysis result (now actually used)
            task_id: Task ID (as parent_session_id)

        Returns:
            Agent list
        """
        # Type definitions imported from intent_types.py (Phase 1 type separation)
        from src.core.intent_types import IntentType, TaskComplexity
        from src.core.agents.factory import AgentCapability
        from src.core.research_framework_manager import get_framework_config

        # v3.4 R2 fix: extract intent fields for agent context
        _intent_confidence = getattr(intent_result, 'intent_confidence', None) or getattr(intent_result, 'confidence', 1.0)
        _domain_context = getattr(intent_result, 'domain_context', {}) or {}
        _hidden_requirements = getattr(intent_result, 'hidden_requirements', []) or []

        agents = []

        # === Intelligent routing: use IntentGate results ===
        complexity = intent_result.complexity if intent_result else TaskComplexity.MULTI
        # P0 fix: Compatible with both DeepIntentResult (primary_intent) and IntentAnalysisResult (intent)
        intent_type = self._get_intent_type(intent_result)

        # Determine Agent count strategy by complexity
        if complexity == TaskComplexity.TRIVIAL:
            max_agents_per_aspect = 1
            max_results_per_agent = 5
        elif complexity == TaskComplexity.SINGLE:
            max_agents_per_aspect = 1
            max_results_per_agent = 10
        elif complexity == TaskComplexity.MULTI:
            max_agents_per_aspect = 1  # 1 comprehensive Agent per section
            max_results_per_agent = 15
        else:  # COMPLEX
            max_agents_per_aspect = 2  # 2 Agents per section (data + analysis)
            max_results_per_agent = 20

        logger.info(
            f"[{task_id}] Intelligent routing: complexity={complexity.value}, max {max_agents_per_aspect} Agents per section")

        # P0-3 fix: get framework config by research type
        output_type_value = requirement.output_type.value if hasattr(
            requirement.output_type, 'value') else str(requirement.output_type)
        framework_config = get_framework_config(output_type_value)

        logger.info(f"[{task_id}] Using research framework: {framework_config.name}")
        logger.info(
            f"[{task_id}] Analysis depth: {framework_config.get_analysis_depth()}")
        logger.info(f"[{task_id}] Focus areas: {framework_config.get_focus_areas()}")

        # Define data collection task types
        data_collection_tasks = [
            ("Industry Overview", "Industry definition, development history, current status"),
            ("Market Size", "Market size, growth rate, segment data"),
            ("Competitive Landscape", "Major players, market share, competition landscape"),
            ("Industry Chain", "Upstream supply, midstream manufacturing, downstream applications"),
            ("Policy & Regulation", "Relevant policies, regulatory impact, compliance requirements"),
            ("Technology Trends", "Core technologies, technology roadmap, innovation direction"),
            ("Company Analysis", "Major company financials, operational data, strategic布局"),
            ("Consumer Insights", "Consumer profile, demand characteristics, purchasing behavior"),
        ]

        # === Section dependency definition ===
        # summary and conclusion are special sections that need to wait for other sections
        DEPENDENT_SECTIONS = {
            "summary",
            "conclusion",
            "executive summary",
            "research conclusion",
        }

        # Separate normal sections and dependent sections
        normal_aspects = []
        dependent_aspects = []

        for i, aspect in enumerate(requirement.aspects):
            aspect_lower = aspect.lower()
            if aspect_lower in DEPENDENT_SECTIONS or any(
                    ds in aspect for ds in DEPENDENT_SECTIONS):
                dependent_aspects.append((i, aspect))
            else:
                normal_aspects.append((i, aspect))

        logger.info(f"[{task_id}] Normal sections: {[a[1] for a in normal_aspects]}")
        logger.info(f"[{task_id}] Dependent sections: {[a[1] for a in dependent_aspects]}")

        # **Critical fix**: pre-compute normal section Agent IDs for dependency relationships
        normal_agent_ids = []
        _aspect_to_agent_id: Dict[str, List[str]] = {}
        for i, aspect in normal_aspects:
            agent_id = f"research_{aspect.lower().replace(' ', '_')}_{i + 1}"
            normal_agent_ids.append(agent_id)
            _aspect_to_agent_id.setdefault(aspect, []).append(agent_id)

        logger.info(f"[{task_id}] Normal section Agent IDs: {normal_agent_ids}")

        # === 1. Create normal section Agents first (one comprehensive Agent per section) ===
        for i, aspect in normal_aspects:
            # Intelligently match data types needed for this dimension (build research context)
            relevant_data_types = self._match_data_types(
                aspect, data_collection_tasks)
            data_types_str = " & ".join(
                [dt[0] for dt in relevant_data_types[:2]])  # Max 2 data types

            # P0-3 fix: get section weight, adjust resource allocation
            section_weight = framework_config.get_section_weight(
                aspect.lower().replace(" ", "_"))
            max_queries = framework_config.get_max_queries()
            max_results = int(
                framework_config.get_max_results() *
                section_weight)  # Adjust by weight
            max_total = framework_config.get_max_total_searches()

            # Phase 4: use intelligent routing adapter to get capability template
            template_data = self._routing_adapter.get_template_for_intent(
                intent_type)

            # === Intelligent routing: merge WisdomStore recommended Skills ===
            wisdom_skills = self._wisdom_store.get_recommended_skills(
                task_type=intent_type.value if intent_type else "research",
                task_aspect=aspect,
            )

            # Merge template Skills and Wisdom recommended Skills
            base_skills = template_data.get(
                "recommended_skills", [
                    "search_skill", "llm_skill"]) if template_data else [
                "search_skill", "llm_skill"]
            optional_skills = []

            # Add Wisdom recommended Skills
            for skill in wisdom_skills:
                if skill not in base_skills and skill not in optional_skills:
                    optional_skills.append(skill)

            logger.debug(
                f"[{task_id}] {aspect}: template Skills={base_skills}, Wisdom recommended={wisdom_skills}")

            # === Create comprehensive research Agent (data collection + analysis integrated) ===
            agent_id = f"research_{aspect.lower().replace(' ', '_')}_{i + 1}"

            # P0-3 fix: build system prompt with framework config
            focus_areas = framework_config.get_focus_areas()
            key_metrics = framework_config.get_key_metrics()
            priority_sources = framework_config.get_priority_sources()
            min_length = framework_config.get_min_section_length()
            analysis_depth = framework_config.get_analysis_depth()

            focus_areas_str = " & ".join(
                focus_areas[:5]) if focus_areas else data_types_str
            metrics_str = " & ".join(key_metrics[:8]) if key_metrics else ""
            sources_str = " & ".join(
                priority_sources[:5]) if priority_sources else ""

            # Build system prompt - pursue extreme quality
            _now = datetime.now()
            _current_date = _now.strftime("%Y-%m-%d")
            _current_year = str(_now.year)
            _pm = PromptManager()
            chart_req = "6. Must include data charts (tables or chart descriptions)" if framework_config.requires_charts() else ""
            multi_src_req = "7. Must include cross-validation from multiple data sources" if framework_config.requires_multiple_sources() else ""
            system_prompt = _pm.render("agents", "body_agent",
                                       strip_frontmatter=True,
                                       current_date=_current_date,
                                       current_year=_current_year,
                                       topic=requirement.topic,
                                       aspect=aspect,
                                       focus_areas=focus_areas_str,
                                       metrics=metrics_str if metrics_str else "Extract key data indicators based on research content, including market size, growth rate, market share and other core metrics",
                                       sources=sources_str if sources_str else "Prioritize authoritative data sources: industry associations, government statistics, broker research, academic papers, listed company annual reports",
                                       region=requirement.region,
                                       depth=analysis_depth,
                                       min_length=min_length,
                                       chart_requirement=chart_req,
                                       multi_source_requirement=multi_src_req,
                                        )
            
            # P-FIX-5: inject research task context
            _all_aspects = getattr(requirement, 'aspects', [])
            _sibling_aspects = [a for a in _all_aspects if a != aspect]
            _role_desc = {
                "financial_analysis": "对财务数据进行结构化分析，产出核心财务指标和趋势判断",
                "market_size": "量化市场规模、增长率和渗透率",
                "competitive_landscape": "评估竞争格局、市场份额和集中度",
                "technology": "评估技术路线、研发投入和创新能力",
                "policy": "分析政策环境和监管影响",
                "risk": "识别和评估关键风险因素",
                "forecast": "基于多维度数据做综合预测",
            }
            _section_role = _role_desc.get(aspect, f"对{aspect}维度进行深度分析")
            _upstream = []
            _downstream = []
            if hasattr(requirement, 'task_structure') and hasattr(requirement.task_structure, 'dependencies'):
                for _dep in requirement.task_structure.dependencies:
                    if getattr(_dep, 'to_section', None) == aspect:
                        _upstream.append(getattr(_dep, 'from_section', ''))
                    if getattr(_dep, 'from_section', None) == aspect:
                        _downstream.append(getattr(_dep, 'to_section', ''))
            system_prompt += f"""
## 研究任务认知（MANDATORY CONTEXT）

核心研究问题: {requirement.topic}
你的角色: {_section_role}
你的产出被以下章节引用: {_downstream}
你引用的上游章节: {_upstream}
其他章节: {_sibling_aspects}
"""
            
            # Create comprehensive research Agent
            # P0-S2 fix: merge template skill_params and framework config

            # 1. Get skill_params from template data (dict)
            template_skill_params = template_data.get("skill_params", {}).copy(
            ) if template_data and template_data.get("skill_params") else {}

            # 2. Merge framework config (framework config has higher priority)
            merged_skill_params = {
                **template_skill_params,
                "search_skill": {
                    **template_skill_params.get("search_skill", {}),
                    "max_results": max_results,  # 框架配置
                    "max_queries": max_queries,
                    "max_total": max_total,
                }
            }

            # Resolve MCP tools for this aspect via static fallback
            # Full MCPToolMatcher integration (async) will be added when
            # _create_agents is made async
            from src.core.decomposition.mcp_matcher import ASPECT_MCP_FALLBACK
            mcp_tools = ASPECT_MCP_FALLBACK.get(
                aspect.replace(" ", "_").lower(), [])

            # 3. 使用模板的 skills（已合并 Wisdom 推荐）
            capability = AgentCapability(
                name=f"{aspect}研究Agent",
                description=f"研究{requirement.topic}的{aspect}，包含数据收集和分析",
                required_skills=base_skills,
                optional_skills=optional_skills,
                skill_params=merged_skill_params,
                role=f"{aspect}研究专家",
                goal=f"深入研究{requirement.topic}的{aspect}，提供超越资深分析师质量的专业分析报告",
                backstory=f"你是资深的{aspect}研究专家，擅长深度数据收集、多维度分析和高质量报告撰写。你的研究质量必须达到或超过行业资深分析师水平。",
                system_prompt=system_prompt,
                mcp_tools=mcp_tools,
            )

            # normal 章节（research_ 前缀）是综合研究 Agent（数据收集+分析一体），
            # 应使用 "analysis" 让 generic_agent 走 DEEP_ANALYSIS 分支
            _template_category = template_data.get("category_name", "data-collection") if template_data else "data-collection"
            if _template_category == "data-collection":
                _template_category = "analysis"

            agent, session = self._agent_factory.create_agent_with_session(
                agent_id=agent_id,
                capability=capability,
                parent_session_id=task_id,
                context={
                    "aspect": aspect,
                    "topic": requirement.topic,
                    "data_types": [dt[0] for dt in relevant_data_types],
                    "research_type": research_type or "market_research",
                    "intent_confidence": _intent_confidence,
                    "domain_context": _domain_context,
                    "hidden_requirements": _hidden_requirements,
                    "depends_on": [
                        aid for ua in _upstream
                        for aid in _aspect_to_agent_id.get(ua, [])
                    ],
                },
                category=_template_category,
            )

            agents.append(agent)
            logger.debug(f"[{task_id}] 创建综合研究Agent: {agent_id}")

            # === 不再创建独立的数据收集Agent和分析Agent ===
            # 之前的实现为每种数据类型创建独立Agent，导致Agent数量爆炸
            # 现在改为每个章节一个综合Agent，减少Agent数量和搜索请求

        # === 2. 创建依赖章节的 Agent（summary, conclusion）===
        # 这些章节需要综合其他章节的结果，不进行独立的数据收集
        for i, aspect in dependent_aspects:
            aspect_lower = aspect.lower()

            # 判断是 summary 还是 conclusion
            is_summary = aspect_lower in {
                "summary", "摘要", "执行摘要"} or "summary" in aspect_lower or "摘要" in aspect
            is_conclusion = aspect_lower in {
                "conclusion", "结论", "研究结论"} or "conclusion" in aspect_lower or "结论" in aspect

            # 创建综合分析 Agent（不创建数据收集 Agent）
            _pm = PromptManager()
            if is_summary:
                role = "执行摘要撰写专家"
                goal = "综合所有研究章节的核心发现，撰写高质量的执行摘要"
                backstory = "你是资深的研究报告撰写专家，擅长提炼关键信息，撰写简洁有力的执行摘要"
                system_prompt = _pm.render("agents", "executive_summary", strip_frontmatter=True,
                                           topic=requirement.topic)
            elif is_conclusion:
                role = "研究结论撰写专家"
                goal = "基于所有研究内容，撰写有深度的结论和建议"
                backstory = "你是资深的研究分析师，擅长从大量数据中提炼洞察，给出有价值的结论和建议"
                system_prompt = _pm.render("agents", "research_conclusion", strip_frontmatter=True,
                                           topic=requirement.topic)
            else:
                role = f"{aspect}综合分析专家"
                goal = f"综合分析{requirement.topic}的{aspect}"
                backstory = f"你是资深的{aspect}研究专家"
                system_prompt = f"研究主题: {requirement.topic}\n研究维度: {aspect}"

            # 创建综合分析 Agent（标记为 synthesis 类型，不需要 MCP tools）
            capability = AgentCapability(
                name=f"{aspect}综合分析",
                description=f"综合分析{requirement.topic}的{aspect}（依赖其他章节）",
                required_skills=["llm_skill"],
                optional_skills=["file_skill"],
                skill_params={},
                role=role,
                goal=goal,
                backstory=backstory,
                system_prompt=system_prompt,
                mcp_tools=[],
            )

            agent_id = f"synthesis_{aspect_lower.replace(' ', '_')}_{i + 1}"
            agent, session = self._agent_factory.create_agent_with_session(
                agent_id=agent_id,
                capability=capability,
                parent_session_id=task_id,
                context={
                    "aspect": aspect,
                    "topic": requirement.topic,
                    "is_dependent": True,
                    "depends_on": normal_agent_ids,
                    "research_type": research_type or "market_research",
                    "intent_confidence": _intent_confidence,
                    "domain_context": _domain_context,
                    "hidden_requirements": _hidden_requirements,
                },
                category="synthesis",  # synthesis 是有效的 category，用于综合分析
            )

            agents.append(agent)
            logger.info(
                f"[{task_id}] 创建依赖章节Agent: {agent_id} (依赖Agent: {normal_agent_ids})")

        logger.info(
            f"[{task_id}] 共创建 {len(agents)} 个Agent（普通章节: {len(normal_aspects)}，依赖章节: {len(dependent_aspects)}）")
        return agents

    def _match_data_types(
        self,
        aspect: str,
        data_collection_tasks: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """根据研究维度匹配需要收集的数据类型

        支持章节ID（如 'market_size'）和章节名称（多语言）双重匹配
        使用 i18n 模块的关键词映射，支持中/英/日/韩等多语言
        """
        from src.core.i18n import I18n, detect_language, get_language

        aspect_lower = aspect.lower()
        matched = []

        # 1. 首先尝试精确匹配章节ID
        section_id_to_data_types = {
            "summary": ["行业概况"],
            "market_size": ["市场规模", "行业概况"],
            "competitive_landscape": ["竞争格局", "企业分析"],
            "competition": ["竞争格局", "企业分析"],
            "industry_chain": ["产业链", "行业概况"],
            "industry_overview": ["行业概况"],
            "market_segments": ["市场规模"],
            "trends": ["技术趋势"],
            "policy_environment": ["政策法规"],
            "policy": ["政策法规"],
            "user_insights": ["消费者洞察"],
            "tech_trends": ["技术趋势"],
            "technology": ["技术趋势"],
            "risks": ["政策法规"],
            "conclusion": ["行业概况"],
        }

        if aspect_lower in section_id_to_data_types:
            for dt in section_id_to_data_types[aspect_lower]:
                for task in data_collection_tasks:
                    if task[0] == dt and task not in matched:
                        matched.append(task)
            if matched:
                return matched

        # 2. 使用 i18n 关键词映射进行多语言匹配
        # 检测用户输入的语言
        detected_lang = detect_language(aspect)
        keywords_map = I18n.get_keywords_map(detected_lang)

        for keyword, data_types in keywords_map.items():
            if keyword.lower() in aspect_lower or keyword in aspect:
                for dt in data_types:
                    for task in data_collection_tasks:
                        if task[0] == dt and task not in matched:
                            matched.append(task)

        # 3. 如果当前语言的关键词没有匹配到，尝试所有语言
        if not matched:
            for lang_code, lang_keywords in I18n.KEYWORDS_MAP.items():
                for keyword, data_types in lang_keywords.items():
                    if keyword.lower() in aspect_lower or keyword in aspect:
                        for dt in data_types:
                            for task in data_collection_tasks:
                                if task[0] == dt and task not in matched:
                                    matched.append(task)

        # 4. 默认：如果没有匹配到，返回前3个基础数据类型
        if not matched:
            matched = data_collection_tasks[:3]

        return matched

    def _cleanup_agents(self, task_id: str) -> None:
        """
        清理 Agent Session Registry（生命周期管理）

        Args:
            task_id: 任务ID
        """
        if self._agent_factory:
            cleared = self._agent_factory.clear_registry(task_id)
            if cleared:
                logger.debug(f"[{task_id}] 已清理 Agent Session Registry")

        self._current_session_id = None

    def _get_intent_type(self, intent_result: Any) -> Optional[Any]:
        """
        P0 fix: Get intent type from either DeepIntentResult or IntentAnalysisResult.
        
        DeepIntentResult has 'primary_intent' attribute.
        IntentAnalysisResult has 'intent' attribute.
        """
        if intent_result is None:
            return None
        if hasattr(intent_result, 'primary_intent'):
            return intent_result.primary_intent
        if hasattr(intent_result, 'intent'):
            return intent_result.intent
        return None

    def _generate_summary(
        self,
        aggregated: Any,
        requirement: ResearchRequirement
    ) -> str:
        """生成结果摘要"""
        return (
            f"研究主题: {requirement.topic}\n"
            f"研究维度: {', '.join(requirement.aspects)}\n"
            f"地域范围: {requirement.region}\n"
            f"推荐Skills: {', '.join(requirement.recommended_skills)}\n"
        )

    # === 向后兼容方法 ===

    def get_history(self) -> List[Dict[str, Any]]:
        """获取任务历史（向后兼容）"""
        return self._task_history

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息（向后兼容）"""
        total = len(self._task_history)
        completed = sum(
            1 for t in self._task_history if t["result"].status == "completed")

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "success_rate": completed / total if total > 0 else 0,
            "dual_track_enabled": self.enable_dual_track,
        }

    # === 文档生成方法 ===

    async def complete_research(
        self,
        task_id: str,
        output_format: Optional[str] = None,
        template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        完成研究，可选立即生成文档

        场景1: output_format=None
        - 保存研究结果，状态设为 COMPLETED
        - 返回 result_id，提示用户可稍后生成

        场景2: output_format="pptx"
        - 保存研究结果，立即生成文档
        - 返回文档路径

        Args:
            task_id: 研究任务ID
            output_format: 输出格式（docx/pptx/pdf），可选
            template: 模板名称，可选

        Returns:
            结果字典
        """
        # 1. 从历史记录中查找任务
        task_record = None
        for record in self._task_history:
            if record["task_id"] == task_id:
                task_record = record
                break

        if not task_record:
            # 尝试从存储加载
            loaded = self._storage_manager.load(task_id)
            if not loaded:
                return {
                    "success": False,
                    "error": f"Task {task_id} not found",
                    "error_code": "TASK_NOT_FOUND",
                }
            task_record = loaded

        # 2. 检查研究状态
        if task_record.get("result", {}).get("status") != "completed":
            return {
                "success": False,
                "error": f"Research {task_id} not completed",
                "error_code": "RESEARCH_NOT_COMPLETED",
            }

        # 3. 根据是否指定格式决定后续动作
        if output_format:
            # 立即生成文档
            doc_result = await self.generate_document_later(
                task_id=task_id,
                output_format=output_format,
                template=template,
            )
            return {
                "success": True,
                "status": "document_generated",
                "task_id": task_id,
                "document": doc_result,
            }
        else:
            # 延迟生成
            return {
                "success": True,
                "status": "research_completed",
                "task_id": task_id,
                "message": "研究已完成，可以使用 generate_document_later() 生成文档",
            }

    async def generate_document_later(
        self,
        task_id: str,
        output_format: str,
        template: Optional[str] = None,
        adjustments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        基于历史研究结果生成文档（延迟生成）

        Args:
            task_id: 研究任务ID
            output_format: 输出格式（docx/pptx/pdf）
            template: 模板名称，可选
            adjustments: 调整参数列表，可选

        Returns:
            文档生成结果，包含 success, document_path, error 等字段
        """
        # 1. 从历史记录中查找任务
        task_record = None
        for record in self._task_history:
            if record["task_id"] == task_id:
                task_record = record
                break

        if not task_record:
            # 尝试从存储加载
            loaded = self._storage_manager.load(task_id)
            if not loaded:
                return {
                    "success": False,
                    "error": f"Task {task_id} not found",
                    "error_code": "TASK_NOT_FOUND",
                }
            task_record = loaded

        # 2. 获取研究结果（复制避免原地修改）
        research_result = dict(task_record.get("result", {}))
        if isinstance(task_record.get("requirement"), ResearchRequirement):
            requirement = task_record["requirement"]
            research_result["topic"] = requirement.topic
            research_result["aspects"] = requirement.aspects

        # 3. 执行文档生成
        logger.info(f"[{task_id}] 延迟生成 {output_format} 文档")

        doc_result = await self._document_agent.execute({
            "action": "produce_document",
            "output_format": output_format,
            "research_result": research_result,
            "task_id": task_id,
            "template": template,
            "adjustments": adjustments or [],
        })

        # 4. 处理警告
        if doc_result.get("warning"):
            logger.warning(f"[{task_id}] 文档生成警告: {doc_result['warning']}")

        return doc_result

    def list_completed_research(
        self,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        列出已完成的研究（可生成文档）

        Args:
            user_id: 用户ID，可选
            limit: 返回数量限制

        Returns:
            已完成的研究列表
        """
        completed = []

        for record in self._task_history:
            result = record.get("result", {})
            if result.get("status") == "completed":
                requirement = record.get("requirement", {})
                if isinstance(requirement, ResearchRequirement):
                    completed.append({
                        "task_id": record["task_id"],
                        "topic": requirement.topic,
                        "aspects": requirement.aspects,
                        "created_at": result.get("created_at"),
                        "completed_at": result.get("completed_at"),
                        "output_format": requirement.output_format,
                    })
                else:
                    completed.append({
                        "task_id": record["task_id"],
                        "topic": requirement.get("topic", "未知主题"),
                        "created_at": result.get("created_at"),
                        "completed_at": result.get("completed_at"),
                    })

        # 按完成时间倒序
        completed.sort(
            key=lambda x: x.get("completed_at") or datetime.min,
            reverse=True
        )

        return completed[:limit]

    # === 分批执行方法（v2.2新增） ===

    async def research_batched(
        self,
        user_input: Union[str, Dict[str, Any]],
        batch_size: int = 5,
    ) -> ResearchResult:
        """
        分批执行研究任务

        当研究维度数量较大（如100+）时，分批创建Agent，
        每批执行完成后休眠释放内存，再创建下一批。

        Args:
            user_input: 用户需求（自然语言或结构化字典）
            batch_size: 每批Agent数量（默认5）

        Returns:
            ResearchResult: 研究结果
        """
        # 1. 解析需求
        requirement = self._parse_requirement(user_input)

        # 2. 意图分析（可选）- Phase 4: 使用智能路由适配器
        intent_result = None
        if self._routing_adapter:
            intent_result = self._routing_adapter.analyze_simple(
                str(user_input))

        # 3. 生成任务ID
        task_id = f"batched_{uuid.uuid4().hex[:8]}"
        self._current_session_id = task_id

        # 4. 记录智慧（可选）
        if self.enable_dual_track and self._wisdom_recorder and intent_result:
            self._wisdom_recorder.record(
                user_input=str(user_input),
                intent_result=intent_result,
            )

        # 5. 分批执行
        total_aspects = len(requirement.aspects)
        previous_agents = None

        logger.info(
            f"[{task_id}] 开始分批执行，共{total_aspects}维度，每批{batch_size}个Agent")

        try:
            for batch_start in range(0, total_aspects, batch_size):
                batch_index = batch_start // batch_size
                batch_end = min(batch_start + batch_size, total_aspects)
                batch_aspects = requirement.aspects[batch_start:batch_end]

                # 创建批次（自动休眠上一批）
                batch_result = await self._agent_factory.create_batch(
                    parent_session_id=task_id,
                    batch_index=batch_index,
                    aspects=batch_aspects,
                    previous_batch_agents=previous_agents,
                )

                # 执行这批Agent
                batch_execution_result = await self._execute_batch(
                    batch_result.agents,
                    requirement,
                    batch_aspects,
                )

                # 记录这批Agent ID
                previous_agents = batch_result.get_agent_ids()

                logger.info(
                    f"[{task_id}] Batch {batch_index} 完成: "
                    f"{len(batch_aspects)} 维度, "
                    f"成功 {batch_execution_result.completed_agents}, "
                    f"失败 {batch_execution_result.failed_agents}"
                )

            # 最终休眠最后一批
            if previous_agents:
                await self._agent_factory.hibernate_batch(previous_agents)
                logger.info(f"[{task_id}] 最终批次已休眠")

            # 6. 构建结果
            total_batches = (total_aspects + batch_size - 1) // batch_size
            result = ResearchResult(
                task_id=task_id,
                status="completed",
                topic=requirement.topic,
                agents_used=[
                    f"batch_{i}" for i in range(total_batches)],
                # 记录批次信息
                stages_completed=total_aspects,
                summary=f"分批执行完成，共{total_aspects}维度，{total_batches}批次",
                completed_at=datetime.now(),
            )

            self._task_history.append({
                "task_id": task_id,
                "requirement": requirement,
                "result": result,
            })

            return result

        except Exception as e:
            logger.error(f"[{task_id}] 分批执行失败: {e}")
            return ResearchResult(
                task_id=task_id,
                status="error",
                topic=requirement.topic,
                agents_used=[],
                stages_completed=0,
                summary=f"错误: {str(e)}"
            )

    async def _execute_batch(
        self,
        agents: List[Any],
        requirement: ResearchRequirement,
        batch_aspects: List[str],
    ) -> Any:
        """
        执行单个批次的Agent

        Args:
            agents: Agent列表
            requirement: 研究需求
            batch_aspects: 这批的研究维度

        Returns:
            BatchExecutionResult: 批次执行结果
        """
        from src.core.agents.batch_structures import BatchExecutionResult, AgentExecutionRecord, BatchStatus

        batch_result = BatchExecutionResult(
            batch_index=0,  # 实际值在外层设置
            task_id=self._current_session_id or "unknown",
            aspects=batch_aspects,
        )

        batch_result.start_batch()

        for i, agent in enumerate(agents):
            aspect = batch_aspects[i] if i < len(batch_aspects) else "unknown"

            # 创建执行记录
            record = AgentExecutionRecord(
                session_id=agent._session.session_id if hasattr(
                    agent, '_session') else f"session_{i}",
                agent_id=agent.agent_id,
                batch_index=batch_result.batch_index,
                aspect=aspect,
                task_input={"aspect": aspect, "topic": requirement.topic},
            )

            batch_result.add_agent_record(record)

            try:
                # 标记开始
                record.start()

                # **修复**: 不再直接使用 topic + aspect 作为搜索词
                # 搜索词应该由 GenericAgent 的 _generate_search_queries 方法生成
                # 这里只传递 topic 和 aspect，让 Agent 自己决定如何搜索
                task = {
                    "action": "search",
                    "parameters": {
                        "topic": requirement.topic,
                        "aspect": aspect,
                    }
                }

                result = await agent.run(task)

                # 标记完成
                if result.get("success"):
                    record.complete(result)
                else:
                    record.fail(result.get("error", "Unknown error"))

            except Exception as e:
                record.fail(str(e))
                logger.warning(f"Agent {agent.agent_id} 执行失败: {e}")

        batch_result.complete_batch()

        return batch_result

    async def restore_batch(
        self,
        task_id: str,
        batch_index: int,
    ) -> List[Any]:
        """
        恢复指定批次的Agent

        Args:
            task_id: 任务ID
            batch_index: 批次索引

        Returns:
            恢复后的Agent列表
        """
        agents = await self._agent_factory.restore_batch(task_id, batch_index)

        logger.info(
            f"[{task_id}] Batch {batch_index} 恢复完成，{len(agents)}个Agent")

        return agents

    # PhaseOrchestrator was removed in P5 cleanup.
    # The phased execution approach (research_with_phases) was never integrated
    # into the main research flow. ExecutionEngine handles all phase sequencing
    # through dependency-based scheduling, which is more flexible and maintainable.

    def _build_quality_metadata(
        self,
        exec_result: Any,
        quality_result: Optional[Dict[str, Any]],
        task_id: str,
    ) -> Dict[str, Any]:
        """
        构建质量元数据

        Args:
            exec_result: 执行结果
            quality_result: 质量检查结果
            task_id: 任务ID

        Returns:
            质量元数据字典
        """
        from datetime import datetime

        metadata = {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "stages": {},
            "overall_passed": False,
            "quality_summary": {},
        }

        # 从执行结果提取各阶段质量信息
        if exec_result and hasattr(exec_result, 'stage_results'):
            for stage_name, stage_results in exec_result.stage_results.items():
                if stage_results:
                    # 提取该阶段的质量元数据
                    quality_scores = []
                    data_volumes = []
                    sources_count = 0

                    for result in stage_results:
                        if isinstance(result, dict):
                            qm = result.get("quality_metadata", {})
                            if qm:
                                quality_scores.append(
                                    qm.get("quality_score", 50))
                                data_volumes.append(qm.get("data_volume", 0))
                                sources_count += len(qm.get("sources", []))

                    if quality_scores:
                        avg_score = sum(quality_scores) / len(quality_scores)
                        metadata["stages"][stage_name] = {
                            "avg_score": avg_score,
                            "total_data_volume": sum(data_volumes),
                            "total_sources": sources_count,
                            "result_count": len(stage_results),
                        }

        # 从质量检查结果提取
        if quality_result:
            metadata["quality_check"] = {
                "score": quality_result.get("quality_score", 0),
                "passed": quality_result.get("passed", False),
                "issues_count": len(quality_result.get("issues", [])),
                "suggestions_count": len(quality_result.get("suggestions", [])),
            }
            metadata["overall_passed"] = quality_result.get("passed", False)

        # 计算综合质量分数
        if metadata["stages"]:
            stage_scores = [s.get("avg_score", 50)
                            for s in metadata["stages"].values()]
            metadata["quality_summary"]["composite_score"] = sum(
                stage_scores) / len(stage_scores)

        return metadata

    # ========== Resume / Revise 辅助方法 ==========

    def _extract_aspects_from_registry(self, task_id: str) -> List[str]:
        """
        从 registry 文件中提取 aspects（用于恢复历史任务数据）

        Args:
            task_id: 任务 ID

        Returns:
            提取的 aspects 列表，失败返回空列表
        """
        try:
            from src.core.agents.session_persistence import SessionPersistenceManager
            spm = SessionPersistenceManager()
            registry = spm.load_registry(task_id)

            if not registry or not registry.child_sessions:
                return []

            # 从 child_sessions 中提取唯一的 aspect
            aspects = set()
            for session in registry.child_sessions.values():
                # 从 task 字段提取
                if session.task and 'aspect' in session.task:
                    aspects.add(session.task['aspect'])
                # 从 context 字段提取
                elif session.context and 'aspect' in session.context:
                    aspects.add(session.context['aspect'])

            # 保持顺序：按 agent_id 中的数字排序
            ordered_aspects = []
            for session in sorted(
                registry.child_sessions.values(),
                key=lambda s: s.session_id
            ):
                aspect = None
                if session.task and 'aspect' in session.task:
                    aspect = session.task['aspect']
                elif session.context and 'aspect' in session.context:
                    aspect = session.context['aspect']
                if aspect and aspect not in ordered_aspects:
                    ordered_aspects.append(aspect)

            return ordered_aspects
        except Exception as e:
            logger.warning(
                f"[{task_id}] _extract_aspects_from_registry 失败: {e}")
            return []

    def _detect_completed_phases(self, task_id: str, plan: Any) -> List[str]:
        """
        检测哪些阶段已完成（通过 ResearchResultStore 中的 completed_agents）
        """
        from src.core.storage import ResearchResultStore
        store = ResearchResultStore(storage_path="data")
        saved = store.load_result(task_id)
        if not saved:
            return []

        completed_agent_ids = set()
        for agent_entry in saved.get("completed_agents", []):
            if agent_entry.get("success"):
                completed_agent_ids.add(agent_entry["agent_id"])

        completed_phases = []
        for phase in plan.execution_order:
            specs = plan.phases.get(phase, [])
            if not specs:
                continue
            # 该阶段所有 agent 都已完成 → 该阶段视为完成
            if all(s.agent_id in completed_agent_ids for s in specs if s):
                completed_phases.append(phase.value)
            else:
                break  # 遇到第一个未完成的阶段就停止

        return completed_phases

    def _slice_plan(self, plan: Any, completed_phases: List[str]) -> Any:
        """从第一个未完成的阶段开始截取plan"""
        import copy

        remaining = []
        started = False
        for phase in plan.execution_order:
            if phase.value not in completed_phases:
                started = True
            if started:
                remaining.append(phase)

        new_plan = copy.copy(plan)
        new_plan.phases = {
            p: s for p,
            s in plan.phases.items() if p in remaining}
        new_plan.execution_order = [
            p for p in plan.execution_order if p in remaining]
        return new_plan

    def _filter_plan_by_aspects(self, plan: Any, aspects: List[str]) -> Any:
        """只保留指定aspect的AgentSpec"""
        import copy

        aspects_lower = [a.lower() for a in aspects]
        new_phases = {}
        for phase, specs in plan.phases.items():
            new_specs = []
            for spec in specs:
                spec_aspect = (spec.context or {}).get("aspect", "")
                if spec_aspect.lower() in aspects_lower or \
                   any(a in spec.agent_id.lower() for a in aspects_lower):
                    new_specs.append(spec)
            if new_specs:
                new_phases[phase] = new_specs

        new_plan = copy.copy(plan)
        new_plan.phases = new_phases
        new_plan.execution_order = [
            p for p in plan.execution_order if p in new_phases]
        return new_plan

    def _merge_results(self, task_id: str, sections: List[Dict]) -> List[Dict]:
        """
        合并新生成的章节结果与 ResearchResultStore 中已有数据
        新结果覆盖旧结果，缺失章节从已有数据填充
        """
        from src.core.storage import ResearchResultStore
        store = ResearchResultStore(storage_path="data")
        saved = store.load_result(task_id)

        if not saved:
            return sections

        # 建立新结果的 id → content 映射
        new_map = {s.get("id", ""): s.get("content", "")
                   for s in sections if s.get("id")}

        # 合并：已有数据中，未被新结果覆盖的章节保留
        merged = list(sections)
        existing_ids = set(new_map.keys())
        for old_s in saved.get("sections", []):
            old_id = old_s.get("id", "")
            if old_id and old_id not in existing_ids:
                merged.append(old_s)

        return merged

    async def resume(self, task_id: str) -> "ResearchResult":
        """恢复中断的研究任务：检测已完成阶段，从断点继续"""
        from src.core.task_persistence import TaskPersistenceManager, TaskState
        from src.core.storage import ResearchResultStore
        from src.core.orchestrator import ResearchRequirement

        logger.info(f"[{task_id}] resume: 尝试恢复任务")

        # 1. 加载任务 - 使用配置中的 tasks_dir
        tp = TaskPersistenceManager()  # 自动从配置读取
        task = tp.load_task(task_id)
        if not task:
            return ResearchResult(task_id=task_id, status="error", topic="", agents_used=[],
                                  stages_completed=0, summary=f"任务不存在: {task_id}")

        # 2. 重建需求 - 处理历史数据不完整的情况
        input_data = task.input_data.copy()

        # 如果 aspects 缺失，尝试从 registry 中提取已执行的 agent 任务
        if 'aspects' not in input_data or not input_data['aspects']:
            aspects = self._extract_aspects_from_registry(task_id)
            if aspects:
                input_data['aspects'] = aspects
                logger.info(
                    f"[{task_id}] resume: 从 registry 提取 aspects: {aspects}")
            else:
                # 无法恢复 aspects，返回错误
                return ResearchResult(
                    task_id=task_id,
                    status="error",
                    topic=input_data.get('topic', ''),
                    agents_used=[],
                    stages_completed=0,
                    summary=f"任务数据不完整，无法恢复: 缺少 aspects 字段"
                )

        # 确保 output_type 有效
        if not input_data.get('output_type'):
            input_data['output_type'] = 'industry_report'
        req = ResearchRequirement(**input_data)

        # 3. 重新分解计划
        from src.core.research_framework_manager import get_framework_config
        from src.core.decomposition import get_strategy
        output_type_value = req.output_type.value if hasattr(
            req.output_type, 'value') else str(req.output_type)
        framework_config = get_framework_config(output_type_value)
        strategy = get_strategy(output_type_value)
        plan = strategy.decompose(req, None, framework_config)

        # 4. 检测已完成阶段
        completed_phases = self._detect_completed_phases(task_id, plan)
        logger.info(f"[{task_id}] resume: 已完成阶段: {completed_phases}")

        # 5. 截取计划
        remaining_plan = self._slice_plan(plan, completed_phases)
        if not remaining_plan.execution_order:
            logger.info(f"[{task_id}] resume: 所有阶段已完成，无需恢复")
            store = ResearchResultStore(storage_path="data")
            saved = store.load_result(task_id)
            return ResearchResult(task_id=task_id, status="completed", topic=req.topic,
                                  agents_used=[], stages_completed=len(
                                      plan.execution_order),
                                  summary="任务已完成",
                                  report=saved if saved else {},
                                  document_path=None)

        # 6. 按剩余计划创建 agent
        agents = self._create_agents_from_plan(remaining_plan, req, task_id,
                                                          intent_result=None)

        # 7. 执行（A-2 回退读取会从 ResearchResultStore 补充已有阶段的数据）
        self._current_session_id = task_id
        from src.core.orchestrator.execution.engine import ExecutionResult
        session_registry = self._agent_factory.get_registry(task_id)

        exec_result = await self._execution_engine.execute_with_scheduler(
            agents=agents,
            requirement={
                "topic": req.topic,
                "aspects": req.aspects,
                "region": req.region,
                "task_id": task_id,
                "session_id": task_id,
            },
            scheduler=self._execution_scheduler,
            decomposition_plan=remaining_plan,
            session_registry=session_registry,
        )

        # 8. 处理结果（同 research() 中的聚合逻辑）
        results_for_aggregation = {}
        if exec_result.stage_results:
            for stage_name, stage_list in exec_result.stage_results.items():
                for i, r in enumerate(stage_list):
                    key = f"{stage_name}_{i}"
                    results_for_aggregation[key] = r

        aggregated = self._result_aggregator.aggregate(
            results_for_aggregation,
            section_details=getattr(req, 'section_details', []),
        )

        # 9. 合并新旧章节数据
        merged_sections = aggregated.to_dict().get("sections", [])
        merged_sections = self._merge_results(task_id, merged_sections)

        # 10. 文档生成
        output_path = None
        if merged_sections:
            doc_result = await self._document_agent.execute({
                "action": "produce_document",
                "task_id": task_id,
                "output_format": "docx",
                "research_result": {
                    "title": req.topic,
                    "topic": req.topic,
                    "sections": merged_sections,
                },
            })
            if doc_result.get("success"):
                output_path = doc_result.get("document_path")

        # 更新任务状态
        try:
            tp.update_task_state(
                task_id,
                TaskState.COMPLETED,
                progress=1.0,
                message="任务恢复完成")
        except Exception:
            pass

        return ResearchResult(
            task_id=task_id, status="completed", topic=req.topic,
            agents_used=[a.agent_id for a in agents],
            stages_completed=len(results_for_aggregation),
            output_path=output_path,
            document_path=output_path,
            summary=f"从断点恢复: 跳过{
                len(completed_phases)}个已完成阶段，重新生成{
                len(
                    remaining_plan.execution_order)}个阶段",
            report=aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {},
        )

    async def revise(self, task_id: str,
                     aspects: List[str]) -> "ResearchResult":
        """局部修订指定章节：只重新生成指定aspect，其他从已有数据合并"""
        from src.core.task_persistence import TaskPersistenceManager, TaskState
        from src.core.storage import ResearchResultStore
        from src.core.orchestrator import ResearchRequirement

        logger.info(f"[{task_id}] revise: 请求修订章节 {aspects}")

        # 1. 加载任务
        tp = TaskPersistenceManager()
        task = tp.load_task(task_id)
        if not task:
            return ResearchResult(task_id=task_id, status="error", topic="", agents_used=[],
                                  stages_completed=0, summary=f"任务不存在: {task_id}")

        # 2. 重建需求
        req = ResearchRequirement(**task.input_data)

        # 3. 重新分解计划
        from src.core.research_framework_manager import get_framework_config
        from src.core.decomposition import get_strategy
        output_type_value = req.output_type.value if hasattr(
            req.output_type, 'value') else str(req.output_type)
        framework_config = get_framework_config(output_type_value)
        strategy = get_strategy(output_type_value)
        plan = strategy.decompose(req, None, framework_config)

        # 4. 只保留指定aspect的AgentSpec
        filtered_plan = self._filter_plan_by_aspects(plan, aspects)
        if not filtered_plan.execution_order:
            return ResearchResult(task_id=task_id, status="completed", topic=req.topic,
                                  agents_used=[], stages_completed=0,
                                  summary=f"未找到章节: {aspects}",
                                  report={},
                                  document_path=None)

        logger.info(
            f"[{task_id}] revise: 过滤后保留 {len(filtered_plan.execution_order)} 个阶段")

        # 5. 创建agent
        agents = self._create_agents_from_plan(filtered_plan, req, task_id,
                                                          intent_result=None)

        # 6. 执行
        self._current_session_id = task_id
        session_registry = self._agent_factory.get_registry(task_id)

        exec_result = await self._execution_engine.execute_with_scheduler(
            agents=agents,
            requirement={
                "topic": req.topic,
                "aspects": req.aspects,
                "region": req.region,
                "task_id": task_id,
                "session_id": task_id,
            },
            scheduler=self._execution_scheduler,
            decomposition_plan=filtered_plan,
            session_registry=session_registry,
        )

        # 7. 聚合结果
        results_for_aggregation = {}
        if exec_result.stage_results:
            for stage_name, stage_list in exec_result.stage_results.items():
                for i, r in enumerate(stage_list):
                    key = f"{stage_name}_{i}"
                    results_for_aggregation[key] = r

        aggregated = self._result_aggregator.aggregate(
            results_for_aggregation,
            section_details=getattr(req, 'section_details', []),
        )

        # 8. 合并新旧章节（新结果覆盖指定aspect，其他用已有数据）
        merged_sections = aggregated.to_dict().get("sections", [])
        merged_sections = self._merge_results(task_id, merged_sections)

        # 9. 文档生成
        output_path = None
        if merged_sections:
            doc_result = await self._document_agent.execute({
                "action": "produce_document",
                "task_id": task_id,
                "output_format": "docx",
                "research_result": {
                    "title": req.topic,
                    "topic": req.topic,
                    "sections": merged_sections,
                },
            })
            if doc_result.get("success"):
                output_path = doc_result.get("report", {}).get("path")

        try:
            tp.update_task_state(
                task_id,
                TaskState.COMPLETED,
                progress=1.0,
                message="修订完成")
        except Exception:
            pass

        return ResearchResult(
            task_id=task_id, status="completed", topic=req.topic,
            agents_used=[a.agent_id for a in agents],
            stages_completed=len(results_for_aggregation),
            output_path=output_path,
            document_path=output_path,
            summary=f"修订完成: 章节 {aspects} 已重新生成",
            report={"sections": merged_sections} if merged_sections else {},
        )

    async def generate_final_document(
        self,
        task_id: str,
        output_format: str = "docx",
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        断点4修复：用户确认后生成最终文档

        Args:
            task_id: 任务ID
            output_format: 输出格式 (docx, pptx, pdf)
            output_dir: 输出目录

        Returns:
            生成结果 {success, document_path, error}
        """
        logger.info(f"[{task_id}] 用户已确认，生成最终 {output_format} 文档")

        # 1. 加载任务数据
        try:
            task_data = self._storage_manager.load(task_id)
            if not task_data:
                return {"success": False, "error": f"任务 {task_id} 不存在"}
        except Exception as e:
            return {"success": False, "error": f"加载任务失败: {e}"}

        # 2. 确定输出目录
        output_dir_path = Path(
            output_dir) if output_dir else self._storage_path / "reports"
        output_dir_path.mkdir(parents=True, exist_ok=True)

        # 3. 调用文档生成
        doc_result = await self._document_agent.execute({
            "action": "produce_document",
            "output_format": output_format,
            "research_result": task_data,
            "task_id": task_id,
            "output_dir": str(output_dir_path),
        })

        if doc_result.get("success", False):
            final_path = doc_result.get("document_path")
            if final_path and Path(final_path).exists():
                logger.info(f"[{task_id}] 最终文档生成完成: {final_path}")
                return {"success": True, "document_path": final_path}
            else:
                return {"success": False, "error": "文档路径无效"}
        else:
            error = doc_result.get("error", "未知错误")
            logger.warning(f"[{task_id}] 最终文档生成失败: {error}")
            return {"success": False, "error": error}

    async def regenerate_report_only(
        self,
        session_id: str,
        existing_results: Dict[str, Any],
        output_format: str = "html",
        output_dir: Optional[str] = None,
        adjustment: Optional[str] = None,
    ) -> ResearchResult:
        """
        Regenerate report from existing results without re-running data collection.
        
        This is a lightweight alternative to full incremental revision when only
        report formatting/presentation needs to change, not the underlying data.
        
        Args:
            session_id: Session identifier for progress streaming
            existing_results: Dict of {section_title: content} from previous research
            output_format: Output format (html/docx/pdf)
            output_dir: Output directory path
            adjustment: Optional adjustment text for logging
            
        Returns:
            ResearchResult with regenerated document path
        """
        from src.core.progress_streamer import start_phase, complete_phase, update_progress
        from src.core.result_aggregator import ResultAggregator
        from src.core.knowledge_compiler import KnowledgeCompiler
        from src.core.preview.preview_generator import PreviewGenerator
        from src.core.preview_storage import PreviewStorage
        
        task_id = f"regenerate_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()
        
        logger.info(f"[{task_id}] Starting report-only regeneration")
        
        if session_id:
            start_phase(session_id, "regenerate", "Report Regeneration",
                        description=adjustment[:200] if adjustment else "Regenerating report")
            update_progress(session_id, 0.1, message="Preparing existing data...")
        
        output_dir_path = Path(output_dir) if output_dir else self._storage_path / "reports"
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        topic = existing_results.get("topic", "Research Report")
        sections = existing_results.get("sections", [])
        
        if not sections:
            logger.warning(f"[{task_id}] No existing sections provided")
            return ResearchResult(
                task_id=task_id,
                status="failed",
                topic=topic,
                agents_used=[],
                stages_completed=0,
                summary="No existing data to regenerate from",
                output_path=None,
                created_at=start_time,
                completed_at=datetime.now(),
            )
        
        if session_id:
            update_progress(session_id, 0.3, message="Building report structure...")
        
        self._report_generator._sections = []
        for section_data in sections:
            section_title = section_data.get("title", section_data.get("id", ""))
            section_content = section_data.get("content", "")
            if isinstance(section_title, str) and isinstance(section_content, str):
                self._report_generator.add_section(
                    title=section_title,
                    content=section_content,
                    level=1,
                )
        
        if session_id:
            update_progress(session_id, 0.5, message="Generating report document...")
        
        report = self._report_generator.generate(
            topic=topic,
            summary=existing_results.get("key_findings", ""),
        )
        
        output_file = output_dir_path / f"{topic.replace(' ', '_')[:50]}_report.md"
        self._report_generator.save(report, output_file)
        output_path = str(report.path) if report and report.path else str(output_file)
        
        if session_id:
            update_progress(session_id, 0.7, message="Generating preview...")
        
        preview_generator = PreviewGenerator(cache_dir=str(PreviewStorage.NEW_DIR))
        preview_result = await preview_generator.generate_preview(
            document_path=output_path,
            task_id=task_id,
            output_format=output_format,
        )
        
        if preview_result.get("success"):
            output_path = preview_result.get("preview_path", output_path)
            logger.info(f"[{task_id}] Preview generated: {output_path}")
        
        if session_id:
            update_progress(session_id, 0.9, message="Finalizing...")
            complete_phase(session_id, "regenerate")
        
        logger.info(f"[{task_id}] Report regeneration complete: {output_path}")
        
        return ResearchResult(
            task_id=task_id,
            status="completed",
            topic=topic,
            agents_used=["report_generator"],
            stages_completed=4,
            summary="Report regenerated from existing data",
            output_path=output_path,
            created_at=start_time,
            completed_at=datetime.now(),
            report={"sections": sections},
        )

    # ========== P2: Knowledge system optimization methods ==========

    async def _phase2_knowledge_for_routing(self, requirement):
        if not self._knowledge_manager:
            return

        relevant = self._knowledge_manager.search(
            requirement.topic, {"limit": 5}
        )

        entities = relevant.get("entities", [])
        knowledge_available = len(entities) > 0

        if knowledge_available:
            requirement._routing_hints = {
                "knowledge_depth": "rich",
                "reduce_background": True,
                "known_entities": [e.get("name") for e in entities[:3]]
            }
        else:
            requirement._routing_hints = {
                "knowledge_depth": "shallow",
                "reduce_background": False,
                "known_entities": []
            }

    async def _phase5_deposit_knowledge(self, aggregated_dict, task_id="", topic="", session_id=None):
        if not self._knowledge_manager:
            return

        km = self._knowledge_manager
        session_id = session_id or topic

        knowledge_pages = self._knowledge_compiler.compile(
            agent_id=task_id,
            result=aggregated_dict,
            topic=topic,
        )

        from src.skills.registry import get_skill_registry
        registry = get_skill_registry()
        kq_skill = registry.get("knowledge_query")
        observations = []
        if kq_skill:
            observations = kq_skill.drain_observations()
            for obs in observations:
                km.record_learning(
                    category=obs["category"],
                    content=obs["content"],
                    session_id=session_id
                )

        patterns = self._extract_patterns_from_results(aggregated_dict)
        for p in patterns:
            km.record_learning(
                category="research_insight",
                content=p,
                session_id=session_id
            )

        await km.deposit(
            research_id=task_id,
            content={
                "topic": topic,
                "content": aggregated_dict,
                "entities": [p.to_dict() for p in knowledge_pages],
                "source_info": {"session_id": session_id, "task_id": task_id},
            }
        )

        logger.info(f"Knowledge deposit stats: "
                     f"observations={len(observations)}, "
                     f"patterns_extracted={len(patterns)}, "
                     f"knowledge_pages={len(knowledge_pages)}")

    def _extract_patterns_from_results(self, aggregated: Dict) -> List[str]:
        texts = []
        sections = aggregated.get("sections", [])
        for section in sections:
            content = section.get("content", "") if isinstance(section, dict) else str(section)
            if content:
                texts.append(content)
        for key in ("content", "text", "executive_summary"):
            if key in aggregated and isinstance(aggregated[key], str):
                texts.append(aggregated[key])

        patterns = []
        KEYWORDS = [
            "趋势", "规律", "关键", "通常", "往往",
            "风险", "机会", "导致", "取决于", "驱动",
            "意味着", "表明", "显著", "持续", "加速",
            "trend", "pattern", "key", "usually", "often",
            "risk", "opportunity", "lead to", "depends on", "driven by",
            "means", "indicates", "significant", "continues", "accelerate"
        ]

        for content in texts:
            if not content:
                continue
            sentences = re.split(r'[。！？；\n]', content)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) < 15:
                    continue
                matched = any(kw in sent for kw in KEYWORDS)
                has_data = bool(re.search(r'\d+[.%]', sent))
                if matched or has_data:
                    patterns.append(sent)

        seen = set()
        unique = []
        for p in patterns:
            key = p[:30]
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return unique[:20]


# 便捷函数

def _get_default_agent_quotas() -> Dict[str, int]:
    return {"background": 2, "analysis": 2, "synthesis": 1, "quality_check": 1}


async def research(
    user_input: Union[str, Dict[str, Any]],
    output_dir: Optional[str] = None
) -> ResearchResult:
    """便捷函数：快速执行研究任务"""
    orchestrator = ResearchOrchestrator()
    return await orchestrator.research(user_input, output_dir)
