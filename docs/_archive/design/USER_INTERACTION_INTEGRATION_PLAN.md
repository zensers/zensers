# User Interaction Flow Integration Plan

## Design Principles

**Core Principle**: Directly integrate existing components into the main flow, do not create new methods, do not retain redundant code.

| Principle | Description |
|------|------|
| **Unified Entry** | Only keep one `research()` method, integrating the interaction flow |
| **Clean Redundancy** | Remove duplicate interaction components, keep the optimal solution |
| **Simplify State** | Merge similar states, reduce state transition complexity |
| **Clean Code** | Intuitive flow, easy to understand and maintain |

---

## 1. Problem Analysis

### 1.1 Current Flow Missing Steps

**Current Flow** (`Orchestrator.research()`):
```
User Input → Parse Requirements → IntentGate → Create Agents → Execute → Aggregate → Output
```

**Missing User Interaction Steps**:
1. ❌ Requirement clarification - Research object confirmation (China/US/Global)
2. ❌ Framework selection - Research dimensions, section structure confirmation
3. ❌ Focus specification - Target companies, excluded companies
4. ❌ Output format - PPT/Word/PDF selection
5. ❌ Report preview - User reviews draft
6. ❌ Revision loop - User feedback, system fine-tuning
7. ❌ Final approval - User confirms before output

### 1.2 Existing Interaction Component Analysis

**Finding: Component functions differ, cannot simply delete**

### 2.1 RequirementClarifier vs SmartClarifier Detailed Comparison

| Feature | RequirementClarifier | SmartClarifier | Conclusion |
|------|---------------------|----------------|------|
| **Lines** | 281 | 485 | SmartClarifier more complete |
| **Output Types** | ❌ Fixed docx | ✅ 7 types (Report/PPT/QuickView/Policy/Dashboard/Competitor/Custom) | SmartClarifier better |
| **Template Library** | ❌ None | ✅ 6 predefined templates | SmartClarifier better |
| **Section Structure** | ❌ Fixed 8 dimensions | ✅ Adjustable sections per template | SmartClarifier better |
| **Question Types** | ✅ QuestionType enum | ❌ No question type definition | RequirementClarifier better |
| **Question Data Class** | ✅ Complete Question definition | ❌ None | RequirementClarifier better |
| **External References** | ❌ None | ❌ None | Neither uses |

**Integration Strategy (no backward compatibility retained)**:
- ✅ Delete `RequirementClarifier` entire file (functionality fully merged)
- ✅ Data classes (Question, QuestionType) already merged into SmartClarifier
- ❌ Do not retain backward compatibility aliases

### 2.2 ConversationManager Functional Analysis

| Function | Unique? | Description |
|------|----------|------|
| **knowledge_bank integration** | ✅ Unique | Interact with knowledge base, get related entities |
| **State persistence** | ✅ Unique | save_state/load_state methods |
| **Message processing dispatch** | ⚠️ Integratable | process_message dispatches by state |
| **Clarification parsing** | ⚠️ Simplify | _parse_clarification simple implementation |
| **External references** | ❌ Not actually used | Only exported in __init__.py |

**Safe Handling Strategy**:
- ❌ Cannot delete ConversationManager (has unique functionality)
- ✅ Should refactor and simplify (remove redundant methods, keep core functionality)

### 2.3 Correct Integration Strategy

```
Integration Strategy (Final):

RequirementClarifier (281 lines) → ❌ Entire file deleted
    ├─ Question data class → Already merged into SmartClarifier
    ├─ QuestionType enum → Already merged into SmartClarifier
    └─ Class definition → Deleted (functionality duplicated, no backward compat)

SmartClarifier (~550 lines):
    ├─ Keep all
    └─ New: Question, QuestionType (merged from RequirementClarifier)

ConversationManager (281 lines):
    ├─ knowledge_bank integration → ✅ Keep
    ├─ save_state/load_state → ✅ Keep (state persistence)
    ├─ process_message → ⚠️ Simplify (remove simple parsing logic)
    └─ Other methods → ⚠️ Simplify or remove

Final Result:
    SmartClarifier (~550 lines) ← Merged Question classes
    ConversationManager (~150 lines) ← Simplified
    Deleted: requirement_clarifier.py entire file (no backward compat)
```

---

## 2. Existing Component Detailed Analysis

### 2.1 SmartClarifier

**File**: `src/core/orchestrator/smart_clarifier.py`

**Core Design Philosophy**:
- User is a decision-maker, not a respondent
- Provide professional framework options, not open-ended questions
- Visual structure display, let users "see" the result
- Support any output type (Report/PPT/Copy/Data...)

**Flow Steps**:

