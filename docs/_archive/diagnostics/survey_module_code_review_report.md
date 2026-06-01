# Survey Module Code Review Report

> Generated: 2026-05-03
> Scope: Survey Module Core Code
> Reviewer: AI Code Auditor

---

## Review Summary

| Item | Details |
|------|------|
| Scope | Survey Module Core Code |
| Files Reviewed | 6 core files |
| Total Lines | ~3000 lines |
| Issues Found | 23 |

### Reviewed Files

| File | Path | Lines |
|------|------|------|
| tencent_survey.py | src/survey/backends/ | 442 |
| survey_skill.py | src/skills/builtin/ | 260 |
| survey_integration_agent.py | src/agents/fixed_agents/ | 1017 |
| survey_analysis_agent.py | src/agents/fixed_agents/ | 798 |
| survey_optimization_agent.py | src/agents/fixed_agents/ | 391 |
| questionnaire_word.html | config/document_templates/ | 268 |

---

## Critical Issues (P0 - Immediate Fix Required)

### Issue 1: Escape Character Syntax Error (survey_integration_agent.py:574-577)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 574-577

**Description**:
The string uses incorrect escape single quotes `\'`, which are unnecessary in Python strings and may cause syntax parsing issues.

**Problem Code**:
```python
# Lines 574-577
if hasattr(self, \'_message_bus\') and self._message_bus:
    self._analysis_agent.set_message_bus(self._message_bus)
if hasattr(self, \'_shared_memory\') and self._shared_memory:
    self._analysis_agent.set_shared_memory(self._shared_memory)
```

**Impact**: Code cannot execute normally, will cause `SyntaxError` or runtime errors.

**Suggested Fix**:
```python
if hasattr(self, '_message_bus') and self._message_bus:
    self._analysis_agent.set_message_bus(self._message_bus)
if hasattr(self, '_shared_memory') and self._shared_memory:
    self._analysis_agent.set_shared_memory(self._shared_memory)
```

---

### Issue 2: Escape Character Error - Persona Handling (survey_integration_agent.py:683-714)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 683, 712-714

**Description**:
Multiple `\'` escape errors exist in persona object handling.

**Problem Code**:
```python
# Line 683
if hasattr(persona, \'__dict__\'):
    persona_dict = persona.__dict__
```

**Impact**: Code logic cannot execute normally, `hasattr` check will fail.

**Suggested Fix**:
```python
if hasattr(persona, '__dict__'):
    persona_dict = persona.__dict__
```

---

### Issue 3: Escape Character Error - Config Loading (survey_integration_agent.py:823)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 823

**Description**:
Escape character error in config loading.

**Problem Code**:
```python
# Line 823
settings = SystemSettings.from_yaml() if hasattr(SystemSettings, \'from_yaml\') else SystemSettings()
```

**Impact**: Condition check fails, may cause config loading exception.

**Suggested Fix**:
```python
settings = SystemSettings.from_yaml() if hasattr(SystemSettings, 'from_yaml') else SystemSettings()
```

---

## Medium Issues (P1 - Fix This Week)

### Issue 4: Async Method Definition Error (survey_optimization_agent.py:167-196)

**File**: `src/agents/fixed_agents/survey_optimization_agent.py`
**Line**: 167-196

**Description**:
`_analyze_questions` is defined as `async def`, but the method has no `await` statements inside - this is a synchronous method incorrectly marked as async.

**Problem Code**:
```python
async def _analyze_questions(
    self, 
    questions: List[Dict], 
    goals: List[str]
) -> Dict[str, Any]:
    """Analyze questions."""
    analysis = {
        "total_questions": len(questions),
        "question_types": {},
        "average_length": 0,
        "goals_addressed": goals,
    }
    # ... all synchronous code, no await
    return analysis
```

**Impact**: Unnecessary async overhead, may cause performance issues.

**Suggested Fix**:
```python
def _analyze_questions(  # Remove async
    self, 
    questions: List[Dict], 
    goals: List[str]
) -> Dict[str, Any]:
    """Analyze questions."""
    # ... keep original logic
```

---

### Issue 5: Method Signature Mismatch - _generate_suggestions (survey_optimization_agent.py)

**File**: `src/agents/fixed_agents/survey_optimization_agent.py`
**Line**: 137, 241-279

**Description**:
`_generate_suggestions` method defines 4 parameters, but only 1 parameter (analysis) is passed at line 137.

**Call Site Code**:
```python
# Line 137
suggestions = self._generate_suggestions(analysis)
```

**Method Definition**:
```python
# Line 241
async def _generate_suggestions(
    self,
    questions: List[Dict],      # Not passed
    issues: List[Dict],          # Not passed  
    goals: List[str],            # Not passed
    target_audience: Optional[str]  # Not passed
) -> List[Dict]:
```

