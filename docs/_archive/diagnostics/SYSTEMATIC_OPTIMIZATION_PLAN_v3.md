# Zensers Research System - Systematic Fix and Deep Enhancement Plan v3.0

> Root cause analysis and phased implementation roadmap based on complete code audit
> Date: 2026-05-04

---

## Part 1: Root Cause Analysis

### 1.1 Gap Between Architecture Design and Actual Execution

**Design Intent**: `IndustryResearchStrategy.decompose()` creates **5 independent phase** Agents for each research dimension:
```
Phase 1: DATA_COLLECTION   →  Only search and collect raw data
     ↓  Dependency Pass
Phase 2: DATA_VALIDATION   →  Cross-validate data quality
     ↓  Dependency Pass
Phase 3: DEEP_ANALYSIS     →  Deep analysis using professional frameworks
     ↓  Dependency Pass
Phase 4: SYNTHESIS         →  Cross-section comprehensive integration
     ↓  Dependency Pass
Phase 5: REPORT_GENERATION →  Generate final report
```

**Actual Execution** (`GenericAgent.execute()` lines 336-374):
```
Each Agent executes the same flow:
  1. _do_deep_research()           ← Search
  2. _build_research_prompt_with_data()  ← Build prompt with search results
  3. _get_professional_role_prompt()     ← Load role profile
  4. LLM Execution(prompt + system_prompt)  ← Full analysis output
```

**Key Code Lines** (`generic_agent.py:336-374`):

```python
# Lines 336-343: Regardless of phase, Agent searches first
if topic and "search_skill" in available_skills:
    search_results = await self._do_deep_research(...)

# Lines 347-355: Then builds "analysis" prompt  
prompt = self._build_research_prompt_with_data(search_results=search_results)

# Line 372: Finally loads professional role
system_prompt = self._get_professional_role_prompt(aspect)

# Line 374: LLM receives "search+analysis" integrated task
result = await skill.execute(prompt=prompt, system_prompt=system_prompt)
```

### 1.2 Three Core Breakpoints

| Breakpoint | Location | Issue |
|--------|------|------|
| **Agent Role Indistinct** | `generic_agent.py:336-374` | DATA_COLLECTION/ANALYSIS/DEEP_ANALYSIS three Agent types execute identical code path |
| **No Phase-Aware Prompt** | `generic_agent.py:1816-1833` | All phases use same `research_with_data.md` template, lacking phase specificity |
| **Agent Profile is Just "Decoration"** | `generic_agent.py:1736-1740` | `_get_professional_role_prompt()` only used for system_prompt, Agent's execute() behavior unrelated to profile |

### 1.3 Data Flow Verification

```
IndustryResearchStrategy.decompose()
    │
    ├── DATA_COLLECTION AgentSpec
    │   └── skills=["search_skill", "llm_skill"]
    │   └── system_prompt = data_collection prompt
    │   └── category="research"
    │
    ├── DATA_VALIDATION AgentSpec
    │   └── skills=["llm_skill"]
    │   └── system_prompt = validation prompt
    │   └── category="quality-check"
    │
    └── DEEP_ANALYSIS AgentSpec
        └── skills=get_skills_for_aspect(aspect)  # Includes search_skill!
        └── system_prompt = deep_analysis prompt
        └── category="market-analysis"

DynamicAgentFactory.create_agent()
    │
    └── system_prompt → self.config["_system_prompt"]  # Stored but may not be used
    └── skills → self._available_skills

GenericAgent.execute(action="execute")
    │
    ├── Line 222: skill_name == "llm_skill" → Enter LLM branch
    ├── Line 251: Check aggregated_data_points ← Empty (first execution)
    ├── Line 327: Check if synthesis section ← No
    ├── Line 337: Check search_skill in available_skills ← YES! DEEP_ANALYSIS also has search_skill
    ├── Line 338: _do_deep_research() ← Search
    └── Line 347: _build_research_prompt_with_data() ← Analysis

Conclusion: APP_RELATION_analysis
Data Collection Agent:    Search + Analysis (should only search)
Data Validation Agent:    Search + Analysis (should only validate)
Deep Analysis Agent:      Search + Analysis (should only deep analyze, data should come from first two phases)
```

---

## Part 2: Layered Fix Plan

### P0 - Emergency Fix (Agent Role Separation)

#### 0.1 Remove Search Capability from DEEP_ANALYSIS Phase Agents

