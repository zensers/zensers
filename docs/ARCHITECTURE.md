# Zensers Project Architecture Design Document

> Version: v1.2 | Date: 2026-05-03
> Status: MCP Protocol Layer Integration Complete

---

## Part 1: Project Overview

### 1.1 Project Positioning

**Zensers** is an open-source automated market research system that completes the full-process research task from requirement analysis to report generation through multi-Agent collaboration.

**Core Goal**: Upgrade the system from a "report generation tool" to a "research collaboration assistant"

```
User -> System -> Report + Knowledge Accumulation + Learning Evolution
         ↓
Next time: User stronger -> System smarter -> Better experience... (Upward spiral)
```

### 1.2 Project Scale

| Metric | Value |
|--------|-------|
| Source files | 110+ |
| Source lines of code | ~38,500 |
| Test files | 74+ |
| Test cases | 2,050+ |
| LSP diagnostics | 0 errors |

### 1.3 Completion Status

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 0 | Complete | 100% - Constraint Layer |
| Phase 1 | Complete | 100% - Session Management |
| Phase 2 | Complete | 100% - CoreMemory/Token Budget/Dream Mode |
| Phase 3 | Complete | 100% - Memory Extraction/Knowledge Management/Learning Mechanism |
| Phase 4 | Complete | 100% - Production Ready |
| Phase 5 | Complete | 100% - MCP Protocol Layer (5 Phases all delivered) |
| Phase 6 | Complete | 100% - Unified Document Generation Agent |
| Phase 8 | Complete | 100% - Preview Revision Workflow |
| **Integration Fixes** | Complete | 100% - Survey Data Flow/Chart Generation/Quality Check |

---

## Part 2: System Architecture

### 2.1 Seven-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 7: Application Layer                         │
│   CLI / Web API                                              │
├─────────────────────────────────────────────────────────────┤
│ Layer 6: Orchestration Layer                       │
│   ResearchOrchestrator / AgentFactory                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: Agent Layer                              │
│   FixedAgents / DynamicAgents / Session Management                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Capability Layer                          │
│   Skills / MCP Tools / Converters                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Layer                              │
│   CoreMemory / SessionMemory / KnowledgeBank                │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Communication Layer                       │
│   MessageBus / SharedMemory / EventBus                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Storage Layer                             │
│   TaskStorage / WAL / ResearchResultStore                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 0: Constraint Layer                          │
│   SourceWhitelist / FactTracer / CrossValidator            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Directory Structure

```
src/
├── agents/                    # Agent implementations
│   └── fixed_agents/          # Fixed Agent team
│       ├── document_generation_agent.py
│       ├── requirement_analysis_agent.py
│       └── ...
│
├── api/                       # Web API layer
│   └── document_api.py        # FastAPI routes
│
├── core/                      # Core framework
│   ├── adjustment/            # Document adjustment
│   ├── agents/                # Agent core system
│   │   ├── factory.py         # Dynamic Agent factory
│   │   ├── agent_session.py   # Session management
│   │   └── result_collector.py
│   ├── harness/               # Constraint layer
│   ├── mcp/                   # MCP support
│   ├── memory/                # Memory system
│   │   ├── budget/            # Token budget
│   │   ├── compressor/        # History compression
│   │   ├── core/              # Core memory
│   │   ├── dream/             # Dream Mode
│   │   ├── extraction/        # Knowledge extraction
│   │   ├── knowledge/         # Knowledge management
│   │   ├── learning/          # Learning mechanism
│   │   ├── retrieval/         # Retrieval system
│   │   └── session/           # Session management
│   ├── orchestrator/          # Master orchestration
│   ├── preview/               # Preview system
│   └── storage/               # Storage layer
│
├── converters/                # Format conversion
│   ├── html_to_word.py
│   ├── html_to_ppt.py
│   └── html_to_pdf.py
│
├── content/                   # Content orchestration
│   ├── content_orchestrator.py
│   └── template_engine.py
│
├── config/                    # Configuration management
├── llm/                       # LLM interface layer
├── skills/                    # Skill system
├── mcp/                       # MCP protocol layer (Phase 5)
│   ├── config.py              # Configuration (YAML/JSON, multi-server)
│   ├── client.py              # MCPClient (local + remote modes)
│   ├── server.py              # MCPServer (tool registration/request handling)
│   ├── tool_registry.py       # Tool registry
│   ├── credentials.py         # CredentialManager (three-level credentials)
│   ├── rate_limiter.py        # RateLimiter (token bucket throttling)
│   ├── handler.py             # MCPProtocolHandler (protocol routing)
│   ├── logging.py             # Structured logging
│   ├── health.py              # Health check
│   └── security.py            # Secure storage/credential rotation
├── agents/                    # Agent system
│   └── mcp_handler.py -> moved to core/mcp/handler.py
└── utils/                     # Utility functions
```

