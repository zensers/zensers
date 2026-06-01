# Zensers Market Research System - Systematic Optimization Plan v2.0

> Systematic optimization roadmap based on deep code audit
> Date: 2026-05-04

---

## 1. Current System Status Assessment

### 1.1 Architecture Capability Assessment

| Assessment Dimension | Theoretical Capability | Actual Performance | Gap |
|----------|---------|---------|------|
| **Agent Count** | Up to ~36 (13 sections x 3 phases + synthesis) | Typically 3-5 | **10x Gap** |
| **Research Phases** | 5 phases (DC→DV→DA→SY→RG) | 3 phases (DC→AN→RG) | 2 phases not enabled |
| **Section Coverage** | 13 standard sections (industry_report template) | 3 sections | **4x Gap** |
| **Search Sources** | 17 search engines | ~80% from Baidu ecosystem | Insufficient source diversity |
| **Search Depth** | Supports multi-round search + full page extraction | Single search without deep extraction | Coarse data granularity |
| **Quality Verification** | 3-level checker + metadata extraction | Basically not enabled | Virtually nonexistent |
| **Output Formats** | 5 formats | HTML/Markdown mainly | Not fully tested |

### 1.2 Core Bottleneck Identification

Through full-chain code audit, the **root cause** of insufficient research depth is not an architecture defect, but a **configuration chain break** causing high-capability components not to be activated:

```
[User Input] → [Template Selection] → [Section Definition] → [Agent Creation] → [Phase Execution] → [Search] → [Analysis] → [Output]
     ↓            ↓            ↓            ↓             ↓          ↓       ↓       ↓
    OK         Default Brief   Only 3      Only 3       3-phase     Single   Shallow Skip
               Version        Sections    Agents        instead    Search   Analysis Quality
                                                         of 5      No Depth          Check
```

---

## 2. Layered Optimization Plan

### P0 - Immediate Execution (High ROI, Minute-level Changes)

#### 0.1 Restore 5-Phase Execution Pipeline

**Issue**: `ExecutionEngine` uses 3 stages (`ExecutionStage`), but task decomposition (`IndustryResearchStrategy`) generates 5-phase (`ResearchPhase`) plans. Stage mismatch causes `DATA_VALIDATION` and `SYNTHESIS` phases to be merged into the generalized `ANALYSIS`.

**File to Modify**: `src/core/orchestrator/execution/engine.py`

```python
# Current (line 106-110):
class ExecutionStage(Enum):
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    REPORT_GENERATION = "report_generation"

# Change to:
class ExecutionStage(Enum):
    DATA_COLLECTION = "data_collection"
    DATA_VALIDATION = "data_validation"    # New
    DEEP_ANALYSIS = "deep_analysis"        # Split from ANALYSIS
    SYNTHESIS = "synthesis"                # New
    REPORT_GENERATION = "report_generation"
```

Also update:
- Classification logic in `classify_agent()`, add `validation` → `DATA_VALIDATION`, `synthesis` → `SYNTHESIS`
- `CATEGORY_KEYWORDS` with corresponding keywords
- `classify_agents()` returns 5-tuple

**Expected Effect**: Agents execute in 5 phases, with clear quality gates and phase transitions between each phase.

---

#### 0.2 Fix Default Framework Level, Enable "Detailed Version"

**Issue**: `SmartClarifier._generate_framework_options()` generates 3 options for the industry_report template. In non-interactive mode (CLI), if the user doesn't select a framework level, the brief version is used by default, selecting only `required` sections. The industry_report.yaml has only 4 sections with `required: true` (Investment Highlights, Industry Overview, Competitive Landscape, Risk Warning), and the other 9 optional sections are all ignored.

**File to Modify**: `src/core/orchestrator/smart_clarifier.py`

**Plan A (Recommended)**: Default to `detailed` instead of `brief`
```python
# In start() method (line 432):
def start(self, user_input: str) -> Dict[str, Any]:
    self.current_choice = UserChoice(
        ...
        depth="standard",  # Change to "detailed"
        ...
    )
```

**Plan B**: In `_parse_requirement()`, default to detailed when no framework specified.
```python
# In orchestrator.py:
framework = framework or "detailed"  # Default detailed
```

