# Zensers Implementation Roadmap

> **Document Version**: v1.6  
> **Created**: 2026-04-05  
> **Updated**: 2026-04-17  
> **Update Frequency**: Biweekly  
> **Related Documents**: API.md, CHANGELOG.md

---

## Project Overview

| Phase | Status | Completion | Description |
|------|------|--------|------|
| **Phase 1** | ✅ Completed | 100% | MVP Core Features |
| **Phase 2** | ✅ Completed | 100% | Data Provider Integration |
| **Phase 3** | ✅ Completed | 100% | Survey System |
| **Phase 3.5** | ✅ Completed | 100% | Document Generation System Enhancement |
| **Phase 4** | 🔄 In Progress | 50% | Production Readiness |
| **Phase 5** | ⬜ Pending | 0% | Advanced Features |
| **Phase 6** | ⬜ Pending | 0% | Ecosystem Development |

---

## Roadmap Overview

```
Phase 1-3 (10 weeks) ✅    Phase 3.5 (1 week) ✅    Phase 4 (4 weeks) 🔄
      │                    │                    │
      ▼                    ▼                    ▼
┌─────────┐         ┌─────────┐         ┌─────────┐
│ Core     │   ✓     │ Document│   ✓     │Production│
│ Features │ ──────> │McKinsey │ ──────> │ Ready   │
│ MVP Done │         │ Report  │         │Stability│
└─────────┘         └─────────┘         └─────────┘
    Status: ✅         Status: ✅          Status: 🔄
```

---

## Phase 3.5: Document Generation System Enhancement ✅ Completed (2026-04-17)

### Objective
Achieve international publication-level professional report generation capability

### Deliverables

#### 1. McKinsey-Style Report Generator ✅
| Component | Status | Description |
|------|------|------|
| Color Scheme | ✅ | Deep Navy Blue primary + Amber Gold accent (three-color principle) |
| Chart Generator | ✅ | 10 professional chart types |
| Layout Design | ✅ | Generous white space, clear hierarchy |
| Word Formatting | ✅ | Markdown bold correctly converted |

#### 2. Chart Type Support ✅
| Type | Description | Status |
|------|------|------|
| BAR | Bar Chart | ✅ |
| HBAR | Horizontal Bar Chart | ✅ |
| BAR_LINE | Bar + Line Combination | ✅ |
| PIE | Pie Chart | ✅ |
| LINE | Line Chart | ✅ |
| RADAR | Radar Chart | ✅ |
| SCATTER | Scatter Plot | ✅ |
| BUBBLE | Bubble Chart | ✅ |
| WATERFALL | Waterfall Chart | ✅ |
| QUADRANT | Quadrant Chart | ✅ |

#### 3. DocumentGenerationAgent Enhancement ✅
| Feature | Status | Description |
|------|------|------|
| produce_document | ✅ | Complete document generation flow |
| load_research_result | ✅ | Historical record loading |
| populate_document_content | ✅ | Content population |
| fallback_generate | ✅ | Fallback generation method |

#### 4. Project Cleanup ✅
| Cleanup Item | Count | Status |
|--------|------|------|
| Cache Directories | 295+ | ✅ Cleaned |
| Deprecated Documents | 39 | ✅ Cleaned |
| Temporary Files | 20+ | ✅ Cleaned |
| Test Data | 300+ | ✅ Cleaned |

#### 5. Documentation Update ✅
| Document | Status | Description |
|------|------|------|
| docs/API.md | ✅ | New API documentation |
| docs/CHANGELOG.md | ✅ | Updated changelog |
| README.md | ✅ | Updated project structure |

### Phase 3.5 Success Criteria
- [x] Generate McKinsey-style professional reports
- [x] Support multiple chart types
- [x] Correct Word format (no Markdown residue)
- [x] Clean project structure with no redundancy
- [x] Complete API documentation

---

## Phase 4: Production Readiness (4 weeks) 🔄 In Progress