**Issue**: `get_skills_for_aspect()` returns `["llm_skill", "search_skill", ...]` for most analysis dimensions, causing DEEP_ANALYSIS phase Agents to also trigger searches.

**Fix**: `src/core/decomposition/strategies.py`

```python
# In IndustryResearchStrategy.decompose(), DEEP_ANALYSIS phase:
spec = AgentSpec(
    ...
    # Before:
    skills=get_skills_for_aspect(aspect),  # Includes search_skill!
    # After:
    skills=["llm_skill", "data_analysis"],  # Only keep analysis and data analysis capabilities
    # Data source: depends on upstream DATA_VALIDATION agent output
    ...
)
```

#### 0.2 Create Independent Task Prompts for Different Phases

**Current**: All Agents use same `research_with_data.md` (containing search data + analysis requirements).

**Fix**:

1. Create `prompts/tasks/data_collection.md` (enhanced):
```markdown
# Data Collection Task

## Research Topic
${topic}

## Research Dimension
${aspect}

## Task Requirements
You are a data collection expert. Your task is:
1. Search and collect data related to the topic
2. Return raw data points (numbers, facts, citations)
3. Label each data point's source and credibility
4. **Do NOT perform deep analysis or write report paragraphs**

## Output Format
Return structured data point list, each containing:
- Data content
- Source URL
- Credibility assessment (high/medium/low)
```

2. Create `prompts/tasks/data_validation.md` (enhanced):
```markdown
# Data Validation Task

## Research Topic
${topic}

## Research Dimension
${aspect}

## Input Data
${data}

## Task Requirements
You are a data validation expert. Your task is:
1. Check each data point's accuracy and consistency
2. Identify conflicts and contradictions between data
3. Mark data gaps requiring supplementary verification
4. **Do NOT re-search or generate new data**

## Output Format
Return validation report containing:
- Validated data points
- Conflicting data points (with conflict description)
- Overall data quality assessment
- Suggested data gaps to supplement
```

3. Create `prompts/tasks/deep_analysis_framework.md`:
```markdown
# Deep Analysis Task

## Research Topic
${topic}

## Research Dimension
${aspect}

## Validated Data
${validated_data}

## Analysis Framework
Please use one of the following analysis frameworks:
${framework}

## Task Requirements
You are a senior industry analyst. Based on validated data, your task is:
1. Select the most appropriate analysis framework
2. Organize analysis according to framework structure
3. Every conclusion must have data support
4. Identify key drivers and risks
5. Provide quantitative assessment
```

4. Modify `GenericAgent.execute()` to use different prompt templates based on Agent phase/category

#### 0.3 Add Phase Awareness in GenericAgent

**Fix**: `src/core/agents/generic_agent.py`

```python
# Add phase judgment before line 336 in execute():
async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
    action = task.get("action", "")
    
    # Get agent's phase info (from context or config)
    agent_category = self._context.get("category", "")
    # Or infer from agent_id: research_=DATA_COLLECTION, analysis_=DEEP_ANALYSIS
    
    if action == "execute":
        # ... existing code ...
        
        # Refactor search logic at lines 336-357:
        topic = task.get("topic", "")
        aspect = task.get("aspect", "")
        
        # Branch behavior based on Agent category
        if agent_category == "data_collection":
            # Search only, no analysis
            search_results = await self._do_deep_research(...)
            return {"success": True, "data_points": [...], "sources": [...]}
        
        elif agent_category == "quality-check":
            # Validate only, no search
            validation_result = await self._validate_data(task.get("data", []))
            return {"success": True, "validation": validation_result}
        
        elif agent_category in ("analysis", "market-analysis"):
            # Deep analysis: use validated data from preceding phases
            # If DATA_VALIDATION data exists, use it for analysis
            # Do not trigger new searches
            analysis = await self._deep_analyze(task)
            return {"success": True, "content": analysis}
        
        else:
            # synthesis / report_generation: use existing logic
            ...
```

---

### P1 - Prompt Depth Enhancement

#### 1.1 Agent Profile Enhancement Template

Add the following structured content to each Agent Profile (using `market_size.md` as example):