**Expected Effect**: Agent count jumps from 3 to 10-15, covering all 13 standard sections.

---

#### 0.3 Unlock Agent Creation Count Limit

**Issue**: `_determine_complexity_params()` has `max_agents_per_aspect` of only 2 for `complex` complexity, and only 1 for `trivial` and `single`. With 13 sections, this is fine (1 Agent per section). But the key is that the system needs to first correctly pass the 13 sections to the `decompose()` method.

**Verify Linkage**: Check if `requirement.aspects` contains the complete 13 section IDs. Current chain:
```
SmartClarifier.select_framework("brief")  →  section_details = brief sections (3)
  →  requirement.aspects = ["summary", "market_size", "conclusion"]  (only 3)
  →  decompose() receives 3 aspects → only creates 9 Agents (3x3)
```

**Fix**: Ensure `detailed` mode has `requirement.aspects` containing all 13 sections.

---

### P1 - Short-to-Medium Term Optimization (1-3 days)

#### 1.1 Prompt Depth Enhancement (Highest ROI)

**Current Status**: 24 Agent Profiles, each only 20-30 lines, containing "Expertise Areas" and "Analysis Framework" two lightweight sections.

**Optimization Direction**: Add the following to each Agent Profile:

```
## Quantitative Output Template (New)
- Must provide specific numerical indicators (CAGR, market share, penetration rate, etc.)
- Must annotate each data's confidence level (high/medium/low)
- Must indicate data source and timeliness

## Counterfactual Reasoning (New)
- Under what conditions might your judgment be invalid?
- What factors could overturn your conclusions?

## Competitive Benchmarking (New)
- Quantitative comparison with comparable companies/markets
- What is the root cause of the difference?

## Analysis Framework Selection (Per Agent Dimension)
- Market Size: TAM/SAM/SOM three-layer decomposition
- Competitive Landscape: Porter's Five Forces + Strategic Groups + CRn
- Technology Trends: Gartner Hype Cycle + TRL Assessment
- Policy Environment: PESTEL Framework
```

**Specific Files to Modify**:
- `prompts/agents/market_size.md` → Add TAM/SAM/SOM template, CAGR calculation requirements
- `prompts/agents/competition.md` → Add CR4/HHI calculation, Porter's Five Forces quantification table
- `prompts/agents/technology.md` → Add TRL assessment table, patent analysis requirements
- `prompts/agents/policy.md` → Add PESTEL framework, compliance cost estimation
- `prompts/agents/industry_chain.md` → Add profit pool analysis, bargaining power assessment
- Other Agent profiles similarly

---

#### 1.2 Search Strategy Upgrade

**Issue**: MultiSearchSkill is configured with 17 search engines, but ~80% of results come from Baidu ecosystem in practice, lacking international sources and deep crawling.

**File to Modify**: `src/skills/search_skill.py`

**Optimization Measures**:

1. **Layered Search Strategy**:
   ```
   Round 1: Broad search (5-8 search engines in parallel)
   Round 2: High-value link full-text extraction (select top-N from Round 1 results for deep crawling)
   Round 3: Targeted search (after identifying gaps, use precise keywords to supplement)
   ```

2. **Force International Sources**: Add configuration item `force_international_sources: true`, when set to true, prioritize Google/Bing International/DuckDuckGo/Brave, ensuring non-Chinese sources account for no less than 30%

3. **Source Diversity Score**: Add source diversity detection in `SearchQualityFilter`, trigger supplementary search when a single source exceeds 50%

---

#### 1.3 Independent Deep Analysis Phase

**Issue**: Currently `DEEP_ANALYSIS` and `DATA_COLLECTION` are merged in the same Agent (Agent both searches and analyzes), lacking multi-round iteration.

**Fix Plan**:

In `IndustryResearchStrategy.decompose()` and `ExecutionEngine`:

```python
# Create independent deep analysis Agent for each aspect
# This Agent receives validated data, uses professional analysis frameworks for deep analysis
# Supports: analysis → identify gaps → trigger supplementary search → re-analyze iteration loop

# Add gap_analysis step in execute_with_scheduler():
if phase == ResearchPhase.DEEP_ANALYSIS:
    for agent in phase_agents:
        result = await agent.execute()
        gaps = await self._analyze_gaps(result)
        if gaps:
            supplementary = await self._supplementary_search(gaps)
            result = await agent.execute_with_new_data(supplementary)
```