**Impact**: Will throw `TypeError: missing required positional arguments` at runtime.

**Suggested Fix**:
Option 1 - Modify call site:
```python
issues = self._identify_issues(questions)
suggestions = self._generate_suggestions(questions, issues, optimization_goals, target_audience)
```

Option 2 - Modify method signature to match actual call:
```python
def _generate_suggestions(
    self,
    analysis: Dict[str, Any],
    issues: Optional[List[Dict]] = None,
    goals: Optional[List[str]] = None,
    target_audience: Optional[str] = None
) -> List[Dict]:
```

---

### Issue 6: Method Name Mismatch - _apply_optimizations (survey_optimization_agent.py)

**File**: `src/agents/fixed_agents/survey_optimization_agent.py`
**Line**: 140, 281-306

**Description**:
Calling `_apply_optimizations` method, but the actual defined method name is `_optimize_questions`.

**Call Site Code**:
```python
# Line 140
optimized_questions = self._apply_optimizations(questions, suggestions)
```

**Method Definition**:
```python
# Line 281
async def _optimize_questions(  # Method name mismatch
    self,
    questions: List[Dict],
    suggestions: List[Dict]
) -> List[Dict]:
```

**Impact**: Will throw `AttributeError: 'SurveyOptimizationAgent' object has no attribute '_apply_optimizations'` at runtime.

**Suggested Fix**:
Unify method name, rename `_optimize_questions` to `_apply_optimizations`.

---

### Issue 7: Duplicate Method Definition (survey_analysis_agent.py:90-157, 201-232)

**File**: `src/agents/fixed_agents/survey_analysis_agent.py`
**Line**: 90-157, 201-232

**Description**:
`execute_async` method is almost functionally identical to `execute` method, code redundancy.

**Problem Code**:
```python
# Line 90 - execute method
async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
    responses = task_input["responses"]
    questions = task_input["questions"]
    # ...

# Line 201 - execute_async method, nearly identical content
async def execute_async(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
    responses = task_input["responses"]
    questions = task_input["questions"]
    # ...
```

**Impact**: Code maintenance difficulty, prone to inconsistency.

**Suggested Fix**:
Delete `execute_async` method, or have it call `execute`:
```python
async def execute_async(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute survey analysis asynchronously."""
    return await self.execute(task_input)
```

---

### Issue 8: Legacy Method ID Generation Inconsistency (survey_integration_agent.py:402-427)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 402-427

**Description**:
Legacy workflow method internally regenerates survey_id and task_id, may be inconsistent with main flow.

**Problem Code**:
```python
async def _full_survey_workflow(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
    """Full survey workflow (legacy interface)"""
    return await self._third_party_workflow(
        task_input,
        f"survey_{uuid.uuid4().hex[:8]}",  # Newly generated ID
        f"task_{uuid.uuid4().hex[:8]}",
    )
```

**Impact**: May cause ID inconsistency, affecting data tracking.

**Suggested Fix**:
Remove these legacy methods, or generate IDs uniformly at the `execute` method entry point.

---

## Low Priority Issues (P2 - Deferrable)

### Issue 9: Config Field Mapping Unreasonable (tencent_survey.py:424-426)

**File**: `src/survey/backends/tencent_survey.py`
**Line**: 424-426

**Description**:
`webhook` field forcibly converted to `org_id`, logic is unreasonable; `user_id` hardcoded to 0.

**Problem Code**:
```python
return TencentSurveyConfig(
    appid=platform_config.app_id,
    secret=platform_config.app_secret,
    access_token=platform_config.secret,
    org_id=int(platform_config.webhook) if platform_config.webhook.isdigit() else 0,
    user_id=0,  # Hardcoded to 0
    base_url=platform_config.api_url or "https://wj.qq.com/api",
)
```

**Impact**: Config mapping logic may be incorrect, causing API call failures.

**Suggested Fix**:
Add dedicated config fields `org_id` and `user_id`, or add config mapping comment documentation.

---

### Issue 10: Temporary Object Creation Non-standard (survey_skill.py:185-193)

**File**: `src/skills/builtin/survey_skill.py`
**Line**: 185-193

**Description**:
When creating temporary `SurveyTask` object, many fields are empty or default values.

**Problem Code**:
```python
task = SurveyTask(
    task_id=task_id,
    survey_id="",      # Empty string
    backend_type=self.default_backend_type,
    status=SurveyStatus.ACTIVE,
    config=None,       # None
    target_count=0     # 0
)
```

**Impact**: May cause subsequent processing errors or incomplete data.

**Suggested Fix**:
Load complete task info from storage layer, or add parameter validation.

---

