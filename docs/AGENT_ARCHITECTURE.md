# Zensers Agent Architecture Design Document

> **Document Version**: v1.1  
> **Created**: 2026-04-06  
> **Updated**: 2026-04-07  
> **Related Documents**: DEVELOPMENT_PLAN_V3.2.md, ROADMAP.md  
> **Core Principle**: Fixed Agent Team + Dynamic Agent Factory + Master Orchestration

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interaction Layer                      │
│                    (CLI / API / Web Interface)                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       Master Agent V2                              │
│                    (OrchestratorV2)                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Responsibilities: Receive requirements -> Dispatch Agent -> Coordinate Flow -> Integrate Output           │  │
│  │ Principle: Only assign work, do not execute                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Fixed Agent Team (Core Team)                     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Requirement Analysis Agent │  │  Data Collection Agent │  │  Report Generation Agent │          │
│  │              │  │              │  │              │          │
│  │ - Intent     │  │ - Web Search │  │ - Section Generation   │          │
│  │   Recognition │  │ - News Search│  │ - Content Integration   │          │
│  │ - Entity     │  │ - Web Scrape │  │ - Markdown   │          │
│  │   Extraction │  │              │  │              │          │
│  │ - Framework  │  └──────────────┘  └──────────────┘          │
│  │   Recommendation │                                          │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                              │
│  │  Layout Design Agent │  │  Quality Check Agent │                              │
│  │              │  │              │                              │
│  │ - Word      │  │ - Completeness Check  │                              │
│  │   Generation │  │ - Consistency Check  │                              │
│  │ - Style     │  │ - Quality Score    │                              │
│  │   Application│  │              │                              │
│  │ - Chart     │  └──────────────┘                              │
│  │   Insertion │                                               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (Complex tasks)
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Factory                               │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Domain Expert   │  │   Analysis Agent  │  │   Research Agent │  │
│  │                 │  │                 │  │                 │  │
│  │ - Energy Storage│  │ - Competitive   │  │ - Technical     │  │
│  │   Expert        │  │   Analysis      │  │   Research      │  │
│  │ - Medical Expert │  │ - Financial     │  │ - Market        │  │
│  │ - Automotive    │  │   Analysis      │  │   Research      │  │
│  │   Expert        │  │ - Policy        │  │ - User Research │  │
│  │                 │  │   Analysis      │  │                 │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  Features: Dynamic creation, task-specific, destroy or recycle after use                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

### 1. Master Does Not Execute

**Principle**: The master Agent is only responsible for scheduling and coordination, not directly executing analysis, generation, or other tasks.

**Benefits**:
- Reduces master complexity, avoids logic bloat
- Clear responsibility when issues arise, easy to debug
- Facilitates testing, master only tests scheduling logic

**Example**:
```python
# ❌ Wrong: Master directly completes tasks
class Orchestrator:
    async def process(self, input):
        # Master directly analyzes requirements
        analysis = self._analyze_requirement(input)
        # Master directly generates report
        report = self._generate_report(analysis)
        return report

# ✅ Correct: Master only schedules, tasks delegated to sub-Agents
class OrchestratorV2:
    async def process(self, input):
        # 1. Dispatch requirement analysis Agent
        analysis = await self.requirement_analyzer.execute(input)
        # 2. Dispatch report generation Agent
        report = await self.report_generator.execute(analysis)
        return report
```

### 2. Fixed + Dynamic

**Principle**: Core capabilities use fixed Agents, special requirements use dynamic creation.

| Type | Purpose | Lifecycle | Optimization |
|------|---------|-----------|-------------|
| **Fixed Agent** | General core capabilities | Long-term | Continuous iterative optimization |
| **Dynamic Agent** | Specialized needs | Destroy after use | Configuration-based generation |

**Example**:
```python
# Fixed Agent - long-term, continuously optimized
self.requirement_analyzer = RequirementAnalysisAgent()
self.data_collector = DataCollectionAgent()

# Dynamic Agent - created on demand, destroyed after use
if analysis.complexity == "high":
    expert = self.agent_factory.create_domain_expert(
        domain="Energy Storage",
        expertise=["Lithium Battery", "Sodium Battery"]
    )
    result = await expert.execute(task)
    # Task complete, destroy or recycle
```

### 3. Single Responsibility

**Principle**: Each Agent does only one thing and does it well.

| Agent | Responsibility | What It Does Not Do |
|-------|---------------|---------------------|
| **RequirementAnalysisAgent** | Analyze requirements | Does not collect data, does not generate reports |
| **DataCollectionAgent** | Collect data | Does not analyze data, does not make judgments |
| **ReportGenerationAgent** | Generate content | Does not layout, does not check quality |
| **LayoutDesignAgent** | Layout design | Does not generate content |
| **QualityCheckAgent** | Quality check | Does not modify content |