---

#### 1.4 Quality Check Subsystem Activation

**Issue**: `ExecutionEngine` initializes `DataCollectionQualityChecker`, `AnalysisQualityChecker`, `ReportQualityChecker` three checkers and `QualityMetadataExtractor`, but the check logic is not executed in the main flow.

**Fix**:

```python
# After each phase execution in execute_with_scheduler():
if phase == ResearchPhase.DATA_COLLECTION:
    quality_ok = await self.data_checker.check(stage_result)
elif phase == ResearchPhase.DEEP_ANALYSIS:
    quality_ok = await self.analysis_checker.check(stage_result)
elif phase == ResearchPhase.REPORT_GENERATION:
    quality_ok = await self.report_checker.check(stage_result)

if not quality_ok:
    # Automatically trigger supplementary search or retry
    await self.quality_executor.execute_feedback(stage_result)
```

---

### P2 - Medium-to-Long Term Architecture Upgrade (1-2 weeks)

#### 2.1 Analysis Framework Engine

**Issue**: TAM/SAM/SOM, Porter's Five Forces, PESTEL, SWOT and other frameworks only appear in text descriptions of Agent Profiles, not structured as executable templates.

**Plan**: Upgrade analysis frameworks from "prompt text" to "structured execution engine".

```python
# New: src/core/analysis/frameworks/
class AnalysisFramework:
    """Analysis Framework Base Class"""
    
class TAMSAMSOMFramework(AnalysisFramework):
    """TAM/SAM/SOM Framework"""
    def execute(self, data: Dict) -> Dict:
        # Parse TAM, SAM, SOM three layers
        # Calculate penetration rate, CAGR
        # Identify growth drivers
        return structured_result

class PorterFiveForcesFramework(AnalysisFramework):
    """Porter's Five Forces Framework"""
    def execute(self, data: Dict) -> Dict:
        # Assess intensity of 5 competitive forces
        # Generate quantitative scoring table
        return structured_result
```

**Each analysis framework returns structured JSON**, not free text, facilitating aggregation and quality verification.

---

#### 2.2 Iterative Deepening Loop

**Issue**: The system is a single-pass architecture, lacking the "hypothesis → verify → revise → deepen" research loop.

**Plan**: Add iteration controller in `ExecutionEngine`:

```python
class DepthController:
    """Depth Controller - Controls Research Iteration"""
    
    async def research_with_iteration(self, topic: str, max_iterations: int = 3):
        for i in range(max_iterations):
            # 1. Execute one research round
            result = await self._execute_round()
            
            # 2. Analyze knowledge gaps
            gaps = await self._identify_gaps(result)
            
            if not gaps:
                break  # No gaps, early termination
            
            # 3. Supplementary search
            supplements = await self._supplementary_research(gaps)
            
            # 4. Revise analysis
            result = await self._revise_analysis(result, supplements)
        
        return result
```

---

#### 2.3 Domain Knowledge Injection

**Issue**: Agents lack industry-specific prior knowledge, starting from scratch for each research.

**Plan**: Pre-build "industry knowledge skeletons" for high-frequency industries:

```yaml
# config/industry_knowledge/new_energy_vehicles.yaml
industry: New Energy Vehicles
key_metrics:
  - Penetration Rate: "Monthly NEV Sales / Monthly Total Vehicle Sales"
  - CAGR: "Compound Annual Growth Rate"
  - CR4: "Top 4 Enterprise Market Share"
key_frameworks:
  - "Penetration Rate S-Curve Analysis"
  - "ICE-EV Parity Model"
  - "Capacity Utilization → Profit Margin Transmission"
data_sources:
  - CAAM
  - CPCA
  - MarkLines
  - EVTank
common_analysis:
  - Battery Cost Decline Path vs Vehicle Price Reduction Space
  - Charging Infrastructure Density vs Penetration Rate Ceiling
```

---

## 3. Execution Priority Matrix