---

## Part 3: Core Module Analysis

### 3.1 Agent System

#### Architecture Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent System Architecture                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  BaseAgent (Abstract Base Class)                                       │
│  ├── agent_id: str                                          │
│  ├── capabilities: List[str]                                │
│  └── execute(context: Dict) -> Result                       │
│                                                             │
│  FixedAgent (Fixed Agent Base Class)                                 │
│  └── Inherits BaseAgent, adds fixed capabilities                           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Fixed Agents (12)                                  │   │
│  │ ├── RequirementAnalysisAgent                        │   │
│  │ ├── DataCollectionAgent                             │   │
│  │ ├── MarketAnalystAgent                              │   │
│  │ ├── FinancialAnalystAgent                           │   │
│  │ ├── ReportWriterAgent                               │   │
│  │ ├── DocumentGenerationAgent                         │   │
│  │ └── ...                                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  DynamicAgentFactory                                        │
│  ├── create_agent(capability: AgentCapability) -> BaseAgent │
│  └── Dynamically generates specialized Agents based on requirements                              │
│                                                             │
│  AgentSession (Session Management)                                 │
│  ├── session_id: str                                        │
│  ├── parent_session_id: Optional[str]                       │
│  ├── status: AgentSessionStatus                             │
│  └── progress: float                                        │
│                                                             │
│  AgentSessionRegistry                                       │
│  └── Manages all sub-Agent Sessions                                │
│                                                             │
│  ResultCollector                                            │
│  └── Asynchronously collects Agent execution results                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Key Components

| Component | Responsibility | File |
|-----------|---------------|------|
| BaseAgent | Agent abstract base class | `src/core/agents/base.py` |
| FixedAgent | Fixed Agent base class | `src/agents/fixed_agents/base_fixed_agent.py` |
| DynamicAgentFactory | Dynamic Agent factory | `src/core/agents/factory.py` |
| AgentSession | Session lifecycle management | `src/core/agents/agent_session.py` |
| AgentSessionRegistry | Session registry | `src/core/agents/agent_session.py` |
| ResultCollector | Async result collection | `src/core/agents/result_collector.py` |

### 3.6 MCP Protocol Layer (Phase 5 New)

MCP (Model Context Protocol) is a **protocol layer** located between Agents and external tools, standardizing the discovery, invocation, and authentication of external tools.

```
GenericAgent.execute({action, parameters})
    │
    ├── action="search" -----> SkillRegistry ---> search_skill, llm_skill, ...
    │
    └── action="mcp" --------> MCP Protocol Layer --> MCP Servers
                                    │
                                    ├── wind.get_stock_data
                                    ├── slack.send_message
                                    └── github.create_pr
```

Differences between MCP and the Skill system:
- **Skills** are system internal capabilities (search, LLM, file operations), tightly coupled
- **MCP tools** are external capabilities (Wind data, Slack messages, GitHub operations), loosely coupled through standard protocols

#### MCP Protocol Layer Components