### 4. Interface Contract

**Principle**: Layers communicate through clear interface contracts.

```python
# Agent Input/Output Contract
@dataclass
class AgentInput:
    """Agent Input Base Class"""
    task_id: str
    timestamp: datetime
    data: Dict[str, Any]

@dataclass
class AgentOutput:
    """Agent Output Base Class"""
    success: bool
    result: Optional[Any]
    error: Optional[str]
    execution_time: float
```

---

## Fixed Agent Team Details

### 1. Requirement Analysis Agent (RequirementAnalysisAgent)

**Responsibility**: Deeply parse user requirements, generate research framework.

**Input**:
```python
@dataclass
class RequirementInput:
    text: str                    # User raw input
    context: Optional[Dict]      # Context information
```

**Output**:
```python
@dataclass
class AnalysisOutput:
    intent: ResearchIntent       # Research intent
    entities: List[Entity]       # Extracted entities
    framework: ResearchFramework  # Recommended research framework
    complexity: str              # Complexity assessment
```

**Core Method**:
```python
class RequirementAnalysisAgent(FixedAgentBase):
    async def execute(self, input: RequirementInput) -> AnalysisOutput:
        # 1. Intent recognition
        intent = await self._identify_intent(input.text)
        # 2. Entity extraction
        entities = await self._extract_entities(input.text)
        # 3. Framework recommendation
        framework = await self._recommend_framework(intent, entities)
        # 4. Complexity assessment
        complexity = self._assess_complexity(entities)
        return AnalysisOutput(intent, entities, framework, complexity)
```

---

### 2. Data Collection Agent (DataCollectionAgent)

**Responsibility**: Collect data from multiple sources.

**Input**:
```python
@dataclass
class DataQueryInput:
    query: str                   # Query term
    sources: List[str]           # Data source list
    limit: int = 10              # Quantity limit
```

**Output**:
```python
@dataclass
class DataCollectionOutput:
    data: List[DataItem]         # Data list
    sources: List[Source]        # Source list
    total_count: int             # Total count
```

**Core Method**:
```python
class DataCollectionAgent(FixedAgentBase):
    async def execute(self, input: DataQueryInput) -> DataCollectionOutput:
        # 1. Search web data
        web_results = await self._search_web(input.query, input.limit)
        # 2. Search news
        news_results = await self._search_news(input.query, input.limit)
        # 3. Data cleaning
        cleaned = self._clean_data(web_results + news_results)
        return DataCollectionOutput(cleaned)
```

---

### 3. Report Generation Agent (ReportGenerationAgent)

**Responsibility**: Generate structured research report content.

**Input**:
```python
@dataclass
class ReportGenerationInput:
    chapters: List[ChapterConfig]  # Chapter configuration
    data: List[DataItem]           # Data
    style: str = "formal"          # Style
```

**Output**:
```python
@dataclass
class ReportOutput:
    sections: List[Section]        # Section list
    total_words: int               # Total word count
    markdown: str                  # Markdown format
```

**Core Method**:
```python
class ReportGenerationAgent(FixedAgentBase):
    async def execute(self, input: ReportGenerationInput) -> ReportOutput:
        sections = []
        for chapter in input.chapters:
            # Generate chapter
            section = await self._generate_section(chapter, input.data)
            sections.append(section)
        # Integrate report
        markdown = self._combine_sections(sections)
        return ReportOutput(sections, sum(s.word_count for s in sections), markdown)
```

---

### 4. Layout Design Agent (LayoutDesignAgent)

**Responsibility**: Format output documents.

**Input**:
```python
@dataclass
class LayoutInput:
    markdown: str                  # Markdown content
    template: str                  # Template name
    output_format: str = "docx"    # Output format
```

**Output**:
```python
@dataclass
class LayoutOutput:
    file_path: str                 # File path
    format: str                    # Format
    page_count: int                # Page count
```

**Core Method**:
```python
class LayoutDesignAgent(FixedAgentBase):
    async def execute(self, input: LayoutInput) -> LayoutOutput:
        # 1. Parse Markdown
        parsed = self._parse_markdown(input.markdown)
        # 2. Apply template
        doc = self._apply_template(parsed, input.template)
        # 3. Generate file
        file_path = self._generate_file(doc, input.output_format)
        return LayoutOutput(file_path, input.output_format, doc.page_count)
```

---