| No. | Optimization Item | Input | Output | ROI | Dependency |
|------|--------|------|------|-----|------|
| P0.1 | Restore 5-Phase Pipeline | 0.5 day | Phase Quality Gates + Specialization | ⭐⭐⭐⭐⭐ | None |
| P0.2 | Default Detailed Framework | 0.1 day | Agents from 3→13+ | ⭐⭐⭐⭐⭐ | None |
| P0.3 | Agent Creation Linkage Verification | 0.3 day | Ensure 13 sections correctly passed | ⭐⭐⭐⭐⭐ | P0.2 |
| P1.1 | Prompt Depth Enhancement | 1 day | 2-3x Agent Output Quality | ⭐⭐⭐⭐⭐ | None |
| P1.2 | Search Strategy Upgrade | 1.5 days | Data Diversity + International Sources | ⭐⭐⭐⭐ | None |
| P1.3 | Independent Deep Analysis | 1 day | Analysis→Supplement→Re-analyze Cycle | ⭐⭐⭐⭐ | P0.1 |
| P1.4 | Quality Check Activation | 1 day | Data Error Rate ↓ | ⭐⭐⭐⭐ | P0.1 |
| P2.1 | Analysis Framework Engine | 3 days | Structured Analysis Output | ⭐⭐⭐ | P1.1 |
| P2.2 | Iterative Deepening Loop | 2 days | Multi-round Deepening Capability | ⭐⭐⭐ | P1.3 |
| P2.3 | Domain Knowledge Injection | 3 days | Industry Prior Knowledge | ⭐⭐⭐ | Ongoing |

---

## 4. Expected Effects

After executing in priority order:

| Metric | Current Value | After P0 | After P0+P1 | After P0+P1+P2 |
|------|--------|------|----------|------------|
| Agents per Task | 3 | 13-15 | 15-20 | 20-36 |
| Sections Covered | 3 | 10-13 | 10-13 | 13+ |
| Search Source Diversity | Single Source 80% | Multi-source | International >30% | Configurable |
| Data Cross-Verification | None | Yes | Auto-verify + Supplement | Full-chain Verify |
| Analysis Framework Depth | Free Text | Structure-guided | Semi-structured | Fully Structured |
| Iterative Deepening | None | None | 1 Round Supplement | Multi-round Iteration |
| Quality Gates | Basically None | 3-Phase Check | 5-Phase Check | Full-chain Check |

---

## 5. Implementation Suggestions

### Implementation Order

```
Week 1: P0.1 + P0.2 + P0.3 (half day) → Immediate Results
   ↓
Week 1-2: P1.1 + P1.4 (2 days) → Prompt and Quality → Baseline Quality Improvement
   ↓
Week 2-3: P1.2 + P1.3 (2.5 days) → Search and Deep Analysis
   ↓
Week 3-4: P2.2 (2 days) → Iteration Loop → Core Differentiation Capability
   ↓
Week 4-6: P2.1 + P2.3 (6 days) → Framework Engine + Knowledge Injection → Professional Moat
```

### Key Checkpoints

1. **After P0 Complete** → Execute one full research, check if Agent count reaches 13+, section coverage 10+
2. **After P1 Complete** → Compare report quality before and after optimization (data density, analysis depth, source diversity)
3. **After P2 Complete** → Compare against international consulting firm (McKinsey, Goldman Sachs) report quality

---

## 6. Appendix: Key Code Locations

| Modification | File | Line |
|--------|------|------|
| ExecutionStage Enum | `src/core/orchestrator/execution/engine.py` | 106-110 |
| Agent Classification Logic | `src/core/orchestrator/execution/engine.py` | 193-217, 313-389 |
| Task Decomposition Strategy | `src/core/decomposition/strategies.py` | 209-609 |
| Framework Selection Logic | `src/core/orchestrator/smart_clarifier.py` | 473-567 |
| Template Definition | `config/templates/industry_report.yaml` | 1-139 |
| Framework Configuration | `config/research_frameworks.yaml` | 1-332 |
| Prompt Rendering | `src/core/prompt_manager.py` | 1-382 |
| Agent Factory | `src/core/agents/factory.py` | Global |
| Search Skill | `src/skills/search_skill.py` | 1-632 |
| Quality Check | `src/core/quality/` | Global |