```
Step 1: start(user_input)
    → Returns output type options
    → [Report] Market Research Report (Word)
    → [PPT] Roadshow PPT
    → [QuickView] Market Quick View
    → [Policy] Policy Interpretation
    → [Custom] Fully Custom

Step 2: select_output_type(output_type)
    → Returns template options for that type
    → Standard Market Research Report (20-30 pages)
    → Investment Roadshow PPT (12-15 pages)
    → Competitor Comparison (8-12 pages)

Step 3: select_template(template_id)
    → Display section structure for adjustment
    → [x] Executive Summary (Required)
    → [ ] Market Size
    → [ ] Competitive Landscape
    → [ ] Technology Trends
    → [ ] Risk Warning

Step 4: set_parameters(parameters)
    → Parameters based on type
    → Region: [China] [US] [Global] [Europe]
    → Time Range: [1 year] [3 years] [5 years]

Step 5: confirm()
    → Display summary for final confirmation
    → [Confirm & Start] [Back & Edit]
```

### 2.2 RequirementClarifier

**File**: `src/core/orchestrator/requirement_clarifier.py`

**Analysis**: This component was designed earlier and is functionally overlapped with SmartClarifier, but has some unique data structures.

**Unique Features**:
- **Question/QuestionType data classes** - Already merged into SmartClarifier
- **go_deep flag** - Allows users to request deep analysis
- **Structured requirement config** - Provides structured config storage

**Deletion Decision**: Entire file can be deleted, core data classes already merged.

### 2.3 ConversationManager

**File**: `src/core/dialogue/conversation_manager.py`

**Analysis**: ConversationManager has unique functionality (knowledge base integration), but message processing overlaps with SmartClarifier.

**Retention Decision**:
- ✅ Keep: knowledge_bank interaction, state persistence
- ⚠️ Simplify: message processing
- ❌ Remove: redundant process_message logic

---

## 3. Integration Plan

### 3.1 SmartClarifier Enhancement

```python
class SmartClarifier:
    """Smart requirement clarifier - handles all interaction types"""

    def __init__(self, framework_manager, knowledge_bank=None):
        self._framework_manager = framework_manager
        self._knowledge_bank = knowledge_bank  # From ConversationManager
        self._session = {}

    async def start(self, user_input: str) -> Dict[str, Any]:
        """
        Start interaction flow.
        Returns output type selection options.
        """
        # Analyze user intent
        intent = await self._analyze_intent(user_input)

        # Get available output types
        output_types = self._get_output_types()

        # Check knowledge base for related entities
        entities = []
        if self._knowledge_bank:
            entities = self._knowledge_bank.search(user_input)

        return {
            "step": "select_output_type",
            "message": "Please select the desired output type",
            "options": output_types,
            "entities": entities,
            "intent": intent,
        }

    async def select_output_type(self, output_type: str) -> Dict[str, Any]:
        """
        Select output type, return available templates.
        """
        templates = self._framework_manager.get_templates(output_type)
        return {
            "step": "select_template",
            "message": "Please select a research template",
            "options": templates,
        }

    async def select_template(self, template_id: str) -> Dict[str, Any]:
        """
        Select template, return section structure.
        """
        template = self._framework_manager.get_template(template_id)
        sections = template.get_sections()
        return {
            "step": "configure_sections",
            "message": "Please confirm the report sections",
            "sections": sections,
        }

    async def set_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Set research parameters based on type.
        """
        return {
            "step": "confirm",
            "message": "Please confirm the research plan",
            "parameters": params,
            "summary": self._generate_summary(),
        }

    async def confirm(self) -> Dict[str, Any]:
        """
        Final confirmation, return complete requirement.
        """
        requirement = self._build_requirement()
        return {
            "step": "done",
            "requirement": requirement,
        }
```

### 3.2 ConversationManager Simplification

```python
class ConversationManager:
    """Simplified conversation manager - state + knowledge base"""

    def __init__(self, knowledge_bank=None):
        self._knowledge_bank = knowledge_bank
        self._state_dir = Path("data/sessions")
        self._state_dir.mkdir(parents=True, exist_ok=True)

    async def search_entities(self, query: str) -> List[Dict]:
        """Search knowledge base for related entities"""
        if not self._knowledge_bank:
            return []
        return self._knowledge_bank.search(query)

    def save_state(self, session_id: str, state: Dict) -> None:
        """Persist conversation state"""
        path = self._state_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)

    def load_state(self, session_id: str) -> Optional[Dict]:
        """Load persisted conversation state"""
        path = self._state_dir / f"{session_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_state(self, session_id: str) -> None:
        """Clear conversation state"""
        path = self._state_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
```

---

## 4. State Machine Integration

### 4.1 Unified State Machine

