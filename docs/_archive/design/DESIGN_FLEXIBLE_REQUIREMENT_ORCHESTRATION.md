# Flexible Requirement Orchestration Architecture Design

> **Version**: v1.0  
> **Date**: 2026-04-15  
> **Status**: Design Draft  
> **Purpose**: Support complex combined requirements (industry research + survey, brand research + survey, etc.)

---

## Part 1: Problem Analysis

### 1.1 User Requirement Scenarios

| Scenario | Description | Currently Supported |
|----------|-------------|-------------------|
| **Industry Research + Survey** | Do industry research first, then use survey to verify key assumptions | Not supported |
| **Pure Survey** | Only survey research, generate survey analysis report | Partially supported |
| **Brand Research + Survey** | After brand company research, collect user feedback through survey | Not supported |
| **Pure Industry Research** | Traditional market research report | Supported |

### 1.2 Current Architecture Limitations

```
┌─────────────────────────────────────────────────────────────────┐
│                     Current Architecture Issues                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  IntentGate                                                     │
│  ├── IntentType only has 7 basic types                                  │
│  ├── No SURVEY type                                          │
│  ├── Does not support composite intents (RESEARCH+SURVEY)                       │
│  └── Can only return a single IntentType                                     │
│                                                                 │
│  CategoryRouter                                                 │
│  ├── No survey-related capability templates                                │
│  └── Intent->category is 1:1 mapping                                         │
│                                                                 │
│  ResearchOrchestrator                                           │
│  ├── Linear workflow: clarify->analyze->execute->aggregate->output                       │
│  ├── Does not support multi-stage workflows                                      │
│  └── Does not support conditional branches (e.g., survey verification)                          │
│                                                                 │
│  Survey System                                                   │
│  ├── Complete independent implementation                                            │
│  └── Not integrated with master orchestrator                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 2: Architecture Design Proposal

### 2.1 Core Concept: Research Type Composition

```python
class ResearchType(Enum):
    """Research type (composable)"""
    INDUSTRY_RESEARCH = "industry_research"      # Industry research
    BRAND_RESEARCH = "brand_research"            # Brand research
    COMPANY_RESEARCH = "company_research"        # Company research
    SURVEY = "survey"                            # Survey
    COMPETITIVE_ANALYSIS = "competitive_analysis" # Competitive analysis
    MARKET_SIZING = "market_sizing"              # Market sizing
    POLICY_ANALYSIS = "policy_analysis"          # Policy analysis
    CONSUMER_RESEARCH = "consumer_research"      # Consumer research


@dataclass
class ResearchComposition:
    """Research composition"""
    types: List[ResearchType]           # Research type list
    primary: ResearchType               # Primary research type
    secondary: List[ResearchType]       # Secondary research types
    sequence: str = "sequential"        # sequential/parallel/conditional
    
    def is_composite(self) -> bool:
        """Whether it is a composite research"""
        return len(self.types) > 1
    
    def requires_survey(self) -> bool:
        """Whether it includes survey"""
        return ResearchType.SURVEY in self.types
```

### 2.2 Workflow Definition

```python
@dataclass
class WorkflowStage:
    """Workflow stage"""
    stage_id: str
    stage_name: str
    research_types: List[ResearchType]
    agents: List[str]
    dependencies: List[str]             # Dependent prerequisite stages
    condition: Optional[str] = None     # Conditional execution
    parallel: bool = False              # Whether to execute in parallel