### Issue 11: Hardcoded English Question Templates (survey_integration_agent.py:587-617)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 587-617

**Description**:
Question templates in `_auto_generate_questions` method are hardcoded in English, not supporting Chinese.

**Problem Code**:
```python
base_questions = [
    {
        "question_id": "q1",
        "text": f"What is your overall view on {topic}?",  # Hardcoded English
        "question_type": "single_choice",
        "options": [
            {"option_id": "opt1", "text": "Very Satisfied", "value": 5},
            # ...
        ]
    },
    # ...
]
```

**Impact**: Does not support Chinese survey generation, poor user experience.

**Suggested Fix**:
Add language parameter, or use internationalization configuration:
```python
def _auto_generate_questions(self, topic: str, language: str = "zh") -> List[Dict]:
    if language == "zh":
        base_questions = [
            {
                "question_id": "q1",
                "text": f"What is your overall view on {topic}?",
                # ...
            }
        ]
```

---

### Issue 12: t-value Lookup Table Incomplete (survey_analysis_agent.py:318-348)

**File**: `src/agents/fixed_agents/survey_analysis_agent.py`
**Line**: 318-348

**Description**:
`_get_t_value` method only implements a simplified t-value lookup table, and the interpolation formula is inaccurate.

**Problem Code**:
```python
# Linear interpolation over-simplified
return 2.0 + (30 - df) * 0.01  # Simplified approximation
```

**Impact**: Statistical results may not be sufficiently precise.

**Suggested Fix**:
Use `scipy.stats.t` for precise calculation, or improve lookup table data:
```python
from scipy import stats

def _get_t_value(self, df: int, alpha: float = 0.05) -> float:
    return stats.t.ppf(1 - alpha/2, df)
```

---

### Issue 13: Issue Detection Templates Only Support English (survey_optimization_agent.py:60-81)

**File**: `src/agents/fixed_agents/survey_optimization_agent.py`
**Line**: 60-81

**Description**:
`patterns` list in `ISSUE_TEMPLATES` is too simple and only supports English.

**Problem Code**:
```python
ISSUE_TEMPLATES = {
    "ambiguous": {
        "name": "Ambiguous question",
        "patterns": ["is it good", "how about", "how much", "often"],  # English only
        "suggestion": "Question phrasing is too vague, suggest making it more specific"
    },
    # ...
}
```

**Impact**: Cannot detect issues in Chinese surveys.

**Suggested Fix**:
Add Chinese question detection patterns:
```python
ISSUE_TEMPLATES = {
    "ambiguous": {
        "name": "Ambiguous question",
        "patterns": [
            "is it good", "how about", "how much", "often",
            "how is it", "what about", "how many", "frequently"
        ],
        "suggestion": "Question phrasing is too vague, suggest making it more specific"
    },
    # ...
}
```

---

### Issue 14: Font Definition Compatibility Issues (questionnaire_word.html:15)

**File**: `config/document_templates/questionnaire_word.html`
**Line**: 15, 33

**Description**:
Font definitions use `SimSun` and `SimHei`, which are Windows-specific fonts.

**Problem Code**:
```css
body {
    font-family: 'SimSun', 'Microsoft YaHei', serif;
}

.cover h1 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
}
```

**Impact**: May not display Chinese fonts correctly on non-Windows systems (Linux, macOS).

**Suggested Fix**:
Add cross-platform font fallback:
```css
body {
    font-family: 'SimSun', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', serif;
}

.cover h1 {
    font-family: 'SimHei', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', sans-serif;
}
```

---

### Issue 15: Synchronous Method Called in Async Context (survey_integration_agent.py:866-871)

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Line**: 866-871

**Description**:
`transform_to_html` is a synchronous method called directly in an async method, potentially blocking the event loop.

**Problem Code**:
```python
html = orchestrator.transform_to_html(  # Synchronous method
    research_result=template_vars,
    output_format="docx",
    template_name="questionnaire_word",
)
```

**Impact**: May block the event loop, affecting concurrent performance.

**Suggested Fix**:
Use `asyncio.to_thread` to wrap the synchronous call:
```python
html = await asyncio.to_thread(
    orchestrator.transform_to_html,
    research_result=template_vars,
    output_format="docx",
    template_name="questionnaire_word",
)
```

---

## Code Style Issues

### Issue 16: Docstring Language Inconsistency

**Files Involved**: All files

**Description**:
Some docstrings use English, some use Chinese - inconsistent.

**Examples**:
```python
# tencent_survey.py - English
"""Tencent Survey API Backend Implementation."""

# survey_analysis_agent.py - English
"""Survey Analysis Agent."""
```

**Suggested Fix**:
Use consistent language for docstrings.

---