```python
class UnifiedStateMachine:
    """Unified state machine for interaction flow"""

    STATES = [
        "INITIAL",
        "SELECT_OUTPUT_TYPE",
        "SELECT_TEMPLATE",
        "CONFIGURE_SECTIONS",
        "SET_PARAMETERS",
        "CONFIRM",
        "EXECUTING",
        "PREVIEWING",
        "REVISING",
        "COMPLETED",
    ]

    def __init__(self):
        self._state = "INITIAL"
        self._history = []

    def transition(self, next_state: str) -> bool:
        """Attempt state transition"""
        if self._is_valid_transition(next_state):
            self._history.append(self._state)
            self._state = next_state
            return True
        return False

    def back(self) -> bool:
        """Go back to previous state"""
        if self._history:
            self._state = self._history.pop()
            return True
        return False

    def _is_valid_transition(self, next_state: str) -> bool:
        """Check if transition is valid"""
        valid_transitions = {
            "INITIAL": ["SELECT_OUTPUT_TYPE"],
            "SELECT_OUTPUT_TYPE": ["SELECT_TEMPLATE", "CONFIRM"],
            "SELECT_TEMPLATE": ["CONFIGURE_SECTIONS", "SELECT_OUTPUT_TYPE"],
            "CONFIGURE_SECTIONS": ["SET_PARAMETERS", "SELECT_TEMPLATE"],
            "SET_PARAMETERS": ["CONFIRM", "CONFIGURE_SECTIONS"],
            "CONFIRM": ["EXECUTING", "SET_PARAMETERS"],
            "EXECUTING": ["PREVIEWING", "COMPLETED"],
            "PREVIEWING": ["REVISING", "COMPLETED"],
            "REVISING": ["EXECUTING", "PREVIEWING"],
            "COMPLETED": [],
        }
        return next_state in valid_transitions.get(self._state, [])
```

### 4.2 Orchestrator Integration

```python
class ResearchOrchestrator:
    """
    Research orchestrator with integrated user interaction flow.
    """

    def __init__(self):
        self._clarifier = SmartClarifier(...)
        self._conversation = ConversationManager(...)
        self._state_machine = UnifiedStateMachine()

    async def research(
        self,
        user_input: Union[str, Dict[str, Any]],
        interaction_mode: bool = True,
        **kwargs,
    ) -> ResearchResult:
        """
        Unified research entry point with interaction flow.
        """
        if interaction_mode:
            return await self._research_interactive(user_input, **kwargs)
        return await self._research_auto(user_input, **kwargs)

    async def _research_interactive(
        self,
        user_input: str,
        **kwargs,
    ) -> ResearchResult:
        """Interactive research flow"""
        # Step 1: Start clarification
        result = await self._clarifier.start(user_input)
        self._state_machine.transition("SELECT_OUTPUT_TYPE")

        # Steps 2-5: Interaction loop
        while self._state_machine.state != "CONFIRM":
            step = self._state_machine.state
            if step == "SELECT_OUTPUT_TYPE":
                output_type = await self._get_user_choice(result["options"])
                result = await self._clarifier.select_output_type(output_type)
                self._state_machine.transition("SELECT_TEMPLATE")
            elif step == "SELECT_TEMPLATE":
                template = await self._get_user_choice(result["options"])
                result = await self._clarifier.select_template(template)
                self._state_machine.transition("CONFIGURE_SECTIONS")
            elif step == "CONFIGURE_SECTIONS":
                sections = await self._get_user_sections(result["sections"])
                self._state_machine.transition("SET_PARAMETERS")
            elif step == "SET_PARAMETERS":
                params = await self._get_user_parameters()
                result = await self._clarifier.set_parameters(params)
                self._state_machine.transition("CONFIRM")

        # Step 6: Final confirmation
        confirmed = await self._get_user_confirmation(result["summary"])
        if not confirmed:
            self._state_machine.back()
            return await self._research_interactive(user_input)

        # Step 7: Start execution
        requirement = await self._clarifier.confirm()
        self._state_machine.transition("EXECUTING")
        return await self._execute_research(requirement)
```

---

## 5. File Change Summary

### 5.1 Files to Delete

| File | Lines | Reason |
|------|-------|--------|
| `src/core/orchestrator/requirement_clarifier.py` | 281 | Functionality merged into SmartClarifier |

### 5.2 Files to Modify

| File | Change | Description |
|------|--------|-------------|
| `src/core/orchestrator/smart_clarifier.py` | Add Question/QuestionType, knowledge_bank integration | Merge from RequirementClarifier and ConversationManager |
| `src/core/dialogue/conversation_manager.py` | Simplify, remove redundant process_message | Remove process_message logic, keep knowledge_bank and state |
| `src/core/orchestrator/orchestrator.py` | Integrate interaction flow | research() integrates SmartClarifier and state machine |
| `src/core/dialogue/state_machine.py` | Add interaction states | Add SELECT_OUTPUT_TYPE, SELECT_TEMPLATE, etc. |

### 5.3 Final Architecture

```
User Input
  │
  ▼
ResearchOrchestrator.research()
  │
  ├─ [Interactive Mode]
  │    │
  │    ├─ SmartClarifier (Enhanced)
  │    │    ├─ start() → output type options
  │    │    ├─ select_output_type() → template options
  │    │    ├─ select_template() → section structure
  │    │    ├─ set_parameters() → research parameters
  │    │    └─ confirm() → complete requirement
  │    │
  │    └─ ConversationManager (Simplified)
  │         ├─ search_entities() → knowledge base
  │         └─ save/load state → persistence
  │
  └─ [Auto Mode]
       │
       └─ Direct execution with default parameters
            │
            ▼
       ExecutionEngine → Report Generation
```