@dataclass
class ResearchWorkflow:
    """Research workflow"""
    workflow_id: str
    name: str
    description: str
    stages: List[WorkflowStage]
    
    # Predefined workflow templates
    WORKFLOW_TEMPLATES = {
        "industry_research": ResearchWorkflow(
            workflow_id="wf_industry",
            name="Industry Research",
            stages=[
                WorkflowStage("data_collection", "Data Collection", [ResearchType.INDUSTRY_RESEARCH], ["data-collection"], []),
                WorkflowStage("analysis", "Deep Analysis", [ResearchType.INDUSTRY_RESEARCH], ["market-analysis"], ["data_collection"]),
                WorkflowStage("report", "Report Generation", [ResearchType.INDUSTRY_RESEARCH], ["report-generation"], ["analysis"]),
            ]
        ),
        
        "industry_with_survey": ResearchWorkflow(
            workflow_id="wf_industry_survey",
            name="Industry Research + Survey Verification",
            stages=[
                WorkflowStage("data_collection", "Data Collection", [ResearchType.INDUSTRY_RESEARCH], ["data-collection"], []),
                WorkflowStage("analysis", "Deep Analysis", [ResearchType.INDUSTRY_RESEARCH], ["market-analysis"], ["data_collection"]),
                WorkflowStage("survey_design", "Survey Design", [ResearchType.SURVEY], ["survey-design"], ["analysis"]),
                WorkflowStage("survey_execution", "Survey Distribution and Collection", [ResearchType.SURVEY], ["survey-execution"], ["survey_design"]),
                WorkflowStage("survey_analysis", "Survey Analysis", [ResearchType.SURVEY], ["survey-analysis"], ["survey_execution"]),
                WorkflowStage("report", "Report Generation", [ResearchType.INDUSTRY_RESEARCH, ResearchType.SURVEY], ["report-generation"], ["analysis", "survey_analysis"]),
            ]
        ),
        
        "brand_with_survey": ResearchWorkflow(
            workflow_id="wf_brand_survey",
            name="Brand Research + Survey",
            stages=[
                WorkflowStage("brand_research", "Brand Research", [ResearchType.BRAND_RESEARCH], ["brand-analysis"], []),
                WorkflowStage("survey_design", "Survey Design", [ResearchType.SURVEY], ["survey-design"], ["brand_research"]),
                WorkflowStage("survey_execution", "Survey Distribution and Collection", [ResearchType.SURVEY], ["survey-execution"], ["survey_design"]),
                WorkflowStage("survey_analysis", "Survey Analysis", [ResearchType.SURVEY], ["survey-analysis"], ["survey_execution"]),
                WorkflowStage("report", "Report Generation", [ResearchType.BRAND_RESEARCH, ResearchType.SURVEY], ["report-generation"], ["brand_research", "survey_analysis"]),
            ]
        ),
        
        "pure_survey": ResearchWorkflow(
            workflow_id="wf_survey",
            name="Pure Survey",
            stages=[
                WorkflowStage("survey_design", "Survey Design", [ResearchType.SURVEY], ["survey-design"], []),
                WorkflowStage("survey_execution", "Survey Distribution and Collection", [ResearchType.SURVEY], ["survey-execution"], ["survey_design"]),
                WorkflowStage("survey_analysis", "Survey Analysis", [ResearchType.SURVEY], ["survey-analysis"], ["survey_execution"]),
                WorkflowStage("report", "Report Generation", [ResearchType.SURVEY], ["report-generation"], ["survey_analysis"]),
            ]
        ),
    }
```

### 2.3 Intent Recognition Extension

```python
class CompositeIntentGate:
    """Composite intent gate"""
    
    # Research type keywords
    RESEARCH_TYPE_KEYWORDS: Dict[ResearchType, List[str]] = {
        ResearchType.INDUSTRY_RESEARCH: [
            "industry research", "industry analysis", "market research"
        ],
        ResearchType.BRAND_RESEARCH: [
            "brand research", "brand analysis", "brand study"
        ],
        ResearchType.COMPANY_RESEARCH: [
            "company research", "enterprise analysis", "company study"
        ],
        ResearchType.SURVEY: [
            "survey", "questionnaire", "poll"
        ],
        ResearchType.COMPETITIVE_ANALYSIS: [
            "competitive analysis", "competitor analysis", "competition analysis"
        ],
        ResearchType.CONSUMER_RESEARCH: [
            "consumer research", "user research", "consumer study"
        ],
    }
    
    # Composition pattern recognition
    COMPOSITION_PATTERNS: Dict[str, List[Tuple[ResearchType, ...]]] = {
        "industry+survey": (ResearchType.INDUSTRY_RESEARCH, ResearchType.SURVEY),
        "brand+survey": (ResearchType.BRAND_RESEARCH, ResearchType.SURVEY),
        "company+survey": (ResearchType.COMPANY_RESEARCH, ResearchType.SURVEY),
        "competitive+survey": (ResearchType.COMPETITIVE_ANALYSIS, ResearchType.SURVEY),
    }
    
    def analyze_composition(
        self,
        user_request: str
    ) -> ResearchComposition:
        """
        Analyze research composition
        
        Args:
            user_request: User request text
            
        Returns:
            ResearchComposition
        """
        detected_types = []
        
        # Detect all matching research types
        for rtype, keywords in self.RESEARCH_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in user_request.lower():
                    detected_types.append(rtype)
                    break
        
        # Deduplicate
        detected_types = list(set(detected_types))
        
        # Determine primary research type
        if ResearchType.SURVEY in detected_types and len(detected_types) > 1:
            # If survey is included, survey is typically secondary verification
            primary = [t for t in detected_types if t != ResearchType.SURVEY][0]
            secondary = [ResearchType.SURVEY]
        elif detected_types:
            primary = detected_types[0]
            secondary = detected_types[1:] if len(detected_types) > 1 else []
        else:
            primary = ResearchType.INDUSTRY_RESEARCH
            secondary = []
        
        return ResearchComposition(
            types=detected_types if detected_types else [ResearchType.INDUSTRY_RESEARCH],
            primary=primary,
            secondary=secondary,
            sequence="sequential"
        )