| Component | Responsibility | File |
|-----------|---------------|------|
| MCPClient | MCP server connection and tool invocation (local/remote modes) | `src/core/mcp/client.py` |
| MCPServer | Local MCP server (tool registration, request handling) | `src/core/mcp/server.py` |
| ToolRegistry | Tool registry | `src/core/mcp/tool_registry.py` |
| CredentialManager | Three-level credential management (session > user > system) | `src/core/mcp/credentials.py` |
| RateLimiter | Token bucket throttling | `src/core/mcp/rate_limiter.py` |
| MCPProtocolHandler | Protocol routing (tool discovery -> credential injection -> invocation -> raw data return) | `src/core/mcp/handler.py` |
| MCPLogger | Structured logging | `src/core/mcp/logging.py` |
| MCPHealthChecker | Health check | `src/core/mcp/health.py` |
| SecureCredentialStorage | Secure credential storage (keyring + encrypted file) | `src/core/mcp/security.py` |
| MCPToolMatcher | Intelligent routing tool matching (keywords + LLM semantics + static fallback) | `src/core/decomposition/mcp_matcher.py` |

#### Data Flow

```
Orchestrator decomposes task -> Agent needs Wind data
  -> GenericAgent.execute({action: "mcp", tool: "wind.get_stock_data"})
  -> MCPProtocolHandler parses tool name -> Locates MCP Server
  -> CredentialManager provides API Key
  -> RateLimiter checks quota
  -> MCPClient calls remote SSE/HTTP endpoint
  -> Raw data returned -> LLM processes -> Standard {content, data_points, sources} output
  -> Engine collects -> Aggregator merges -> Report generation
```

**Key Design Decision**: MCP returns raw data without format conversion. LLM can naturally understand any JSON structure; closed-source MCP tools cannot modify their output format.

### 3.2 Memory System

#### Three-Layer Memory Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Three-Layer Memory Architecture                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: Core Memory (memory_core.json)                       │
│  ├── User preferences, core needs, high-frequency entities                           │
│  ├── Loaded at startup (< 10ms)                                    │
│  ├── Size limit: < 10KB                                       │
│  └── Promotion condition: mention_count >= 5 or recurrence_count >= 3 │
│                                                             │
│  Layer 2: Session Layer (sessions/)                                │
│  ├── sessions_index.json (session index)                        │
│  ├── sess_*.json (multiple sessions)                                │
│  ├── Step-based auto-save (each change)                             │
│  └── Restored at startup (< 50ms)                                    │
│                                                             │
│  Layer 3: Full Data (knowledge_bank.db)                      │
│  ├── All entities, relationships, data points, insights                           │
│  ├── Learning records, feature requests                                     │
│  └── On-demand query                                               │
│                                                             │
│  Dream Mode (Background Compression Service)                                  │
│  ├── Six stages: Positioning -> Signal Collection -> Integration -> Promotion -> Pruning -> Archiving              │
│  ├── Trigger: Session end/Every 24 hours/Manual/Threshold                      │
│  └── Functions: Compression, deduplication, promotion, pruning                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Knowledge Management Modules

| Module | Responsibility | File |
|--------|---------------|------|
| KnowledgeBank | Knowledge base main entry | `src/core/memory/knowledge_bank.py` |
| TemporalKnowledge | Time validity tracking | `src/core/memory/knowledge/temporal_knowledge.py` |
| ProvenanceStore | Source tracing | `src/core/memory/knowledge/provenance_store.py` |
| KnowledgeCompiler | Knowledge compiler | `src/core/memory/knowledge/compiler.py` |
| ContradictionDetector | Contradiction detection | `src/core/memory/knowledge/contradiction_detector.py` |
| KnowledgeImporter | Knowledge importer | `src/core/memory/knowledge/importer.py` |

#### Retrieval Mechanisms

| Module | Responsibility | Latency |
|--------|---------------|---------|
| VectorStore | Vector storage and retrieval | ~50ms |
| SemanticSearch | Semantic search | ~60ms |
| HybridSearch | Hybrid retrieval strategy | ~100ms |

### 3.3 Storage Layer