> **Detailed Plan**: PHASE4_DEVELOPMENT_PLAN.md

### Objective
Elevate the system from "feature complete" to "production ready"

### Current Progress

| Week | Task | Focus | Status |
|------|------|------|------|
| Week 1 | Crash Recovery | WAL Enhancement, Task Persistence, Error Handling | ✅ Completed |
| Week 2 | Observability | Structured Logging, Metrics Collection, Health Check | 🔄 In Progress |
| Week 3 | Performance Optimization | Cache Optimization, Parallel Optimization, Performance Benchmarking | ⬜ Pending |
| Week 4 | Documentation Examples | API Documentation, User Guide, Example Projects | ✅ Completed |

### Acceptance Criteria
- [x] Crash recovery rate 100%
- [ ] Single report time < 15min
- [ ] Concurrent tasks >= 10
- [x] API documentation coverage 100%

---

## Phase 1: MVP Core Features (6 weeks) ✅ Completed (2026-04-06)

### Skill System (Week 1-2) ✅ Completed

| Skill | Type | Status | Description |
|-------|------|--------|-------------|
| HTTPSkill | Built-in | ✅ | HTTP request wrapper |
| SearchSkill | Built-in | ✅ | Web search (DuckDuckGo, no API key needed) |
| NewsSearchSkill | Built-in | ✅ | News search (DuckDuckGo) |
| WebScraperSkill | Built-in | ✅ | Web content extraction |
| LLMSkill | Built-in | ✅ | LLM call wrapper |
| DocxSkill | Built-in | ✅ | Word document generation |

**Implementation details**:
- Search Skill uses DuckDuckGo instead of Tavily, no API key required
- All Skills uniformly inherit `Skill` base class
- `SkillRegistry` supports auto-registration of core Skills
- Retains LangChain Tools compatibility layer

### Data Layer Foundation (Week 4-5) ✅ Completed
| Component | Status | Description |
|-----------|--------|-------------|
| DataBus Framework | ✅ | Routing + Degradation + Caching framework (V3 Enhanced) |
| DataBus V3 | ✅ | Market routing, smart degradation, cost gating, audit logging |
| Public Data Sources | ✅ | akshare, National Bureau of Statistics |
| Bloomberg Mock | ✅ | Bloomberg Mock adapter |
| Wind Mock | ✅ | Wind Mock adapter |
| Cache System | ✅ | Multi-level cache (memory + disk) |
| Circuit Breaker | ✅ | CircuitBreaker three-state transition |
| Rate Limiter | ✅ | TokenBucketRateLimiter |
| Retry Handler | ✅ | EnhancedRetryHandler |

### Integration Tests (Week 5-6) ✅ Completed
| Test Item | Status | Acceptance Criteria |
|-----------|--------|-------------------|
| End-to-End Flow | ✅ | Complete pipeline from requirements to report |
| **Constraint Engineering Tests** | ✅ | Untrusted sources rejected/degraded |
| **Quality Gate Tests** | ✅ | Unverified content correctly flagged |
| Concurrency Tests | ✅ | 3 research tasks in parallel |
| Crash Recovery | ✅ | WAL supports crash recovery |
| Cost Baseline | ✅ | Cost gating available |
| Phase 2 Integration Tests | ✅ | All 36 tests passing |

### Phase 1 Success Criteria
- [x] Complete a new energy vehicle industry research report
- [x] Full process automation from input to output
- [x] **All data sources undergo whitelist verification**
- [x] **Key numbers have traceability records**
- [x] **Output content includes confidence levels**
- [x] Cost < $5/report
- [x] Time < 30 minutes