### 5. Quality Check Agent (QualityCheckAgent)

**Responsibility**: Check report quality.

**Input**:
```python
@dataclass
class QualityCheckInput:
    report: ReportOutput           # Report
    requirements: List[str]        # Requirements list
```

**Output**:
```python
@dataclass
class QualityCheckOutput:
    score: float                   # Quality score (0-100)
    issues: List[QualityIssue]     # Issue list
    passed: bool                   # Whether passed
```

**Core Method**:
```python
class QualityCheckAgent(FixedAgentBase):
    async def execute(self, input: QualityCheckInput) -> QualityCheckOutput:
        # 1. Completeness check
        completeness = self._check_completeness(input.report)
        # 2. Consistency check
        consistency = self._check_consistency(input.report)
        # 3. Format check
        format_ok = self._check_format(input.report)
        # 4. Calculate score
        score = self._calculate_score(completeness, consistency, format_ok)
        return QualityCheckOutput(score, issues, score >= 60)
```

---

## Agent Factory Details

### Dynamic Agent Types

| Type | Purpose | Creation Parameters |
|------|---------|--------------------|
| **DomainExpertAgent** | Domain-specific analysis | domain, expertise |
| **AnalystAgent** | Specialized analysis | analysis_type, focus_areas |
| **ResearcherAgent** | Deep research | research_scope, methodology |
| **WriterAgent** | Professional writing | writing_style, target_audience |
| **ValidatorAgent** | Validation and checking | validation_rules |

### Factory Interface

```python
class AgentFactory:
    """Agent Factory - dynamically creates specialized Agents"""
    
    def create_domain_expert(
        self,
        domain: str,
        expertise: List[str],
        llm_model: str = "gpt-4"
    ) -> DomainExpertAgent:
        """Create a domain expert Agent"""
        config = AgentConfig(
            role="domain_expert",
            domain=domain,
            expertise=expertise,
            llm_model=llm_model
        )
        return DomainExpertAgent(config)
    
    def create_analyst(
        self,
        analysis_type: str,
        focus_areas: List[str],
        llm_model: str = "gpt-4"
    ) -> AnalystAgent:
        """Create an analysis Agent"""
        config = AgentConfig(
            role="analyst",
            analysis_type=analysis_type,
            focus_areas=focus_areas,
            llm_model=llm_model
        )
        return AnalystAgent(config)
    
    def find_suitable_agent(self, task_description: str) -> Optional[DynamicAgent]:
        """Intelligently match the appropriate Agent based on task description"""
        # Analyze task description
        # Match the most suitable Agent type
        # Return configured Agent
        pass
```

### Lifecycle Management

```python
class AgentLifecycleManager:
    """Agent Lifecycle Manager"""
    
    def __init__(self):
        self._active_agents: Dict[str, DynamicAgent] = {}
        self._agent_pool: List[DynamicAgent] = []
    
    def register(self, agent: DynamicAgent) -> str:
        """Register an Agent"""
        agent_id = str(uuid.uuid4())
        self._active_agents[agent_id] = agent
        return agent_id
    
    def destroy(self, agent_id: str) -> None:
        """Destroy an Agent"""
        if agent_id in self._active_agents:
            agent = self._active_agents.pop(agent_id)
            agent.cleanup()
    
    def recycle(self, agent: DynamicAgent) -> None:
        """Recycle an Agent back to the pool"""
        agent.reset()
        self._agent_pool.append(agent)
```

---

## Master Agent V2 Details

### 6-Stage Processing Flow