```markdown
## Quantitative Output Template
- Current market size: XX billion yuan (year), YoY growth XX%
- TAM: XX billion yuan, SAM: XX billion yuan, SOM: XX billion yuan
- CAGR (recent 3/5 years): XX%
- CR4/CR5/CR8: XX%
- Penetration rate: XX%, YoY change XX percentage points
- Growth driver decomposition: volume vs price contribution (volume growth XX%, price growth XX%)

## Analysis Framework (must select one)
1. TAM/SAM/SOM three-layer decomposition: ...
2. Growth factor decomposition: ...
3. Penetration rate S-curve: ...

## Counterfactual Reasoning
- Under what conditions might your judgment be overturned?
- What external factors could change the current trend?
- Does the data have timeliness or sample bias?

## Confidence Annotation
Every core data point and conclusion must be annotated with confidence:
- high: Multi-source cross-validated, official data, recent data
- medium: Single-source professional report, indirect inference
- low: Estimate, speculation, outdated data
```

#### 1.2 Unified Update All Agent Profiles

| File | Applied Framework | New Quantitative Indicators |
|------|---------|-------------|
| `market_size.md` | TAM/SAM/SOM | CAGR, Penetration Rate, CRn |
| `competition.md` | Porter's Five Forces | CR4/HHI, Entry Barrier Score |
| `technology.md` | Gartner Hype Cycle | TRL Level, Patent Count, R&D Ratio |
| `policy.md` | PESTEL | Policy Intensity Score, Compliance Cost |
| `industry_chain.md` | Profit Pool Analysis | Gross Margin by Segment, Bargaining Power Score |
| `financial_analysis.md` | DuPont Decomposition | ROE, Gross Margin, Cash Flow |
| `enterprise.md` | SWOT + Competitiveness Assessment | Market Share, Revenue Growth |
| `risk.md` | Risk Matrix | Probability x Impact Score |
| `trend.md` | S-Curve | Penetration Rate, Substitution Rate |

#### 1.3 Output Specification Enhancement

In `prompts/_shared/output_spec.md`, add:
```markdown
## Structured Output Requirements
Each analysis paragraph must contain:
1. ✅ Core judgment sentence (within 10 words)
2. ✅ Data support (specific numbers with year)
3. ✅ Logical deduction (because A therefore B)
4. ✅ Counter-evidence or boundary conditions
5. ❌ Prohibit vague statements: "has significant implications", "worth noting"
6. ❌ Prohibit in-text source annotations: "(Source: XX)" → list uniformly at end
```

---

### P2 - Agent Count and Section Coverage Release

#### 2.1 Default Framework Level Upgrade

**Fix**: `src/core/orchestrator/smart_clarifier.py:432`

```python
def start(self, user_input: str) -> Dict[str, Any]:
    self.current_choice = UserChoice(
        ...
        # Before: depth="standard"
        # After:
        depth="detailed",  # Default to detailed version, create more Agents
        ...
    )
```

Or default to detailed in non-interactive mode:

```python
# In orchestrator.py:
framework = framework or "detailed"  # CLI mode defaults to detailed
```

#### 2.2 Ensure Full Section List Passed to decompose

Verify chain:
```
SmartClarifier.select_framework("detailed")
  → section_details = all 13 sections from industry_report.yaml
  → requirement.selected_sections = 13 section IDs
  → requirement.aspects = 13 section names
  → decompose(aspects=13) → creates 13x3+2+1=42 Agents
```

**Need to check**: Whether `requirement.aspects` is correctly passed in the chain, confirm if `_parse_requirement()` uses `selected_sections` as `aspects`.

---

### P3 - Search Strategy Upgrade

#### 3.1 Layered Search Strategy

**Fix**: `src/skills/search_skill.py`

Implement three-layer search strategy:
```
Round 1: Broad net (5-8 search engines in parallel, Baidu+Bing+Google+360+Sogou)
Round 2: High-value link full-page crawl (extract full text from top-N URLs of R1 using web_scraper)
Round 3: Targeted supplement (precisely supplement after identifying data gaps)
```

#### 3.2 Force International Sources

Add configuration in `MultiSearchSkill`:
```python
SEARCH_STRATEGY = {
    "china_focused": {
        "preferred_engines": ["baidu", "bing_cn", "so", "sogou"],
        "international_weight": 0.3,  # At least 30% international sources
    },
    "global": {
        "preferred_engines": ["google", "bing_intl", "duckduckgo", "brave"],
        "international_weight": 0.7,
    }
}
```

#### 3.3 Source Diversity Scoring

Add diversity check in `SearchQualityFilter`:
```python
def check_diversity(self, sources: List[Dict]) -> Dict:
    domains = Counter(s["domain"] for s in sources)
    top_domain_ratio = max(domains.values()) / len(sources)
    return {
        "passed": top_domain_ratio < 0.5,  # No single source exceeds 50%
        "top_domain_ratio": top_domain_ratio,
        "recommendation": "Add more sources" if top_domain_ratio > 0.5 else ""
    }
```