#### Storage Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer Architecture                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Core Storage Layer (src/core/storage.py)                           │
│  ├── TaskStorage: Task persistence                                │
│  └── WriteAheadLog (WAL): Write-ahead log                         │
│                                                             │
│  Advanced Storage Managers                                              │
│  ├── TaskPersistenceManager: Task status and checkpoints               │
│  └── EnhancedWAL: Enhanced WAL (checksums, checkpoints)               │
│                                                             │
│  Business Storage Modules (src/core/storage/)                           │
│  ├── ResearchResultStore: Research result storage                      │
│  ├── ExportManager: Document export management                            │
│  └── DocumentVersionManager: Document version control                   │
│                                                             │
│  Core Memory Layer                                                 │
│  └── CoreMemory: User core preferences and knowledge crystallization                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Data Storage Formats

| Storage Type | Format | Location |
|--------------|--------|----------|
| Research results | JSON | `data/results/{task_id}/` |
| Task status | JSON | `data/tasks/` |
| WAL logs | Line-level JSON | `data/wal/` |
| Export history | JSON | `data/exports/` |
| Version management | JSON | `data/versions/` |
| Knowledge base | SQLite | `data/knowledge_bank.db` |

#### Key Features

- **Atomic writes**: Temporary file + `os.replace()` ensures data safety
- **WAL mechanism**: Write-ahead log supports crash recovery
- **Path safety**: Regex validation + path resolution prevents path traversal
- **File size limit**: Maximum 500MB per file

### 3.4 Document Generation System

#### Document Generation Flow

```
Research Results -> ContentOrchestrator -> HTML Intermediate Format
                                      ↓
                              ┌──────┴──────┐
                              ↓       ↓       ↓
                         Word    PPT     PDF
                              ↓       ↓       ↓
                         Version Management -> Export Management -> Preview System
```

#### Key Components

| Component | Responsibility | File |
|-----------|---------------|------|
| ContentOrchestrator | Content orchestration | `src/content/content_orchestrator.py` |
| TemplateEngine | Template engine | `src/content/template_engine.py` |
| HTMLToWordConverter | Word conversion | `src/converters/html_to_word.py` |
| HTMLToPPTConverter | PPT conversion | `src/converters/html_to_ppt.py` |
| HTMLToPDFConverter | PDF conversion | `src/converters/html_to_pdf.py` |
| DocumentVersionManager | Version control | `src/core/storage/document_version_manager.py` |
| ExportManager | Export management | `src/core/storage/export_manager.py` |
| PreviewGenerator | Preview generation | `src/core/preview/preview_generator.py` |
| AdjustmentHandler | Adjustment handling | `src/core/adjustment/adjustment_handler.py` |
| DocumentAPI | Web API | `src/api/document_api.py` |

#### API Endpoints

| Endpoint | Method | Function |
|----------|--------|----------|
| `/documents/generate` | POST | Generate document |
| `/documents/{task_id}/versions` | GET | List versions |
| `/documents/{task_id}/rollback` | POST | Rollback version |
| `/documents/export` | POST | Export to specified location |
| `/documents/{task_id}/preview` | GET | Get preview |
| `/documents/adjust` | POST | Adjust document |
| `/research/completed` | GET | List completed research |
| `/research/{task_id}/generate` | POST | Delayed document generation |

---

## Part 4: Potential Architecture Issues

### 4.1 Issue List

| Priority | Issue | Impact | Status |
|----------|-------|--------|--------|
| Red P0 | Agent system dual structure | Unclear responsibilities, developer confusion | Pending |
| Red P0 | Storage layer scattered | Data consistency risk | Pending |
| Orange P1 | Communication mechanism duplication | Cognitive burden, potential data inconsistency | Pending |
| Orange P1 | Module high coupling | Circular dependency risk, hard to test | Pending |
| Yellow P2 | Configuration management scattered | Reduced maintainability | Pending |

### 4.2 Detailed Issue Analysis

#### Red P0-1: Agent System Dual Structure

**Problem Manifestation**:
```
src/agents/fixed_agents/  -> 12 fixed Agents
src/core/agents/          -> Agent core system (Factory, Session, etc.)
```

**Impact**:
- Developers unclear which base class to inherit
- `FixedAgent` and `BaseAgent` have overlapping responsibilities
- Inconsistency between documentation and code structure