### Phase 1 Progress (2026-04-06)
- ✅ **Skill System**: 6 core Skills completed
- ✅ **Agent Base Class**: BaseAgent implemented
- ✅ **Agent Factory**: DynamicAgentFactory completed (dynamic generation, unlimited domains)
- ✅ **Master Scheduling**: ResearchOrchestrator completed (end-to-end automation)
- ✅ **Fixed Agent Team**: 5 fixed Agents completed (Requirements Analysis, Data Collection, Report Generation, Layout Design, Quality Check)
- ✅ **Master Agent V2**: OrchestratorV2 completed (pure scheduling coordination)
- ✅ **Data Layer**: DataBus V3 completed (market routing, smart degradation, cost gating, audit logging)
- ✅ **Constraint Engineering**: SourceWhitelist + FactTracer + QualityGate completed
- ✅ **Error Handling**: Circuit breaker, rate limiter, retry handler completed
- ✅ **Data Adapters**: Bloomberg Mock + Wind Mock completed

**Phase 1 Status**: ✅ **Completed**

**Phase 2 Status**: ✅ **Completed**

---

### Phase 1 Agent Architecture Refactoring (2026-04-06)

**Architecture Upgrade**: From single complex Agent to "Fixed Agent Team + Dynamic Agent Factory + Master Scheduling"

#### Fixed Agent Team (Core Team)

| Agent | Responsibilities | Status | Description |
|-------|-----------------|--------|-------------|
| **RequirementAnalysisAgent** | Deep analysis of user requirements | ✅ | Intent recognition, entity extraction, framework recommendation |
| **DataCollectionAgent** | Collect multi-source data | ✅ | Web search, news search, web scraping |
| **ReportGenerationAgent** | Generate report content | ✅ | Section generation, content integration |
| **LayoutDesignAgent** | Layout formatting | ✅ | Markdown to Word, style application |
| **QualityCheckAgent** | Quality check | ✅ | Completeness check, consistency check, scoring |

#### Dynamic Agent Factory

| Feature | Status | Description |
|---------|--------|-------------|
| **create_domain_expert** | ✅ | Create domain expert Agent |
| **create_analyst** | ✅ | Create analyst Agent |
| **create_researcher** | ✅ | Create researcher Agent |
| **find_suitable_agent** | ✅ | Smart Agent matching |
| **Lifecycle Management** | ✅ | Create, destroy, recycle |

#### Master Agent V2 (OrchestratorV2)

**Core Change**: From "directly completing tasks" to "pure scheduling coordination"

```
User Request
    ↓
[Master Agent V2] - Only schedules, doesn't work
    ↓
[Requirements Agent] → [Data Collection Agent] → [Dynamic Agent*] → [Report Generation Agent] → [Layout Design Agent] → [Quality Check Agent]
    ↓
Complete Research Report
```

**6-Stage Processing Flow**:
1. Requirements Analysis (Fixed Agent)
2. Data Collection (Fixed Agent)
3. Dynamic Agent Creation (if needed)
4. Report Generation (Fixed Agent)
5. Layout Design (Fixed Agent)
6. Quality Check (Fixed Agent)

**Architecture Advantages**:
- ✅ Clear responsibilities: each Agent does one thing
- ✅ Quality controllable: fixed Agents can be repeatedly optimized
- ✅ Clear accountability: know who to go to for issues
- ✅ Easy to test: each Agent independently testable
- ✅ Flexible expansion: dynamic Agents handle special requirements

---

## Phase 2: Data Provider Integration (2-3 weeks) ✅ Completed (2026-04-06)

### Objective
Integrate Bloomberg and Wind paid data sources to improve data quality and coverage.

### Deliverables

#### 2.1 Error Handling Framework ✅
| Component | Status | Description |
|-----------|--------|-------------|
| CircuitBreaker | ✅ | Circuit breaker (three-state transition, auto-recovery) |
| TokenBucketRateLimiter | ✅ | Token bucket rate limiter |
| EnhancedRetryHandler | ✅ | Enhanced retry handler (exponential backoff + jitter) |
| RateLimiterManager | ✅ | Rate limiter manager (multi-provider) |
| execute_with_resilience | ✅ | Resilient execution function |