```python
class OrchestratorV2:
    """Master Agent V2 - Pure scheduling and coordination"""
    
    def __init__(self):
        # Fixed Agent team
        self.requirement_analyzer = RequirementAnalysisAgent()
        self.data_collector = DataCollectionAgent()
        self.report_generator = ReportGenerationAgent()
        self.layout_designer = LayoutDesignAgent()
        self.quality_checker = QualityCheckAgent()
        
        # Agent Factory
        self.agent_factory = AgentFactory()
        self.lifecycle_manager = AgentLifecycleManager()
    
    async def process_request(self, user_input: str) -> Dict:
        """
        6-Stage processing flow
        
        Args:
            user_input: User input text
            
        Returns:
            Dict containing: report, quality, execution_log
        """
        execution_log = []
        
        # Stage 1: Requirement Analysis (Fixed Agent)
        analysis = await self._stage_requirement_analysis(user_input)
        execution_log.append({"stage": 1, "agent": "RequirementAnalysisAgent", "status": "success"})
        
        # Stage 2: Data Collection (Fixed Agent)
        data = await self._stage_data_collection(analysis)
        execution_log.append({"stage": 2, "agent": "DataCollectionAgent", "status": "success"})
        
        # Stage 3: Dynamic Agent Creation (if needed)
        if analysis.complexity == "high":
            expert_result = await self._stage_dynamic_analysis(analysis, data)
            execution_log.append({"stage": 3, "agent": "DynamicExpert", "status": "success"})
        
        # Stage 4: Report Generation (Fixed Agent)
        report = await self._stage_report_generation(analysis, data)
        execution_log.append({"stage": 4, "agent": "ReportGenerationAgent", "status": "success"})
        
        # Stage 5: Layout Design (Fixed Agent)
        formatted = await self._stage_layout_design(report)
        execution_log.append({"stage": 5, "agent": "LayoutDesignAgent", "status": "success"})
        
        # Stage 6: Quality Check (Fixed Agent)
        quality = await self._stage_quality_check(formatted)
        execution_log.append({"stage": 6, "agent": "QualityCheckAgent", "status": "success"})
        
        return {
            "report": formatted,
            "quality": quality,
            "execution_log": execution_log
        }
```

### Error Handling and Recovery

```python
async def _stage_with_retry(
    self,
    stage_name: str,
    agent: FixedAgentBase,
    input_data: Any,
    max_retries: int = 3
) -> Any:
    """Stage execution with retry"""
    for attempt in range(max_retries):
        try:
            result = await agent.execute(input_data)
            if result.success:
                return result
            else:
                logger.warning(f"{stage_name} failed: {result.error}")
        except Exception as e:
            logger.error(f"{stage_name} error: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    raise StageExecutionError(f"{stage_name} failed after {max_retries} retries")
```

---

## Communication Mechanism

### Inter-Agent Communication

```python
# Message Bus - Asynchronous Communication
class MessageBus:
    async def publish(self, event: Event) -> None:
        """Publish event"""
        pass
    
    async def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to event"""
        pass

# Shared Memory - Synchronous Data Sharing
class SharedMemory:
    async def read(self, key: str) -> Any:
        """Read data"""
        pass
    
    async def write(self, key: str, value: Any) -> None:
        """Write data"""
        pass
```

### Communication Patterns

| Mode | Purpose | Example |
|------|---------|---------|
| **Message Bus** | Asynchronous notification | Agent notifies master after completing task |
| **Shared Memory** | Synchronous data sharing | Agents share analysis results |
| **Direct Call** | Synchronous execution | Master directly calls sub-Agent |

---

## Testing Strategy

### Unit Testing

```python
# Fixed Agent Unit Test
class TestRequirementAnalysisAgent:
    async def test_parse_simple_requirement(self):
        agent = RequirementAnalysisAgent()
        input_data = RequirementInput(text="Analyze energy storage industry")
        result = await agent.execute(input_data)
        assert result.intent.type == "industry_research"
        assert "Energy Storage" in [e.name for e in result.entities]
```

### Integration Testing

```python
# Agent Collaboration Integration Test
class TestAgentCollaboration:
    async def test_requirement_to_report_flow(self):
        orchestrator = OrchestratorV2()
        result = await orchestrator.process_request("Analyze energy storage industry")
        assert result["report"] is not None
        assert result["quality"].score > 0
```

### E2E Testing

```python
# End-to-End Test
class TestEndToEnd:
    async def test_full_research_workflow(self):
        # Submit research requirement
        result = await cli_runner.invoke(cli, ['research', 'Analyze energy storage industry'])
        assert result.exit_code == 0
        
        # Verify output
        report = load_report(result.output)
        assert len(report.sections) >= 5
        assert report.quality_score >= 0.6
```

---

## Key Design Supplement: Agent Collaboration Flow (v1.2 New)

> **Important Note**: The original design document lacked detailed design for Agent collaboration flow and Session hierarchy management.
> This section was added on 2026-04-10 to fix critical architecture design gaps.
> See: [AGENT_SESSION_MANAGEMENT.md](./AGENT_SESSION_MANAGEMENT.md)

### 1. Core Problem

**Original Design Gap**: Agents created without Session binding, master cannot track sub-Agent status.

| Defect | Description | Impact |
|--------|-------------|--------|
| No Session Binding | Agents created without independent Session | Unable to track Agent lifecycle |
| No Hierarchy | Unable to track parent-child Session relationships | Master doesn't know which sub-Agents were created |
| No Status Tracking | Master cannot know sub-Agent execution progress | Unable to implement progress monitoring |
| No Async Collection | Unable to implement event-driven result aggregation | Can only synchronously block and wait |

