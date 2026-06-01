# Prompt Externalization Refactoring Plan (Revised)

> Based on comprehensive codebase audit and analysis of original plan issues, a redesigned Prompt externalization plan.
>
> Analysis Date: 2026-04-30
> Audit Scope: src/core/agents/ src/core/analysis/ src/core/decomposition/ src/core/orchestrator/ src/skills/

---

## Table of Contents

1. [Current Status: Prompt Panorama in Codebase](#1-current-status-prompt-panorama-in-codebase)
2. [Existing Infrastructure Inventory](#2-existing-infrastructure-inventory)
3. [Original Plan Issue Summary](#3-original-plan-issue-summary)
4. [Revised Plan Design Principles](#4-revised-plan-design-principles)
5. [Target Architecture](#5-target-architecture)
6. [Directory Structure Design](#6-directory-structure-design)
7. [PromptManager Specification](#7-promptmanager-specification)
8. [Migration Strategy](#8-migration-strategy)
9. [Implementation Plan](#9-implementation-plan)
10. [Risks and Mitigation](#10-risks-and-mitigation)

---

## 1. Current Status: Prompt Panorama in Codebase

### 1.1 Three Independent Prompt Construction Chains

There are **three independent and non-shared** prompt construction chains in the codebase:

```
┌─────────────────────────────────────────────────────────────────┐
│  Chain A: generic_agent.py (by Role Dimension)                  │
│                                                                  │
│  _get_professional_role_prompt()    ← 14 role role_map          │
│  _build_research_prompt_with_data() ← Research prompt with data │
│  _build_basic_research_prompt()     ← Basic research prompt     │
│  _build_synthesis_prompt_with_data() ← Synthesis prompt (3 var)│
│       │                                                          │
│       ▼                                                          │
│  GenericAgent.execute() → llm_skill.execute(prompt=...)          │
└──────┬──────────────────────────────────────────────────────────┘
       │ Location: src/core/agents/generic_agent.py (L1669-2421)
       │
┌──────▼──────────────────────────────────────────────────────────┐
│  Chain B: strategies.py (by Phase Dimension)                    │
│                                                                  │
│  _build_data_collection_prompt()    ← Data collection phase     │
│  _build_validation_prompt()         ← Data validation phase     │
│  _build_analysis_prompt()           ← Deep analysis phase       │
│  _build_synthesis_prompt()          ← Synthesis phase (4 vars)  │
│  _build_report_prompt()             ← Report generation phase   │
│       │                                                          │
│       ▼                                                          │
│  AgentSpec.system_prompt → ExecutionEngine → GenericAgent → LLM │
└──────┬──────────────────────────────────────────────────────────┘
       │ Location: src/core/decomposition/strategies.py (L407-660)
       │
┌──────▼──────────────────────────────────────────────────────────┐
│  Chain C: orchestrator.py (by Agent Type Dimension)             │
│                                                                  │
│  body_agent system_prompt        ← Synthesis Agent (~40 lines)  │
│  summary_agent system_prompt     ← Executive Summary Agent      │
│  conclusion_agent system_prompt  ← Conclusion Agent             │
│       │                                                          │
│       ▼                                                          │
│  AgentCapability.system_prompt → AgentFactory → ... → LLM       │
└──────┬──────────────────────────────────────────────────────────┘
       │ Location: src/core/orchestrator/orchestrator.py (L2952-3095)
       │
┌──────▼──────────────────────────────────────────────────────────┐
│  Chain D: phase_prompts.py (by Phase, Structured Templates)     │
│                                                                  │
│  PhasePromptTemplate dataclass    ← Structured templates        │
│  PhasePrompts manager              ← Template manager           │
│  get_prompt_for_phase()            ← Convenience function       │
│       │                                                          │
│       ▼                                                          │
│  PhaseOrchestrator → LLM Call                                    │
└──────┬──────────────────────────────────────────────────────────┘
       │ Location: src/core/analysis/phase_prompts.py (382 lines)
```

### 1.2 Detailed Data for Each Chain

| Dimension | Chain A (generic_agent.py) | Chain B (strategies.py) | Chain C (orchestrator.py) | Chain D (phase_prompts.py) |
|------|--------------------------|----------------------|------------------------|--------------------------|
| Prompt Lines | ~250 lines | ~250 lines | ~80 lines | ~160 lines |
| Roles/Phases | 14 roles + 1 default | 5 phases + sub-variants | 2 Agent types | 5 phases |
| Template Form | f-string mixed with logic | f-string mixed with logic | f-string mixed with logic | Structured dataclass |
| Condition Branches | Yes (3 synthesis variants) | Yes (4 synthesis variants) | Yes (summary/conclusion) | No (independent templates) |
| Shared Fragments | format_rules (14x concatenated) | Style requirements (3x repeated) | None | None |
| Loading Method | Direct method call | Direct method call | Direct method call | PhasePrompts manager |

### 1.3 Prompt Variable Dependency Analysis

Each chain's prompts reference completely different variables:

| Variable | Chain A | Chain B | Chain C | Chain D |
|------|--------|--------|--------|--------|
| topic | ✅ | ✅ | ✅ | ✅ |
| aspect | ✅ | ✅ | ✅ | ✅ (optional) |
| aspects | ✅ | ✅ | ❌ | ❌ |
| data_str | ✅ | ❌ | ❌ | ❌ |
| focus_areas | ❌ | ✅ | ✅ | ❌ |
| metrics | ❌ | ✅ | ✅ | ❌ |
| sources | ❌ | ✅ | ✅ | ❌ |
| analysis_depth | ❌ | ❌ | ✅ | ❌ |
| min_length | ❌ | ❌ | ✅ | ❌ |
| context(dict) | ❌ | ❌ | ❌ | ✅ |
| output_schema | ❌ | ❌ | ❌ | ✅ |
| framework_config | ❌ | ✅ | ✅ | ❌ |

### 1.4 Duplicate Content Identification

Cross-chain duplicated content:

| Duplicate Content | Location | Frequency | Variance |
|---------|---------|---------|-------|
| Writing style specification (no colloquial, etc.) | Chain B, C | 7+ times | Low (slightly different wording) |
| Source annotation prohibition | Chain A, B, C | 10+ times | Low |
| Judgment sentence start requirement | Chain A, B | 5+ times | Low |
| Data cross-validation requirement | Chain A, C | 4+ times | Low |
| format_rules (output specification) | Chain A | 14x concatenated | Identical |

---

## 2. Existing Infrastructure Inventory

### 2.1 Reusable Infrastructure

```
✅ config/research_frameworks.yaml  ← Framework configuration
✅ config/agents.yaml                ← Agent configuration
✅ src/core/analysis/phase_prompts.py ← PromptManager + structured templates (strongest candidate)
✅ src/skills/llm_skill.py           ← Unified prompt → LLM call entry point
✅ src/core/decomposition/strategies.py ← AgentSpec.prompt delivery system
```

### 2.2 PhasePrompts Existing Design Assessment

```
PhasePromptTemplate:
  ┌────────────────────────────┐
  │ phase: str                 │ ← Phase identifier
  │ role_definition: str       │ ← Role definition
  │ goal_template: str         │ ← Goal template (with {variables})
  │ instructions: List[str]    │ ← Instruction list
  │ output_schema: Dict        │ ← Output structure definition
  │ examples: List[Dict]       │ ← Examples
  │ frameworks: List[Enum]     │ ← Analysis frameworks
  └────────────────────────────┘
  │
  └──→ render(topic, aspect, context) → str
```

**Advantages**:
- Structured fields (role_definition / instructions separated)
- Built-in `render()` method supporting template variable substitution
- Extensible: `custom_prompts` parameter, `register_prompt()` runtime registration
- Field-level individual externalization, no need for full-block replacement

**Disadvantages**:
- Content still hardcoded in Python code (inside `_init_phase_prompts()`)
- No template nesting support
- No YAML frontmatter metadata
- No file loading mechanism

---

## 3. Original Plan Issue Summary

| # | Issue | Severity | Description |
|---|------|---------|------|
| 1 | **Ignored Existing PhasePrompts System** | 🔴 Blocking | Plan didn't mention `phase_prompts.py`, would create two parallel management systems |
| 2 | **Role List Inaccurate** | 🔴 Blocking | 3 out of 14 roles misnamed, 2 omissions, 1 non-existent |
| 3 | **Didn't Consider Role x Phase Orthogonality** | 🔴 Blocking | Roles and methodologies organized by different dimensions in 3 chains, flat directory can't express |
| 4 | **PromptManager Too Simple** | 🟡 Important | No template nesting, no schema validation, `str.format` fragile, hardcoded subdirectories |
| 5 | **Incorrect Directory Location** | 🟡 Important | `config/prompts/` semantically wrong; prompts are behavior code, not deployment config |
| 6 | **Unclear Boundary Division** | 🟡 Important | 3-way branches can't be expressed through plain text templates, conditional logic stays in Python |
| 7 | **No Migration Path** | 🟡 Important | Transition period, rollback, test compatibility, A/B testing not considered |
| 8 | **format_rules Repetition Exaggerated** | 🟢 Minor | Only 1 definition in code, not 14; repetition is in concatenation behavior, not storage |

---

## 4. Revised Plan Design Principles

### Principle 1: Integrate First, Externalize Later

Don't create an isolated PromptManager. First integrate the differences across the three chains, eliminate duplication, **then consider** externalizing the final unified content.

```
Current Status: 3 independent chains → Integrate into unified template system → Externalize to files as needed
```

### Principle 2: PhasePrompts is the Foundation, Not Competition

`PhasePrompts` already has the best structured design (dataclass + render + schema). The new plan should extend it, not replace it.

### Principle 3: Progressive, Reversible

Each Phase can be independently verified after completion. No requirement to externalize everything at once. Each Phase should have clear Before/After comparison.

### Principle 4: Organize by "Shared Dimensions", Not "Source Files"

Original plan organized by source files (roles/ tasks/ agents/), but prompts from different source files have significant semantic overlap. Should organize by **shared dimension** - when a writing specification is referenced by 3 chains, extract it as an independent fragment.

### Principle 5: Content in `src/`, Config in `config/`

- `src/core/prompts/` — Prompt template files (behavior definition, version-bound with code)
- `config/prompts/` — Prompt meta-configuration (override paths, enable toggles, environment-related)

---

## 5. Target Architecture

### 5.1 Unified Three-Layer Prompt System

```
┌─────────────────────────────────────────────────────────────────┐
│                     Unified Prompt System                        │
│                                                                  │
│  Layer 1: Atomic Fragments (Atoms)                               │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ Writing style specification (no colloquial, source rules)│      │
│  │ Role definitions (market size analyst, competition, etc) │      │
│  │ Analysis framework descriptions (Porter Five Forces)     │      │
│  │ Output specifications (format_rules)                     │      │
│  └────────────────────────────────────────────────────────┘     │
│                            │ Composition                        │
│                            ▼                                    │
│  Layer 2: Templates                                            │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ research_prompt_template      (role+data+spec)          │      │
│  │ synthesis_prompt_template     (constraints+style+struct)│      │
│  │ body_agent_template           (framework+metrics+source)│      │
│  │ summary_template / conclusion_template                   │      │
│  └────────────────────────────────────────────────────────┘     │
│                            │ Instantiation (fill variables)     │
│                            ▼                                    │
│  Layer 3: Rendered Prompt → LLM                                │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Integrated Call Relationship

```
  strategies.py          orchestrator.py        generic_agent.py
  _build_*_prompt()      _create_agents()       _build_*_prompt()
       │                      │                      │
       │    (Unified Template Layer)                  │
       └──────────────────┬───┘──────────────────────┘
                          │
               PromptManager.render(
                   template_name="research_prompt",
                   role_name="market_size",
                   shared_fragments=["writing_style", "output_spec"],
                   **variables
               )
                          │
                          ▼
  PhasePrompts.render()   ← Extended based on existing PhasePromptTemplate
       │
       ▼
   PhasePromptTemplate Instance
   (role_definition + goal_template + instructions + output_schema)
       │
       ▼
  str → LLM / Agent.system_prompt
```

---

## 6. Directory Structure Design

### 6.1 Final Directory Structure

```
src/core/prompts/                       ← Prompt templates (behavior code, version-bound)
├── __init__.py
├── manager.py                          ← PromptManager (based on PhasePrompts extension)
│
├── atoms/                              ← Layer 1: Atomic fragments
│   ├── roles/                           Role definitions
│   │   ├── market_size.yaml
│   │   ├── competition.yaml
│   │   ├── trend.yaml
│   │   ├── industry_chain.yaml
│   │   ├── financial.yaml              ← Missing in original plan
│   │   ├── valuation.yaml              ← Missing in original plan
│   │   ├── policy.yaml
│   │   ├── technology.yaml
│   │   ├── enterprise.yaml
│   │   ├── consumer.yaml               ← Doesn't exist in current code (new reserved)
│   │   ├── risk.yaml
│   │   ├── investment.yaml
│   │   ├── executive_summary.yaml
│   │   ├── conclusion.yaml
│   │   ├── validation.yaml
│   │   └── general.yaml
│   │
│   ├── frameworks/                     Analysis frameworks
│   │   ├── porter_five_forces.yaml
│   │   ├── pestel.yaml
│   │   ├── swot.yaml
│   │   ├── scr.yaml
│   │   ├── tam_sam_som.yaml
│   │   └── du_pont.yaml
│   │
│   └── standards/                      General specifications (multi-reference)
│       ├── writing_style.yaml          Writing style (no colloquial, etc.)
│       ├── output_spec.yaml            Output specification (format_rules)
│       └── source_citation.yaml        Source citation rules
│
├── templates/                          ← Layer 2: Templates (compose atomic fragments)
│   ├── research_with_data.yaml         Chain A: Research prompt with data
│   ├── research_basic.yaml             Chain A: Basic research prompt
│   ├── synthesis_with_data.yaml        Chain A: Synthesis prompt
│   ├── data_collection.yaml            Chain B: Data collection
│   ├── data_validation.yaml            Chain B: Data validation
│   ├── deep_analysis.yaml              Chain B: Deep analysis
│   ├── synthesis_summary.yaml          Chain B: Executive summary
│   ├── synthesis_conclusion.yaml       Chain B: Research conclusion
│   ├── synthesis_insight.yaml          Chain B: Core insight
│   ├── synthesis_general.yaml          Chain B: General synthesis
│   ├── body_agent.yaml                 Chain C: body agent system prompt
│   ├── executive_summary_agent.yaml    Chain C: summary agent
│   └── conclusion_agent.yaml           Chain C: conclusion agent
│
└── schemas/                            ← Template variable Schema definitions
    ├── research_with_data.schema.json
    ├── synthesis.schema.json
    └── body_agent.schema.json

config/prompts/                         ← Prompt configuration (environment-related)
├── settings.yaml                       ← Override paths, enable/disable toggles
└── overrides/                          ← Production environment overrides
    └── writing_style.yaml
```

### 6.2 Why Not in `config/prompts/`

- **Semantic issue**: LLM prompts are **behavior definitions** (determine how Agents think), not deployment configuration. They version-evolve together with Python code.
- **Modification frequency**: Prompt modification frequency is same as code (every feature iteration may change), not like `settings.yaml` that only changes with environment.
- **Content size**: Total prompt files expected to be 100+, placing in `config/` would pollute the config directory.

**Exception**: `config/prompts/overrides/` for production environment fine-tuning overrides (non-developers change prompts without changing code).

### 6.3 File Format Choice: YAML Instead of .md

Original plan uses `.md` plain text format, but based on current status analysis, **YAML** is recommended:

| Dimension | .md Plain Text | YAML Structured |
|------|-----------|------------|
| Role definition + analysis framework | Mixed in Markdown text | Independent fields, can be loaded individually |
| Variable substitution | `str.format()` fragile | Jinja2/string.Template both work |
| Metadata (version, author, etc.) | YAML frontmatter non-standard | Native support |
| Nesting/Reference | None | Supports `$ref` or `!include` |
| Match existing infrastructure | Mismatched | `research_frameworks.yaml` already uses YAML |
| Schema validation | None | JSON Schema can validate YAML |

---

## 7. PromptManager Specification

### 7.1 Core API

```python
class PromptManager:
    """
    Unified Prompt Manager
    
    Responsibilities:
    1. Load atomic fragments (atoms/) and templates (templates/)
    2. Support template nesting (a template references multiple atomic fragments)
    3. Support variable substitution and Schema validation
    4. Cache loaded content
    5. Compatible with PhasePromptTemplate interface
    
    Design Principles:
    - Non-invasive: Don't change existing caller API signatures
    - Progressive: Existing code can migrate gradually
    - Reversible: Each template can independently switch back to hardcoded version
    """
    
    def __init__(self, base_dir: str = "src/core/prompts"):
        ...
    
    def load_atom(self, name: str) -> dict:
        """Load atomic fragment (YAML -> dict)"""
        ...
    
    def load_template(self, name: str) -> dict:
        """Load template (YAML -> dict, with variable declarations)"""
        ...
    
    def render(self, template_name: str, **variables) -> str:
        """
        Render template to final prompt string
        
        Compatible with PhasePromptTemplate.render() signature:
        render(topic, aspect, context) continues to work
        """
        ...
```

---

## 8. Migration Strategy

### 8.1 Four-Phase Progressive Migration

```
Phase 0: Infrastructure (no behavior change)
┌──────────────────────────────────────────────┐
│ Create src/core/prompts/ directory structure  │
│ Implement PromptManager class                │
│ Extend based on PhasePromptTemplate           │
│ Unit tests: template loading + rendering      │
│ Effect: New code, zero modification, zero risk│
└──────────────────────────────────────────────┘

Phase 1: PhasePrompts Internal Refactor (Chain D, no external impact)
┌──────────────────────────────────────────────┐
│ Move hardcoded templates in                  │
│ _init_phase_prompts() to YAML files one by one│
│ PhasePrompts internally uses PromptManager   │
│ Keep get_prompt_for_phase() API unchanged    │
│ Effect: Callers zero modification            │
└──────────────────────────────────────────────┘

Phase 2: Atomic Fragment Extraction
┌──────────────────────────────────────────────┐
│ Identify duplicate content across 3 chains    │
│ Extract to shared YAML under atoms/standards/ │
│ Unify at atomic fragment layer first          │
│ Effect: Eliminate 80%+ cross-chain duplication│
└──────────────────────────────────────────────┘

Phase 3: Chains A/B/C Template Externalization
┌──────────────────────────────────────────────┐
│ Replace 4 prompt methods in generic_agent.py │
│ Replace 6 _build_*_prompt in strategies.py   │
│ Replace 3 system_prompts in orchestrator.py  │
│ Each replacement: compare output, run tests  │
│ Effect: All prompts externalized             │
└──────────────────────────────────────────────┘
```

---

## 9. Implementation Plan

### 9.1 Effort Estimation

| Phase | Files Involved | Estimated Effort | Risk | Pass Criteria |
|-------|---------|---------|------|---------|
| 0: Infrastructure | New 5-8 files | 2-3 days | Low | Unit tests pass |
| 1: PhasePrompts Refactor | phase_prompts.py + 5 YAML | 2-3 days | Low | Output comparison passes |
| 2: Atomic Fragment Extraction | 3-5 YAML + audit | 3-5 days | Medium | Duplicate elimination > 80% |
| 3a: generic_agent refactor | generic_agent.py + 4 YAML | 3-4 days | Medium-High | LLM output comparison matches |
| 3b: strategies refactor | strategies.py + 6 YAML | 3-4 days | Medium-High | LLM output comparison matches |
| 3c: orchestrator refactor | orchestrator.py + 3 YAML | 1-2 days | Medium | LLM output comparison matches |
| 4: Cleanup optimization | Various files | 2-3 days | Low | Old code deleted, reload works |

**Total: 16-24 person-days**

---

## 10. Risks and Mitigation

### 10.1 Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------|------|---------|
| Jinja2 syntax introduces bugs in existing prompts | Medium | Medium | Output comparison after each migration; use `str.format` as transition |
| YAML file encoding issues (Chinese) | Low | High | Explicit UTF-8; CI add encoding check |
| Template variable changes cause render failures | Medium | High | Schema validation + pre-render variable check + hardcoded fallback |
| Atomic fragment extraction breaks original semantics | Medium | Medium | Before/after comparison, merge one by one |
| PhasePrompts caller changes | Low | Medium | Keep `get_prompt_for_phase()` API unchanged |
| Team unfamiliar with YAML format | Medium | Low | Provide template writing docs + schema auto-completion |

---

*End of Revised Plan*