**Improvement Suggestions**:
```
src/core/agents/
├── base.py           # Unified Agent base class
├── factory.py        # Dynamic Agent factory
├── fixed/            # Fixed Agent team
├── dynamic/          # Dynamically generated Agents
├── session/          # Session management
└── orchestrator/     # Master orchestration
```

#### Red P0-2: Storage Layer Scattered

**Problem Manifestation**:
```
src/core/storage.py           # TaskStorage + WAL
src/core/storage_wal.py       # EnhancedWAL
src/core/task_persistence.py  # Task persistence
src/core/storage/             # Business storage modules
src/core/memory/stores/       # Memory storage
```

**Impact**:
- Data consistency hard to guarantee
- WAL logic duplicated
- Non-unified storage interfaces

**Improvement Suggestions**:
```
src/core/storage/
├── __init__.py
├── task_storage.py     # Single-layer task storage
├── wal.py              # WAL implementation
├── result_store.py     # Research result storage
└── interfaces.py       # Storage interface contracts
```

#### Orange P1-1: Communication Mechanism Duplication

**Problem Manifestation**:
- `MessageBus`: Event notifications
- `SharedMemory`: State sharing
- `EventBus`: Not fully implemented

**Improvement Suggestions**:
```python
class AgentCommunication:
    """Unified communication interface"""
    async def subscribe(topic, handler)
    async def publish(topic, event)
    async def get_state(key)
    async def set_state(key, value)
```

#### Orange P1-2: Module High Coupling

**Problem Manifestation**:
- `ResearchOrchestrator` imports 20+ modules
- Directly depends on concrete implementations rather than interfaces
- Difficult to unit test

**Improvement Suggestions**:
```python
# Use dependency injection
class ResearchOrchestrator:
    def __init__(
        self,
        agent_factory: IAgentFactory,
        session_registry: ISessionRegistry,
        result_store: IResultStore,
        communication: AgentCommunication,
    ):
        ...
```

#### Yellow P2: Configuration Management Scattered

**Problem Manifestation**:
- `src/config/settings.py` centralized configuration
- Various modules still have embedded configurations and hardcoded paths

**Improvement Suggestions**:
```python
class Config:
    @classmethod
    def get_storage_path(cls) -> Path:
        return Path(settings.system.data_dir)
```

---

## Part 5: Improvement Plan

### 5.1 Three-Phase Refactoring

#### Phase 1 (Week 1-2): Unify Agent and Communication Layer

| Task | Estimated Effort |
|------|------------------|
| Merge `src/agents/` and `src/core/agents/` | 2 days |
| Unify `MessageBus` and `SharedMemory` | 2 days |
| Establish Agent lifecycle management model | 1 day |
| Update test cases | 2 days |

#### Phase 2 (Week 3-4): Integrate Storage and Decouple Dependencies

| Task | Estimated Effort |
|------|------------------|
| Consolidate storage logic into `src/core/storage/` | 3 days |
| Introduce dependency injection container | 2 days |
| Simplify three-level record system | 2 days |
| Update test cases | 2 days |

#### Phase 3 (Week 5-6): Configuration Centralization and Test Verification

| Task | Estimated Effort |
|------|------------------|
| Unify configuration management | 2 days |
| Establish interface contract tests | 2 days |
| Update architecture documentation | 1 day |
| Team training | 1 day |

### 5.2 Risk Assessment

| Risk | Level | Mitigation Measures |
|------|-------|---------------------|
| Circular dependencies | High | Use dependency injection, lazy imports |
| Data inconsistency | High | Unified storage interfaces, transactional guarantees |
| Insufficient test coverage | Medium | Contract testing, coverage checks |
| Team familiarity | Medium | Documentation updates, training |

---

## Part 6: Design References

### 6.1 Reference Projects

| Project | Reference Points |
|---------|------------------|
| Claude Code | 7-layer memory + Dream Mode + Constraint Layer |
| MemGPT | Layered memory architecture + memory extraction Pipeline |
| Zep/Graphiti | Temporal knowledge graph + quality governance |