### 2. Solution: Session Hierarchy Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ParentSession (Master Session)                                │
│  ├── session_id: "research_abc123"                          │
│  ├── AgentSessionRegistry (Sub-Session Registry)                 │
│  │   └── child_sessions[agent_1, agent_2, agent_3]          │
│  ├── ResultCollector (Result Collector)                           │
│  └── MessageBus (Event Communication)                                  │
│                                                             │
│          ┌──────────┼──────────┐                            │
│          ▼          ▼          ▼                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │ChildSession│ │ChildSession│ │ChildSession│               │
│  │ parent_id: │ │ parent_id: │ │ parent_id: │               │
│  │ Master ID  │ │ Master ID  │ │ Master ID  │               │
│  │ status:    │ │ status:    │ │ status:    │               │
│  │ running    │ │ completed  │ │ pending    │               │
│  └────────────┘ └────────────┘ └────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 3. Core Components

| Component | Responsibility | File |
|-----------|---------------|------|
| **AgentSession** | Agent execution context, includes status, progress, results | `src/core/agents/agent_session.py` |
| **AgentSessionRegistry** | Sub-Session registry, tracks all sub-Agent statuses | `src/core/agents/agent_session.py` |
| **ResultCollector** | Event-driven result collection, supports async waiting | `src/core/agents/result_collector.py` |
| **SessionOrigin** | Session origin type (primary/spawned/background) | `src/core/agents/agent_session.py` |

### 4. Runtime Flow

```
1. User initiates request -> Orchestrator creates master Session
2. Agent creation phase -> Factory.create_agent_with_session()
3. Task distribution phase -> Publish agent.started event
4. Execution monitoring phase -> Agent publishes agent.progress event
5. Result aggregation phase -> Publish agent.completed event
6. Final integration phase -> ResultCollector.wait_for_all()
```

### 5. Key Design Decisions

| Design | Decision | Reason |
|--------|----------|--------|
| Independent Session per Agent | Easy to track and recover | Supports async parallel execution |
| Event-Driven Communication | MessageBus publish/subscribe | Decouples master from sub-Agents |
| Async Result Collection | ResultCollector | Supports concurrency and timeout control |
| Session Origin Tracking | SessionOrigin enum | Distinguishes primary/spawned/background |

**Detailed Design**: See [AGENT_SESSION_MANAGEMENT.md](./AGENT_SESSION_MANAGEMENT.md)

---

## File Structure

```
src/agents/
├── __init__.py
├── base.py                           # Agent base class
├── orchestrator_v2.py                # Master Agent V2
├── fixed_agents/                     # Fixed Agent team
│   ├── __init__.py
│   ├── base_fixed_agent.py           # Fixed Agent base class
│   ├── requirement_analysis_agent.py # Requirement Analysis Agent
│   ├── data_collection_agent.py      # Data Collection Agent
│   ├── report_generation_agent.py    # Report Generation Agent
│   ├── layout_design_agent.py        # Layout Design Agent
│   └── quality_check_agent.py        # Quality Check Agent
└── factory/                          # Agent Factory
    ├── __init__.py
    ├── dynamic_agent.py              # Dynamic Agent base class
    ├── agent_factory.py              # Agent Factory
    └── lifecycle_manager.py          # Lifecycle Management

tests/unit/agents/
├── test_fixed_agents.py              # Fixed Agent tests
├── test_agent_factory.py             # Agent Factory tests
└── test_orchestrator_v2.py           # Master Agent tests

tests/integration/
├── test_agent_collaboration.py       # Agent collaboration tests
└── test_full_pipeline.py             # Full pipeline tests

tests/e2e/
└── test_research_workflow.py         # E2E tests
```

---

## Best Practices

### 1. Agent Design

- **Single Responsibility**: Each Agent does only one thing
- **Clear Interface**: Input/output types clearly defined
- **Error Handling**: All exceptions caught internally, return standard error format
- **Logging**: Log key operations for debugging

### 2. Master Orchestration

- **No Direct Processing**: Only schedule, do not execute specific tasks
- **Status Monitoring**: Monitor each Agent's execution status
- **Error Recovery**: Retry or degrade on failure
- **Timeout Control**: Set timeout for each stage

### 3. Dynamic Agent

- **Configuration-based**: Generated through configuration, avoid hardcoding
- **Lightweight**: Only include necessary logic
- **Recyclable**: Support recycling and reuse

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-04-06 | Initial version, defined fixed Agent + dynamic factory architecture |

---

*Agent Architecture Design Document v1.0 - Continuously updated based on project progress*