---

### P4 - Quality Verification Subsystem Activation

#### 4.1 Enable Three-Phase Quality Check

`ExecutionEngine` has initialized three checkers but not used in the main flow. Modify `execute_with_scheduler()`:

```python
# After each batch execution:
if self.enable_quality_control:
    batch_phase = self._determine_batch_phase(batch_index, execution_batches)
    if batch_phase == "data_collection":
        quality_ok = await self.data_checker.check(batch_results)
    elif batch_phase == "deep_analysis":
        quality_ok = await self.analysis_checker.check(batch_results)
    elif batch_phase == "report_generation":
        quality_ok = await self.report_checker.check(batch_results)
    
    if not quality_ok:
        # Trigger supplementary search or retry
        await self.quality_executor.execute_feedback(batch_results)
```

#### 4.2 Quality Checker Threshold Configuration

Check quality configuration in `config/settings.yaml`:
```yaml
quality:
  max_retries: 3
  min_data_volume: 5  # Minimum data points
  threshold_data_collection: 0.6  # Data collection phase quality threshold
  threshold_analysis: 0.7  # Analysis phase quality threshold
  threshold_report: 0.8  # Report phase quality threshold
```

---

### P5 - Iterative Deepening Mechanism

#### 5.1 Add Gap Analysis in DEEP_ANALYSIS Phase

```python
# Extend DEEP_ANALYSIS in IndustryResearchStrategy.decompose():
# Deep analysis includes two sub-steps:
# Step 1: Analyze based on validated data
# Step 2: Identify knowledge gaps, trigger supplementary search
# Step 3: Revise analysis based on supplementary data

# Implementation: Add iterative method in GenericAgent
async def execute_with_depth(self, task, max_iterations=2):
    result = await self.execute(task)
    for i in range(max_iterations - 1):
        gaps = self._identify_knowledge_gaps(result)
        if not gaps:
            break
        supplements = await self._supplementary_search(gaps)
        result = await self._revise_analysis(result, supplements)
    return result
```

---

## Part 3: Implementation Roadmap

### Phase Breakdown

| Phase | Content | Workload | Effect |
|------|------|--------|------|
| **Sprint 1** | P0: Agent Role Separation + Phase-Independent Prompt | 2 days | From "search-analysis integration" to "phased specialization" |
| **Sprint 2** | P1: Prompt Depth Enhancement | 1.5 days | 2-3x Agent Output Quality Improvement |
| **Sprint 3** | P2: Agent Count Release | 0.5 day | Agents from 3→13+, Report Coverage 4x |
| **Sprint 4** | P3: Search Strategy Upgrade | 1.5 days | Data Diversity + International Sources |
| **Sprint 5** | P4: Quality Verification Activation | 1 day | Automatic Quality Gates |
| **Sprint 6** | P5: Iterative Deepening | 2 days | Multi-round Analysis Loop |

### Priority Recommendation

```
This Week:
  Sprint 1 (Agent Role Separation) - Core architecture fix
  Sprint 3 (Agent Count Release) - Immediately increase report coverage
  Sprint 2 (Prompt Enhancement) - Highest ROI

Next Week:
  Sprint 4 (Search Upgrade)
  Sprint 5 (Quality Verification)

This Month:
  Sprint 6 (Iterative Deepening)
```

### Key File Index

| Modification | File | Line |
|----------|------|------|
| Agent Role Separation | `src/core/agents/generic_agent.py` | 336-374, 1730-1740 |
| Phase-Aware Prompt Construction | `src/core/agents/generic_agent.py` | 1742-1833, 2087-2129 |
| Decomposition Strategy | `src/core/decomposition/strategies.py` | 209-409 |
| Agent Skill Assignment | `src/core/decomposition/strategies.py` | 37-83 |
| Prompt Manager | `src/core/prompt_manager.py` | 338-370 |
| Execution Engine | `src/core/orchestrator/execution/engine.py` | 963-1148, 1240-1315 |
| Scheduler | `src/core/orchestrator/execution/scheduler.py` | 122-241 |
| Smart Clarifier | `src/core/orchestrator/smart_clarifier.py` | 432-567 |
| Template Definition | `config/templates/industry_report.yaml` | Full file |
| Search Skill | `src/skills/search_skill.py` | Full file |
| Framework Configuration | `config/research_frameworks.yaml` | Full file |