### Issue 17-19: Type Annotations Using Python 3.10+ Syntax

**Files Involved**:
- `survey_integration_agent.py:130`
- `survey_analysis_agent.py:76`
- `survey_optimization_agent.py:95`

**Description**:
Uses `tuple[bool, str]` instead of `Tuple[bool, str]`, requires Python 3.10+.

**Problem Code**:
```python
def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
```

**Impact**: Will error on Python 3.9 and below.

**Suggested Fix**:
```python
from typing import Tuple

def validate_input(self, task_input: Dict[str, Any]) -> Tuple[bool, str]:
```

Or explicitly require Python 3.10+ in `pyproject.toml`.

---

### Issue 20: Missing Unit Test Coverage

**Files Involved**: Test files

**Description**:
Some core methods lack unit tests, especially error handling paths.

**Suggested Fix**:
Add unit tests for the following methods:
- `survey_integration_agent._save_responses_to_db`
- `survey_analysis_agent._generate_charts`
- `survey_optimization_agent._get_llm_suggestions`

---

### Issue 21: Overly Broad Type Definitions

**Files Involved**: All files

**Description**:
Multiple uses of `Dict[str, Any]` are too broad, reducing type checking effectiveness.

**Suggested Fix**:
Use more specific types or define TypedDict:
```python
from typing import TypedDict

class QuestionDict(TypedDict):
    question_id: str
    text: str
    question_type: str
    options: Optional[List[Dict[str, Any]]]
    required: bool
```

---

### Issue 22: Incomplete Exception Handling

**Files Involved**: All files

**Description**:
Multiple `except Exception` catches only log, without appropriate recovery or retry mechanisms.

**Example**:
```python
except Exception as e:
    logger.error(f"Failed to save task to database: {e}")
    # No retry or recovery
```

**Suggested Fix**:
Add retry mechanism or re-raise exception:
```python
except Exception as e:
    logger.error(f"Failed to save task to database: {e}")
    raise  # Re-raise for caller to handle
```

---

### Issue 23: Log Language Inconsistency

**Files Involved**: All files

**Description**:
Mixed Chinese and English in log messages, suggest unification.

**Examples**:
```python
logger.info(f"Task saved to database: {task_id}")  # English
logger.info(f"Successfully created Tencent Survey backend from config system")  # English
```

**Suggested Fix**:
Use consistent language for log messages.

---

## Issue Statistics

### By Priority

| Priority | Count | Percentage |
|--------|------|------|
| P0 (Critical) | 3 | 13% |
| P1 (Medium) | 5 | 22% |
| P2 (Low) | 9 | 39% |
| Code Style | 6 | 26% |
| **Total** | **23** | **100%** |

### By File

| File | Issue Count |
|------|--------|
| survey_integration_agent.py | 8 |
| survey_optimization_agent.py | 4 |
| survey_analysis_agent.py | 3 |
| tencent_survey.py | 1 |
| survey_skill.py | 1 |
| questionnaire_word.html | 1 |
| Multi-file General | 5 |

### By Issue Type

| Type | Count |
|------|------|
| Syntax Errors | 3 |
| Method Signature Mismatch | 3 |
| Code Redundancy | 2 |
| Type Issues | 3 |
| Internationalization Issues | 2 |
| Configuration Issues | 2 |
| Compatibility Issues | 2 |
| Other | 6 |

---

## Fix Priority Recommendations

### Phase 1: Immediate Fix (Today)

1. **Issues 1-3**: Escape Character Errors
   - These issues will prevent code from running
   - Small fix effort, large impact

### Phase 2: Fix This Week

2. **Issues 4-8**: Method Signature and Definition Issues
   - These issues will cause runtime errors
   - Requires careful call chain review

### Phase 3: Subsequent Iterations

3. **Issues 9-15**: Feature Improvements
   - Improve code quality and user experience
   - Can be gradually optimized

4. **Issues 16-23**: Code Style
   - Unify code standards
   - Improve maintainability

---

## Appendix

### A. Related File Paths

```
E:\market_report_systerm\
├── src\
│   ├── survey\
│   │   └── backends\
│   │       └── tencent_survey.py
│   ├── skills\
│   │   └── builtin\
│   │       └── survey_skill.py
│   └── agents\
│       └── fixed_agents\
│           ├── survey_integration_agent.py
│           ├── survey_analysis_agent.py
│           └── survey_optimization_agent.py
└── config\
    └── document_templates\
        └── questionnaire_word.html
```

### B. References

- [Python Async Best Practices](https://docs.python.org/3/library/asyncio.html)
- [Type Annotation Guide](https://docs.python.org/3/library/typing.html)
- [Survey Design Best Practices](https://www.wj.qq.com/docs/openapi/)

---

*End of Report*