```

### 2.4 Workflow Orchestrator

```python
class WorkflowOrchestrator:
    """Workflow orchestrator"""
    
    def __init__(
        self,
        research_orchestrator: ResearchOrchestrator,
        survey_client: SurveyClient,
        agent_factory: DynamicAgentFactory,
    ):
        self._research_orchestrator = research_orchestrator
        self._survey_client = survey_client
        self._agent_factory = agent_factory
        self._intent_gate = CompositeIntentGate()
    
    async def execute(
        self,
        user_request: str,
        requirement: Optional[Dict[str, Any]] = None,
        interaction_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute research workflow
        
        Args:
            user_request: User request
            requirement: Structured requirement
            interaction_callback: Interaction callback
            
        Returns:
            Execution result
        """
        # 1. Analyze research composition
        composition = self._intent_gate.analyze_composition(user_request)
        
        # 2. Select workflow template
        workflow = self._select_workflow(composition)
        
        # 3. Execute workflow stages
        stage_results = {}
        for stage in workflow.stages:
            # Check dependencies
            if not self._check_dependencies(stage, stage_results):
                continue
            
            # Execute stage
            stage_result = await self._execute_stage(
                stage=stage,
                requirement=requirement or {},
                previous_results=stage_results,
                interaction_callback=interaction_callback,
            )
            stage_results[stage.stage_id] = stage_result
        
        # 4. Aggregate results
        final_result = self._aggregate_results(stage_results, composition)
        
        return final_result
    
    def _select_workflow(self, composition: ResearchComposition) -> ResearchWorkflow:
        """Select workflow template"""
        if composition.types == [ResearchType.SURVEY]:
            return ResearchWorkflow.WORKFLOW_TEMPLATES["pure_survey"]
        elif ResearchType.SURVEY in composition.types and ResearchType.INDUSTRY_RESEARCH in composition.types:
            return ResearchWorkflow.WORKFLOW_TEMPLATES["industry_with_survey"]
        elif ResearchType.SURVEY in composition.types and ResearchType.BRAND_RESEARCH in composition.types:
            return ResearchWorkflow.WORKFLOW_TEMPLATES["brand_with_survey"]
        else:
            return ResearchWorkflow.WORKFLOW_TEMPLATES["industry_research"]
    
    async def _execute_stage(
        self,
        stage: WorkflowStage,
        requirement: Dict[str, Any],
        previous_results: Dict[str, Any],
        interaction_callback: Optional[Callable],
    ) -> Dict[str, Any]:
        """Execute workflow stage"""
        
        if ResearchType.SURVEY in stage.research_types:
            # Survey-related stage
            return await self._execute_survey_stage(stage, requirement, previous_results)
        else:
            # Research-related stage
            return await self._execute_research_stage(stage, requirement, previous_results)
    
    async def _execute_survey_stage(
        self,
        stage: WorkflowStage,
        requirement: Dict[str, Any],
        previous_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute survey stage"""
        
        if stage.stage_id == "survey_design":
            # Design survey based on research results
            research_result = previous_results.get("analysis", {})
            questions = self._generate_survey_questions(research_result)
            
            survey = await self._survey_client.create_survey(
                title=f"{requirement.get('topic', 'Research')} Survey",
                questions=questions
            )
            return {"survey": survey}
        
        elif stage.stage_id == "survey_execution":
            # Distribute survey
            survey = previous_results["survey_design"]["survey"]
            task = await self._survey_client.distribute(
                survey=survey,
                target_count=requirement.get("survey_count", 100)
            )
            responses = await self._survey_client.get_results(task)
            return {"responses": responses, "task": task}
        
        elif stage.stage_id == "survey_analysis":
            # Analyze survey results
            responses = previous_results["survey_execution"]["responses"]
            analysis = await SurveyAnalysisAgent().execute({
                "responses": responses,
                "questions": previous_results["survey_design"]["survey"].questions
            })
            return {"analysis": analysis}
        
        return {}
```

---

## Part 3: Complete Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Flexible Requirement Orchestration Architecture                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User Requirement Input                                                              │
│  "Help me do a new energy vehicle industry research and use a survey to verify user purchase intent"                    │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CompositeIntentGate                               │   │
│  │  ├── Detect research types: INDUSTRY_RESEARCH + SURVEY                        │   │
│  │  ├── Determine primary type: INDUSTRY_RESEARCH                                   │   │
│  │  ├── Determine secondary type: SURVEY                                            │   │
│  │  └── Output: ResearchComposition                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    WorkflowSelector                                  │   │
│  │  └── Select workflow: industry_with_survey                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    WorkflowOrchestrator                              │   │
│  │                                                                     │   │
│  │  Stage 1: data_collection                                           │   │
│  │  ├── Type: INDUSTRY_RESEARCH                                        │   │
│  │  ├── Agent: data-collection                                         │   │
│  │  └── Output: Industry data                                                 │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  Stage 2: analysis                                                  │   │
│  │  ├── Type: INDUSTRY_RESEARCH                                        │   │
│  │  ├── Agent: market-analysis                                         │   │
│  │  └── Output: Industry analysis results                                             │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  Stage 3: survey_design                                             │   │
│  │  ├── Type: SURVEY                                                   │   │
│  │  ├── Agent: survey-design (generate survey based on analysis results)                    │   │
│  │  └── Output: Survey design                                                 │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  Stage 4: survey_execution                                          │   │
│  │  ├── Type: SURVEY                                                   │   │
│  │  ├── Agent: survey-execution (AI simulation or platform distribution)                     │   │
│  │  └── Output: Survey collected data                                             │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  Stage 5: survey_analysis                                           │   │
│  │  ├── Type: SURVEY                                                   │   │
│  │  ├── Agent: survey-analysis                                         │   │
│  │  └── Output: Survey analysis results                                             │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  Stage 6: report                                                    │   │
│  │  ├── Type: INDUSTRY_RESEARCH + SURVEY                               │   │
│  │  ├── Agent: report-generation                                       │   │
│  │  └── Output: Final report (integrating industry analysis + survey verification)                        │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  Final Output: Industry research report (including survey verification section)                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 4: Integration with Existing System

### 4.1 Integration Points

| Existing Component | Integration Method | Description |
|--------------------|-------------------|-------------|
| **ResearchOrchestrator** | As child component of WorkflowOrchestrator | Handles INDUSTRY_RESEARCH type stages |
| **SurveyClient** | As child component of WorkflowOrchestrator | Handles SURVEY type stages |
| **IntentGate** | Extended to CompositeIntentGate | Supports composite intent recognition |
| **CategoryRouter** | Add survey-related templates | Supports survey capability routing |
| **DynamicAgentFactory** | Register survey-related Agents | Supports dynamic creation of survey Agents |

### 4.2 New Components

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| **ResearchType** | `src/core/research_type.py` | Research type enum |
| **ResearchComposition** | `src/core/research_type.py` | Research composition definition |
| **WorkflowStage** | `src/core/workflow.py` | Workflow stage definition |
| **ResearchWorkflow** | `src/core/workflow.py` | Workflow definition |
| **CompositeIntentGate** | `src/core/composite_intent_gate.py` | Composite intent recognition |
| **WorkflowOrchestrator** | `src/core/workflow_orchestrator.py` | Workflow orchestrator |

---

## Part 5: Implementation Plan

### 5.1 Phase 11: Composite Intent Support (Week 43-44)

| Task | Deliverable | Dependencies |
|------|-------------|--------------|
| ResearchType enum | `src/core/research_type.py` | None |
| ResearchComposition class | Same as above | None |
| CompositeIntentGate | `src/core/composite_intent_gate.py` | None |
| Unit tests | `tests/unit/core/test_composite_intent.py` | All above |

### 5.2 Phase 12: Workflow Engine (Week 45-47)

| Task | Deliverable | Dependencies |
|------|-------------|--------------|
| WorkflowStage/ResearchWorkflow | `src/core/workflow.py` | Phase 11 |
| WorkflowOrchestrator | `src/core/workflow_orchestrator.py` | Phase 11 |
| Predefined workflow templates | Same as above | None |
| Integration with ResearchOrchestrator | Modify `orchestrator.py` | All above |
| Integration with SurveyClient | Modify `survey/client.py` | All above |
| Integration tests | `tests/integration/test_workflow.py` | All above |

### 5.3 Phase 13: User Interaction Enhancement (Week 48-49)

| Task | Deliverable | Dependencies |
|------|-------------|--------------|
| Workflow selection interaction | Modify `smart_clarifier.py` | Phase 12 |
| Stage progress display | New API endpoint | Phase 12 |
| Intermediate result preview | New preview feature | Phase 12 |

---

## Part 6: Acceptance Criteria

| Number | Acceptance Item | Acceptance Criteria |
|--------|-----------------|---------------------|
| A01 | Composite intent recognition | Can correctly identify combinations like "industry+survey", "brand+survey" |
| A02 | Workflow selection | Automatically select correct workflow template based on research composition |
| A03 | Stage execution | Each stage executes correctly according to dependency order |
| A04 | Result aggregation | Final report correctly integrates results from each stage |
| A05 | Backward compatibility | Existing pure industry research flow is not affected |

---

**Reviewer Signature**: ________________

**Review Date**: ________________

**Review Comments**: ________________
