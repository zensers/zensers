# Report Framework Communication Refactoring Plan

> **Version:** v1.0
> **Date:** 2026-05-04
> **Status:** Design Draft

---

## Table of Contents

1. [Background and Problem Summary](#1-background-and-problem-summary)
2. [Architecture Design Goals](#2-architecture-design-goals)
3. [Overall Design Plan](#3-overall-design-plan)
4. [Detailed Design](#4-detailed-design)
   - 4.1 Parameter Configuration Layer - `research_frameworks.yaml` Extension
   - 4.2 Model Layer - New `InteractionParameter` Model
   - 4.3 Logic Layer - `SmartClarifier` Type-Aware Refactoring
   - 4.4 Presentation Layer - CLI Dynamic Parameter Rendering
   - 4.5 Internationalization
5. [File Modification List](#5-file-modification-list)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Appendix: Parameter Configuration Reference](#7-appendix-parameter-configuration-reference)

---

## 1. Background and Problem Summary

### 1.1 Current System Flow

```
User Input → SmartClarifier Interaction Flow
              ├── Step 1: Select Output Type (13 hardcoded options)
              ├── Step 2: Select Framework (Detailed/Standard/Concise)
              ├── Step 3: Confirm Sections
              ├── Step 4: Set Parameters (region + time_range ← hardcoded)
              └── Step 5: Final Confirmation
                     ↓
         ResearchFrameworkManager (Agent config, unrelated to interaction)
                     ↓
         ExecutionEngine → ReportGenerationAgent
```

### 1.2 Identified 8 Issues

| # | Issue | Severity | Impact Scope |
|---|------|--------|----------|
| P1 | **All types share one parameter set** — region/time_range hardcoded | 🔴 Blocking | All non-industry-research types |
| P2 | **SmartClarifier lacks type awareness** — no output_type branching | 🔴 Blocking | Architecture layer |
| P3 | **Framework tier logic mismatches non-industry templates** — section ID hardcoded | 🟡 Serious | Weekly/Quarterly reports, competitor analysis |
| P4 | **Multilingual stops at config layer** — CLI fully Chinese hardcoded | 🟡 Serious | International users |
| P5 | **Parameters disconnected from ResearchFrameworkConfig** | 🟡 Serious | Architecture layer |
| P6 | **depth parameter overlaps with framework semantics** | 🟢 Minor | UX |
| P7 | **CLI callback lacks dynamic parameter support** — hardcoded region/time_range | 🟡 Serious | CLI frontend |
| P8 | **output_type CLI help incomplete** | 🟢 Minor | Documentation |

---

## 2. Architecture Design Goals

### 2.1 Core Principles

1. **Type-Driven** — Each report type defines its own interaction parameter set
2. **Configuration-First** — Interaction parameters defined via YAML config, no code changes
3. **Graceful Degradation** — Types without configured parameters use defaults
4. **Native Multilingual** — All user-visible text supports i18n

### 2.2 Design Goals

```
                  ResearchFrameworkConfig
                  (Extended: new interaction field)
                         │
                         ▼ Load
                  ResearchFrameworkManager
                  (New: get_interaction_params)
                         │
                         ▼ Inject
                  SmartClarifier (Refactored)
                         │
                  Step 4: Dynamic Parameters
                  Load corresponding
                  interaction_params by output_type
                         │
                         ▼ Pass
                  CLI Callback
                  (Dynamically render any parameter fields)
```

---

## 3. Overall Design Plan

### 3.1 Four-Layer Architecture

```
Layer 1: Configuration Layer
research_frameworks.yaml Extension
└─ Each framework adds interaction_parameters field

Layer 2: Model Layer
New InteractionParameter Model
└─ Supports text / select / multi_select / date types

Layer 3: Logic Layer
SmartClarifier Refactoring
└─ confirm_sections() → Read parameters from framework config

Layer 4: Presentation Layer
CLI Callback + i18n Full Chain
└─ Dynamic rendering + Language switching
```

### 3.2 Core Data Flow

```
research_frameworks.yaml (Extended)
         │
         ▼ Load
ResearchFrameworkManager (New get_interaction_params)
         │
         ▼ Lookup
SmartClarifier (Refactored)
└─ output_type lookup → Return corresponding interaction_parameters
         │
         ▼ Render
CLI Callback
└─ parameters field dynamic rendering (supports text / select / multi_select)
         │
         ▼ Collect
UserChoice Struct Extension
→ ResearchRequirement → Final delivery to ExecutionEngine
```

---

## 4. Detailed Design

### 4.1 Configuration Layer - `research_frameworks.yaml` Extension

#### 4.1.1 New `interaction_parameters` Field

Add `interaction_parameters` node under each framework config in `config/research_frameworks.yaml`.

```yaml
# research_frameworks.yaml extension example
industry_report:
  name: "Industry Research Report"
  description: "Comprehensive industry analysis including market size, competitive landscape, trend forecasting"
  # ... existing agent_config and section_weights remain unchanged ...
  
  # === New: Interaction Parameter Config ===
  interaction_parameters:
    region:
      type: select
      label:
        zh: "Research Region"
        en: "Research Region"
      default: "China"
      options:
        - value: "China"
          label:
            zh: "China"
            en: "China"
        - value: "Global"
          label:
            zh: "Global"
            en: "Global"
        - value: "US"
          label:
            zh: "US"
            en: "US"
        - value: "Europe"
          label:
            zh: "Europe"
            en: "Europe"
    
    time_range:
      type: select
      label:
        zh: "Time Range"
        en: "Time Range"
      default: "3 years"
      options:
        - value: "1 year"
          label:
            zh: "1 year"
            en: "1 year"
        - value: "3 years"
          label:
            zh: "3 years"
            en: "3 years"
        - value: "5 years"
          label:
            zh: "5 years"
            en: "5 years"
```

### 4.2 Model Layer - New `InteractionParameter` Model

```python
@dataclass
class InteractionParameter:
    """Interaction parameter model"""
    name: str
    type: str  # text / select / multi_select / date
    label: Dict[str, str]  # i18n labels
    default: Any
    options: Optional[List[Dict]] = None
    required: bool = True
    validation: Optional[Dict] = None  # e.g. {"min": 1, "max": 100}

    @classmethod
    def from_yaml(cls, name: str, config: Dict) -> "InteractionParameter":
        return cls(
            name=name,
            type=config.get("type", "text"),
            label=config.get("label", {}),
            default=config.get("default"),
            options=config.get("options"),
            required=config.get("required", True),
            validation=config.get("validation"),
        )
```

### 4.3 Logic Layer - SmartClarifier Type-Aware Refactoring

```python
class SmartClarifier:
    """Report framework interaction manager - type aware"""

    def __init__(self, framework_manager: ResearchFrameworkManager):
        self._framework_manager = framework_manager

    def get_interaction_params(self, output_type: str) -> List[InteractionParameter]:
        """
        Get interaction parameters for a specific output type.
        
        Returns configured parameters if available,
        falls back to default parameters otherwise.
        """
        framework = self._framework_manager.get_framework(output_type)
        if not framework:
            return self._get_default_params()
        params_config = framework.get("interaction_parameters", {})
        if not params_config:
            return self._get_default_params()
        return [
            InteractionParameter.from_yaml(name, config)
            for name, config in params_config.items()
        ]

    def _get_default_params(self) -> List[InteractionParameter]:
        """Default parameters fallback"""
        return [
            InteractionParameter(
                name="region",
                type="select",
                label={"zh": "Research Region", "en": "Research Region"},
                default="China",
                options=[
                    {"value": "China", "label": {"zh": "China", "en": "China"}},
                    {"value": "Global", "label": {"zh": "Global", "en": "Global"}},
                ],
            ),
            InteractionParameter(
                name="time_range",
                type="select",
                label={"zh": "Time Range", "en": "Time Range"},
                default="1 year",
                options=[
                    {"value": "1 year", "label": {"zh": "1 year", "en": "1 year"}},
                    {"value": "3 years", "label": {"zh": "3 years", "en": "3 years"}},
                ],
            ),
        ]
```

### 4.4 Presentation Layer - CLI Dynamic Parameter Rendering

```python
async def _render_interaction_params(
    params: List[InteractionParameter],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Dynamically render interaction parameters as CLI prompts.
    Supports text, select, multi_select, date types.
    """
    result = {}
    for param in params:
        label = param.label.get(language, param.label.get("en", param.name))

        if param.type == "select":
            options_text = "\n".join(
                f"  {i+1}. {opt['label'].get(language, opt['value'])}"
                for i, opt in enumerate(param.options or [])
            )
            print(f"\n{label}:")
            print(options_text)
            choice = input(f"Select (1-{len(param.options or [])}, default: {param.default}): ").strip()
            if choice and choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(param.options or []):
                    result[param.name] = param.options[idx]["value"]
                else:
                    result[param.name] = param.default
            else:
                result[param.name] = param.default

        elif param.type == "text":
            value = input(f"\n{label} (default: {param.default}): ").strip()
            result[param.name] = value or param.default

    return result
```

### 4.5 Internationalization

```python
class I18nManager:
    """Simple i18n manager for CLI text"""

    TRANSLATIONS = {
        "select_output_type": {
            "en": "Select output type",
            "zh": "Select output type",
        },
        "select_framework": {
            "en": "Select research framework",
            "zh": "Select research framework",
        },
        "confirm_sections": {
            "en": "Confirm report sections",
            "zh": "Confirm report sections",
        },
        "set_parameters": {
            "en": "Set research parameters",
            "zh": "Set research parameters",
        },
        "final_confirm": {
            "en": "Confirm and start research",
            "zh": "Confirm and start research",
        },
    }

    def __init__(self, language: str = "en"):
        self.language = language

    def get(self, key: str) -> str:
        return self.TRANSLATIONS.get(key, {}).get(self.language, key)
```

---

## 5. File Modification List

| File | Change | Effort |
|------|--------|--------|
| `config/research_frameworks.yaml` | Add interaction_parameters field (per framework) | 2h |
| `src/core/models/interaction_parameter.py` | New InteractionParameter model | 1h |
| `src/core/orchestrator/smart_clarifier.py` | Add get_interaction_params() + type-aware branching | 3h |
| `src/core/orchestrator/research_framework_manager.py` | Add get_framework() method | 1h |
| `src/cli/main.py` | Dynamic parameter rendering + language support | 3h |
| `src/core/i18n/manager.py` | New I18nManager | 1h |

---

## 6. Implementation Roadmap

| Phase | Content | Effort | Risk |
|-------|---------|--------|------|
| Phase 1 | YAML config extension + model class | 3h | Low |
| Phase 2 | SmartClarifier refactoring + type-aware logic | 4h | Medium |
| Phase 3 | CLI dynamic rendering + i18n | 4h | Medium |
| Phase 4 | Integration test + documentation | 2h | Low |

---

## 7. Appendix: Parameter Configuration Reference

### Parameter Type Definition

| Type | Description | UI Component |
|------|-------------|-------------|
| text | Free text input | Text input field |
| select | Single selection | Dropdown |
| multi_select | Multi-selection | Checkbox list |
| date | Date range | Date picker |

### Multi-language Support

All user-facing labels use dictionary format:
```yaml
label:
  en: "English Text"
  zh: "Chinese Text"
```