#### 2.2 BloombergAdapter ✅
| Feature | Status | Priority | Description |
|---------|--------|----------|-------------|
| Mock Adapter | ✅ | 🔴 High | Develop and test without real Terminal |
| Field Mapping System | ✅ | 🔴 High | Internal field name → Bloomberg field code |
| Ticker Conversion | ✅ | 🔴 High | Internal format → Bloomberg format |
| Historical Data Query | ✅ | 🔴 High | Supports date range queries |
| Cost Estimation | ✅ | 🟡 Medium | Cost estimation per query |
| BLPAPI Connection | ⬜ | 🔴 High | Requires real Bloomberg account |

#### 2.3 WindAdapter ✅
| Feature | Status | Priority | Description |
|---------|--------|----------|-------------|
| Mock Adapter | ✅ | 🔴 High | Develop and test without real Wind terminal |
| Field Mapping System | ✅ | 🔴 High | Internal field name → Wind indicator code |
| A-Share Specific Fields | ✅ | 🔴 High | Northbound funds, margin trading, institutional holdings |
| Macro Data | ✅ | 🔴 High | GDP, CPI, PMI, etc. |
| Industry Data | ✅ | 🟡 Medium | Shenwan industry classification |
| WindPy Connection | ⬜ | 🔴 High | Requires real Wind account |

#### 2.4 DataBus V3 Enhancement ✅
| Feature | Status | Description |
|---------|--------|-------------|
| Market Routing | ✅ | US→Bloomberg, CN→Wind, auto-routing |
| Smart Degradation | ✅ | Primary→Backup→Public data |
| Circuit Breaker Protection | ✅ | Integrated CircuitBreaker |
| Rate Limiting Control | ✅ | Integrated TokenBucketRateLimiter |
| Cost Gating | ✅ | Budget control, over-limit alerts, hard limits |
| Call Audit | ✅ | All paid call records, 90-day retention |

### Phase 2 Success Criteria ✅
- [x] Bloomberg/Wind Mock adapters available
- [x] US stock data query working (Mock)
- [x] A-share data query working (Mock)
- [x] Failure degradation test passed
- [x] Cost monitoring available
- [x] Circuit breaker protection test passed
- [x] Rate limiter test passed
- [x] Audit log test passed

### Phase 2 New Files
```
src/core/data_providers/
├── error_handling.py          # Circuit breaker, rate limiter, retry handler
├── databus_v3.py              # DataBus V3 Enhanced
└── adapters/
    ├── bloomberg_adapter.py   # Bloomberg Mock adapter
    └── wind_adapter.py        # Wind Mock adapter

tests/
├── test_phase2_1.py           # Error handling tests
├── test_phase2_3.py           # DataBus V3 tests
├── test_phase2_5.py           # Bloomberg Mock tests
├── test_phase2_6.py           # Wind Mock tests
└── test_phase2_integration.py # Integration tests

docs/
└── PHASE2_CODE_REVIEW.md      # Code review report
```

---

## Phase 3: Advanced Features (3-4 weeks)

### Objective
Implement user surveys and AI-simulated respondent functionality.

### Deliverables

#### 3.1 Survey Agents (Week 1-2)
| Agent | Status | Priority | Features |
|-------|--------|----------|----------|
| Survey Optimization Agent | ⬜ | 🔴 High | AI checks survey quality |
| Survey Distribution Agent | ⬜ | 🔴 High | Multi-channel distribution + quota control |
| Survey Analysis Agent | ⬜ | 🟡 Medium | Statistical analysis + text mining |
| Survey Integration Agent | ⬜ | 🟡 Medium | Integrate into research report |

#### 3.2 Simulated Respondent Agents (Week 2-3)
| Agent | Status | Priority | Features |
|-------|--------|----------|----------|
| Persona Generation Agent | ⬜ | 🔴 High | Generate virtual respondent personas |
| Simulated Response Agent | ⬜ | 🔴 High | AI plays respondent to answer questions |
| Response Validation Agent | ⬜ | 🟡 Medium | Check response reasonableness |
| Result Calibration Agent | ⬜ | 🟡 Medium | Calibrate with real data |