### 6.2 Design Principles

1. **Constraint First**: Garbage in = garbage memory
2. **Progressive Storage**: Hot layer to cold layer progression strategy
3. **Step-based Save**: Save immediately on each state change
4. **Dependency Inversion**: Depend on interfaces rather than implementations
5. **Single Responsibility**: Each module has clear responsibilities

---

## Part 7: Appendix

### 7.1 Key File List

```
Core Framework:
├── src/core/orchestrator/research_orchestrator.py  # Master orchestration
├── src/core/agents/factory.py                       # Agent factory
├── src/core/agents/agent_session.py                 # Session management
├── src/core/communication.py                        # Communication layer
└── src/core/storage.py                              # Storage layer

Memory System:
├── src/core/memory/core/core_memory.py              # Core memory
├── src/core/memory/knowledge_bank.py                # Knowledge base
├── src/core/memory/dream/dream_mode.py              # Dream Mode
└── src/core/memory/retrieval/vector_store.py        # Vector retrieval

Constraint Layer:
├── src/core/harness/constraints.py                  # Source validation
├── src/core/harness/cross_validator.py              # Cross validation
└── src/core/harness/quality.py                      # Quality gate

MCP Protocol Layer:
├── src/core/mcp/config.py                           # Configuration file (YAML/JSON)
├── src/core/mcp/client.py                           # MCP client
├── src/core/mcp/server.py                           # MCP server
├── src/core/mcp/credentials.py                      # Credential management
├── src/core/mcp/rate_limiter.py                     # Rate limiting
├── src/core/mcp/handler.py                          # Protocol routing
├── src/core/mcp/logging.py                          # Structured logging
├── src/core/mcp/health.py                           # Health check
├── src/core/mcp/security.py                         # Secure storage
└── src/core/decomposition/mcp_matcher.py            # Tool matching

Document Generation:
├── src/agents/fixed_agents/document_generation_agent.py
├── src/content/content_orchestrator.py
├── src/converters/html_to_*.py
├── src/core/storage/document_version_manager.py
├── src/core/storage/export_manager.py
├── src/core/preview/preview_generator.py
├── src/core/adjustment/adjustment_handler.py
└── src/api/document_api.py
```

### 7.2 Test Coverage

| Module | Test Files | Test Cases |
|--------|------------|------------|
| Phase 0 Constraint Layer | 4 | 48 |
| Phase 1 Session Management | 5 | 28 |
| Phase 2 CoreMemory | 4 | 83 |
| Phase 2 TokenBudget | 3 | 110 |
| Phase 2 DreamMode | 1 | 60 |
| Phase 3 Knowledge Management | 10+ | 200+ |
| Phase 4 Production Ready | 4 | 170+ |
| Phase 5 MCP | 3 | 48 |
| Phase 6 Document Generation | 10+ | 200+ |
| **Total** | **74+** | **2,050+** |

---

## Part 8: Conclusion

The Zensers project architecture design document has a relatively high level of completeness, but there is deviation between the code implementation and the design. It is recommended to prioritize solving the two P0 issues of **Agent Dual Structure** and **Storage Layer Dispersion**, then gradually advance dependency decoupling and configuration centralization.

The entire refactoring process should be accompanied by comprehensive unit tests to ensure functionality is not broken. The full refactoring effort is expected to take **4-6 weeks**.

### MCP Integration Status

The MCP protocol layer (Phase 5) completed delivery of all 5 Phases on 2026-05-03:

| Phase | Content | Status |
|-------|---------|--------|
| Phase 1 Infrastructure | CredentialManager, RateLimiter, MCPClient remote mode | Complete |
| Phase 2 Protocol Layer | MCPProtocolHandler, GenericAgent action="mcp" routing | Complete |
| Phase 3 Intelligent Routing | MCPToolMatcher, AgentCapability.mcp_tools injection | Complete |
| Phase 4 Observability | MCPLogger, MCPHealthChecker, SecureCredentialStorage | Complete |
| Phase 5 Testing and Documentation | Contract tests (48 tests, 0 failed), deployment guide | Complete |