#### 3.3 Supporting Skills (Week 3-4)
| Skill | Status | Description |
|-------|--------|-------------|
| SurveySkill | ⬜ | Survey operations wrapper |
| PersonaSkill | ⬜ | Persona generation |
| SimulationSkill | ⬜ | Simulated response engine |

### Phase 3 Success Criteria
- [ ] Design and distribute a survey
- [ ] Analyze survey results
- [ ] Generate 100 virtual respondents
- [ ] Simulated response quality passes verification

---

## Phase 4: Continuous Optimization (Ongoing)

### Objective
Continuously optimize performance, cost, and quality.

### Optimization Directions

#### 4.1 Performance Optimization
| Target | Current | Target | Method |
|--------|---------|--------|--------|
| Single report time | 30min | 15min | Parallel optimization, caching |
| Cache hit rate | - | >80% | Smart TTL, prefetching |
| Concurrent tasks | 3 | 10 | Resource scheduling optimization |

#### 4.2 Cost Optimization
| Target | Current | Target | Method |
|--------|---------|--------|--------|
| Single report cost | $5 | $2 | Tiered model, caching |
| LLM cost share | 60% | 40% | Small model preprocessing |
| Data cost share | 30% | 20% | Caching, degradation |

#### 4.3 Quality Optimization
| Target | Current | Target | Method |
|--------|---------|--------|--------|
| Report pass rate | - | >90% | Three lines of defense |
| Data accuracy | - | >95% | Multi-source verification |
| User satisfaction | - | >4.5/5 | Feedback iteration |

---

## Reserved Interface Detailed Design

### 1. BloombergAdapter

```python
# File: src/data_providers/bloomberg_adapter.py

class BloombergAdapter(DataProvider):
    """Bloomberg Data Adapter - Reserved Interface"""
    
    def __init__(self, config: BloombergConfig):
        self.config = config
        self.connection = None  # BLPAPI Connection
        
    async def connect(self) -> bool:
        """Establish BLPAPI Connection - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
        
    async def fetch_market_data(
        self, 
        tickers: List[str], 
        fields: List[str],
        start_date: date,
        end_date: date
    ) -> DataResponse:
        """Get market data - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
        
    async def fetch_financial_data(
        self,
        tickers: List[str],
        fields: List[str],
        period: str = "annual"
    ) -> DataResponse:
        """Get financial data - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
```

**Estimated Phase**: Phase 2  
**Priority**: 🔴 High  
**Dependency**: Bloomberg account, BLPAPI SDK  
**Estimated Effort**: 1 week

---

### 2. WindAdapter

```python
# File: src/data_providers/wind_adapter.py

class WindAdapter(DataProvider):
    """Wind Data Adapter - Reserved Interface"""
    
    def __init__(self, config: WindConfig):
        self.config = config
        self.w = None  # WindPy Object
        
    async def connect(self) -> bool:
        """Establish WindPy Connection - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
        
    async def wsd(
        self,
        tickers: List[str],
        fields: List[str],
        start_date: date,
        end_date: date
    ) -> DataResponse:
        """WSD Function - Historical Sequence Data - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
        
    async def edb(
        self,
        indicators: List[str],
        start_date: date,
        end_date: date
    ) -> DataResponse:
        """EDB Function - Macro Data - Phase 2 Implementation"""
        raise NotImplementedError("Phase 2 Implementation")
```

**Estimated Phase**: Phase 2  
**Priority**: 🔴 High  
**Dependency**: Wind account, WindPy SDK  
**Estimated Effort**: 1 week

---

### 3. Survey Agent Group

```python
# File: src/agents/survey_agents.py

class SurveyOptimizationAgent(Agent):
    """Survey Optimization Agent - Reserved Interface"""
    
    async def optimize_survey(
        self, 
        survey: Survey
    ) -> OptimizedSurvey:
        """Optimize survey design - Phase 3 Implementation"""
        raise NotImplementedError("Phase 3 Implementation")

class SurveyDistributionAgent(Agent):
    """Survey Distribution Agent - Reserved Interface"""
    
    async def distribute(
        self,
        survey: Survey,
        channels: List[Channel],
        quota: QuotaConfig
    ) -> DistributionResult:
        """Multi-channel survey distribution - Phase 3 Implementation"""
        raise NotImplementedError("Phase 3 Implementation")
```

**Estimated Phase**: Phase 3  
**Priority**: 🟡 Medium  
**Dependency**: Phase 1 Complete  
**Estimated Effort**: 2 weeks

---

### 4. Simulated Respondent Agent Group

```python
# File: src/agents/simulation_agents.py

class PersonaGenerationAgent(Agent):
    """Persona Generation Agent - Reserved Interface"""
    
    async def generate_personas(
        self,
        target_population: PopulationSpec,
        count: int
    ) -> List[Persona]:
        """Generate virtual respondent personas - Phase 3 Implementation"""
        raise NotImplementedError("Phase 3 Implementation")

class SimulatedResponseAgent(Agent):
    """Simulated Response Agent - Reserved Interface"""
    
    async def simulate_response(
        self,
        persona: Persona,
        question: Question
    ) -> Response:
        """AI plays respondent answering questions - Phase 3 Implementation"""
        raise NotImplementedError("Phase 3 Implementation")
```

**Estimated Phase**: Phase 3  
**Priority**: 🟡 Medium  
**Dependency**: Phase 1 Complete, Persona Database  
**Estimated Effort**: 2 weeks

---

## Milestone Checkpoints

### Checkpoint 1: Phase 1 Midpoint (Week 3) ✅ Completed
- [x] Core class implementation complete
- [x] 3 Agents available
- [x] Basic Skills available

### Checkpoint 2: Phase 1 End (Week 6) ✅ Completed
- [x] MVP features complete
- [x] End-to-end tests passing
- [x] Cost baseline met

### Checkpoint 3: Phase 2 End (Week 9) ✅ Completed (2026-04-06)
- [x] Bloomberg/Wind Mock integration
- [x] Data quality improved (circuit breaker, rate limiter protection)
- [x] Failure degradation available
- [x] Cost gating available
- [x] Audit logging available

### Checkpoint 4: Phase 3 End (Week 13) ⬜ Pending
- [ ] User survey functionality available
- [ ] Simulated respondents available
- [ ] Advanced features integrated

---

## Risk and Response

| Risk | Likelihood | Impact | Response |
|------|-----------|--------|----------|
| Bloomberg account delay | Medium | High | Develop with public data first |
| Wind data points over budget | Medium | Medium | Cost gating + caching |
| LLM API instability | Low | High | Multi-provider fallback |
| Development schedule delay | Medium | Medium | Weekly checkpoints + scope trimming |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.6 | 2026-04-17 | **Phase 3.5 Complete**: McKinsey-style report generator, chart generation service, project cleanup, API documentation |
| v1.5 | 2026-04-07 | Phase 3 Complete: Survey system |
| v1.4 | 2026-04-06 | **Phase 2 Complete**: Error handling framework, DataBus V3, Bloomberg/Wind Mock adapters all complete, all 36 tests passing |
| v1.3 | 2026-04-06 | Agent architecture refactor: Fixed Agent team (5) + Dynamic Agent Factory + Master Agent V2 (pure scheduling) |
| v1.2 | 2026-04-06 | Agent Factory refactor: From fixed 9 types to dynamic generation, supports any domain |
| v1.1 | 2026-04-06 | Update Phase 1 progress: Skill system complete, Agent base class complete, Agent Factory pending |
| v1.0 | 2026-04-05 | Initial version, defining Phase 1-4 roadmap |

---

*Roadmap v1.6 - Updated 2026-04-17*
