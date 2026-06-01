# Prompt Externalization Refactoring Plan

> Goal: Extract LLM prompts hardcoded in Python code to independent `.md` files,
> achieving separation of prompts and code. Change prompts without touching Python; non-developers can edit directly.
>
> Design Principles:
> 1. No new dependencies — Only use Python standard library + existing project dependencies (PyYAML already exists)
> 2. Plain text — `.md` files, `string.Template` for variable substitution
> 3. Don't change logic — Extract only plain text, keep condition branches/loops in Python
> 4. Interface unchanged — Existing API signatures unchanged, zero modification for callers
> 5. Progressive replacement — Migrate one by one, compare and verify output consistency

---

## 1. Current Status

There are 4 independent prompt construction chains in the codebase:

| Chain | Location | Content | Lines |
|------|------|------|------|
| A | `generic_agent.py` | 14 role definitions + 3 research prompts + 3 synthesis prompt variants | ~250 lines |
| B | `strategies.py` | Data collection/validation/analysis/synthesis(4 variants)/report, 5 phases | ~250 lines |
| C | `orchestrator.py` | body_agent + summary_agent + conclusion_agent system prompts | ~80 lines |
| D | `phase_prompts.py` | Structured PhasePromptTemplate, 5 phase templates, existing manager | ~160 lines |

Chain D already has a structured template system (`PhasePromptTemplate` dataclass + `PhasePrompts` manager),
but its prompt content is still distributed in hardcoded `_init_phase_prompts()`.

---

## 2. Target Architecture

### 2.1 Directory Structure

```
prompts/
├── _shared/                     # Shared fragments (cross-file references)
│   ├── writing_style.md         # Writing style specification
│   └── output_spec.md           # Output specification (format_rules)
│
├── agents/                      # Agent Profile = system_prompt + skills + config
│   ├── body_agent.md            # orchestrator body_agent
│   ├── executive_summary.md     # orchestrator summary_agent
│   ├── research_conclusion.md   # orchestrator conclusion_agent
│   ├── general.md               # orchestrator general fallback
│   ├── market_size.md           # Role: Market Size
│   ├── competition.md           # Role: Competitive Landscape
│   ├── trend.md                 # Role: Development Trends
│   ├── industry_chain.md        # Role: Industry Chain
│   ├── policy.md                # Role: Policy & Regulation
│   ├── technology.md            # Role: Technology Trends
│   ├── enterprise.md            # Role: Enterprise Analysis
│   ├── risk.md                  # Role: Risk Analysis
│   ├── investment.md            # Role: Investment Value
│   ├── executive_summary_role.md # Role: Executive Summary Writing
│   ├── conclusion_role.md       # Role: Research Conclusion Writing
│   ├── validation.md            # Role: Data Validation
│   ├── general_role.md          # Role: General Research
│   ├── conversation.md          # Phase 5: Research Interaction Dialogue Agent (from research_api.py)
│   ├── intent_analysis_system.md # Phase 5: Intent Analysis system prompt (from semantic_intent.py)
│   ├── intent_analysis_user.md  # Phase 5: Intent Analysis user prompt template
│   ├── section_analysis_system.md # Phase 5: Section Analysis system prompt (from task_structure.py)
│   └── section_analysis_user.md # Phase 5: Section Analysis user prompt template
│
├── tasks/                       # User prompt: current task definition (Chain A/B)
│   ├── research_with_data.md    # Research prompt with data
│   ├── basic_research.md        # Basic research without data
│   ├── synthesis_target.md      # Synthesis analysis — with target_aspect
│   ├── synthesis_aspect.md      # Synthesis analysis — with aspect without target
│   └── synthesis_default.md     # Synthesis analysis — no aspect no target
│
└── phases/                      # Phase templates (Chain D, PhasePromptTemplate format)
    ├── data_collection.md
    ├── data_validation.md
    ├── deep_analysis.md
    ├── synthesis.md
    └── report_generation.md
```

### 2.2 Agent Profile File Format (frontmatter + body)

```markdown
---
skills:
  required: [search_skill, llm_skill]
  optional: [file_skill]
---

You are a senior industry research analyst specializing in market quantitative analysis and sizing.

## Expertise
- Market Size Estimation (Top-down/Bottom-up)
- Growth Driver Decomposition

## Analysis Framework
1. Overall Assessment
2. Structure Analysis
```

Frontmatter uses YAML (project already has PyYAML dependency), body is plain text Markdown.

### 2.3 AgentProfile Data Structure

```python
@dataclass
class AgentProfile:
    name: str
    system_prompt: str               # Body → LLM system prompt
    required_skills: List[str]       # frontmatter.skills.required
    optional_skills: List[str]       # frontmatter.skills.optional
    config: Dict[str, Any]           # frontmatter.config
    
    @classmethod
    def from_md(cls, path: Path) -> "AgentProfile":
        content = path.read_text(encoding="utf-8")
        return cls.from_text(path.stem, content)
    
    @classmethod
    def from_text(cls, name: str, content: str) -> "AgentProfile":
        # Scan for --- delimiters line by line, support trailing spaces and empty frontmatter
        lines = content.split('\n')
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end = i
                    break
            if end is not None:
                fm_text = '\n'.join(lines[1:end])
                body = '\n'.join(lines[end+1:]).strip()
                try:
                    import yaml
                    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
                except yaml.YAMLError as e:
                    logger.warning(f"YAML frontmatter parse error: {e}")
                    fm = {}
                skills = fm.get("skills", {})
                return cls(name=name, system_prompt=body,
                    required_skills=skills.get("required", []),
                    optional_skills=skills.get("optional", []),
                    config=fm.get("config", {}))
        return cls(name=name, system_prompt=content.strip())
```

---

## 3. Variable Syntax

Use `string.Template` (Python standard library, zero dependency) instead of `str.format`:

| Scenario | Syntax | Description |
|------|------|------|
| Normal Variable | `$topic` or `${topic}` | Direct substitution |
| Default Variable | `safe_substitute()` doesn't throw | Keeps `$xxx` as-is |

**Why not `str.format`:** When `.md` files contain `{"key": "value"}` or `{` in code blocks,
`str.format` treats them as unclosed placeholders and crashes. `string.Template`'s `$` syntax has no conflict with `{}`.

---

## 4. Shared Fragment Reference Mechanism

Cross-file repeated writing style specifications are referenced via `{include:writing_style}` markers:

```markdown
## Data
${data_str}
---
{include:writing_style}
```

`prompts/_shared/writing_style.md`:
```markdown
1. Output analysis body directly, forbid any conversational prefixes
2. Each paragraph starts with a clear judgment sentence
3. Forbid adding source annotations within body text
4. Avoid colloquial expressions
```

`PromptManager.render()` parses `{include:xxx}` and replaces it with `_shared/xxx.md` content,
supports nesting, max depth 5 levels to prevent infinite recursion.

---

## 5. PromptManager

```python
"""src/core/prompt_manager.py"""
import re, logging
from pathlib import Path
from string import Template
from threading import Lock
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class AgentProfile:
    def __init__(self, name: str, system_prompt: str,
                 required_skills=None, optional_skills=None, config=None):
        self.name = name
        self.system_prompt = system_prompt
        self.required_skills = required_skills or []
        self.optional_skills = optional_skills or []
        self.config = config or {}
    
    @classmethod
    def from_md(cls, path: Path) -> "AgentProfile":
        return cls.from_text(path.stem, path.read_text(encoding="utf-8"))
    
    @classmethod
    def from_text(cls, name: str, content: str) -> "AgentProfile":
        lines = content.split('\n')
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---': end = i; break
            if end is not None:
                fm_text = '\n'.join(lines[1:end])
                body = '\n'.join(lines[end+1:]).strip()
                try:
                    import yaml
                    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
                except yaml.YAMLError:
                    fm = {}
                skills = fm.get("skills", {})
                return cls(name=name, system_prompt=body,
                    required_skills=skills.get("required", []),
                    optional_skills=skills.get("optional", []),
                    config=fm.get("config", {}))
        return cls(name=name, system_prompt=content.strip())


class PromptManager:
    def __init__(self, base_dir: str = "prompts"):
        self._base_dir = Path(base_dir)
        self._cache: Dict[str, str] = {}
        self._lock = Lock()
    
    def load(self, category: str, name: str) -> str:
        key = f"{category}/{name}"
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        path = self._base_dir / category / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        content = path.read_text(encoding="utf-8")
        with self._lock:
            if key not in self._cache:
                self._cache[key] = content
        return content
    
    def render(self, category: str, name: str, strip_frontmatter=False, **variables) -> str:
        return self._render_with_includes(category, name, 0, strip_frontmatter, **variables)
    
    def _render_with_includes(self, category, name, depth, strip_frontmatter=False, **variables):
        if depth > 5:
            raise RuntimeError(f"Prompt include recursion too deep: {name}")
        template = self.load(category, name)
        if strip_frontmatter:
            template = re.sub(r'^---\n.*?\n---\n', '', template, flags=re.DOTALL)
        template = re.sub(
            r'\{include:(\w+)\}',
            lambda m: self._render_with_includes("_shared", m.group(1), depth + 1),
            template
        )
        result = Template(template).safe_substitute(**variables)
        unresolved = re.findall(r'\$[a-zA-Z_]\w*|\$\{[a-zA-Z_]\w*\}', result)
        if unresolved:
            logger.warning(f"Unresolved variables in {category}/{name}: {unresolved}")
        return result
    
    def load_profile(self, name: str) -> AgentProfile:
        return AgentProfile.from_text(name, self.load("agents", name))
    
    def load_profile_system_prompt(self, name: str) -> str:
        return self.load_profile(name).system_prompt
    
    def invalidate(self, key: Optional[str] = None):
        with self._lock:
            if key: self._cache.pop(key, None)
            else: self._cache.clear()
```

---

## 6. Migration Approach for Each Chain

### Chain A + C: generic_agent.py + orchestrator.py

```python
# Before
def _get_professional_role_prompt(self, aspect):
    role_map = {"market_size": "You are a...", ...}
    format_rules = "\n\n## Output Spec\n..."
    return role_map.get(aspect, default) + format_rules

# After (load from Agent Profile)
def _get_professional_role_prompt(self, aspect):
    pm = PromptManager()
    try:
        profile = pm.load_profile(aspect)
    except FileNotFoundError:
        if "size" in aspect:
            profile = pm.load_profile("market_size")
        elif "competition" in aspect:
            profile = pm.load_profile("competition")
        else:
            profile = pm.load_profile("general_role")
    spec = pm.render("_shared", "output_spec")
    return profile.system_prompt + "\n\n" + spec
```

### Chain B: strategies.py

```python
# Before
system_prompt = self._build_data_collection_prompt(topic, aspect, ...)
# After
pm = PromptManager()
system_prompt = pm.render("phases", "data_collection",
    topic=topic, aspect=aspect, ...)
```

### Chain D: phase_prompts.py

`_init_phase_prompts()` changed to load from `prompts/phases/` directory:

```python
def _init_phase_prompts():
    global PHASE_PROMPTS
    pm = PromptManager()
    phases = ["data_collection", "data_validation", "deep_analysis",
              "synthesis", "report_generation"]
    for phase in phases:
        try:
            content = pm.load("phases", phase)
            PHASE_PROMPTS[phase] = _parse_phase_md(content, phase)
        except Exception as e:
            logger.error(f"Failed to load phase prompt {phase}: {e}")
```

---

## 7. _parse_phase_md Parsing Rules

```python
def _parse_phase_md(content: str, phase: str) -> PhasePromptTemplate:
    sections = re.split(r'\n## ', content)
    
    if len(sections) == 1 and '\n## ' not in content:
        logger.error(f"No ## headers in {phase}")
        return PhasePromptTemplate(phase=phase)
    
    intro = sections[0].strip() if sections else ''
    if intro and not intro.startswith('#'):
        logger.warning(f"Text before first ## in {phase} discarded: {intro[:60]}")
    
    fields = {"phase": phase}
    for section in sections:
        if '\n' not in section:
            continue
        key, _, value = section.partition('\n')
        key = key.strip().lower()
        key = key.lstrip('#').strip()
        key = key.replace(' ', '_').replace('-', '_')
        value = value.strip()
        
        if key == "instructions":
            fields["instructions"] = [
                i.strip().lstrip("- ") for i in value.split('\n') if i.strip().startswith("- ")
            ]
        elif key == "output_schema":
            import json
            json_match = re.search(r'```json\s*(.*?)\s*```', value, re.DOTALL)
            if json_match:
                fields["output_schema"] = json.loads(json_match.group(1))
            elif value.strip():
                try: fields["output_schema"] = json.loads(value)
                except json.JSONDecodeError: fields["output_schema"] = {}
            else: fields["output_schema"] = {}
        elif key == "frameworks":
            raw = [i.strip().lstrip("- ").upper().replace("-", "_")
                   for i in value.split('\n') if i.strip().startswith("- ")]
            fields["frameworks"] = [PromptFramework[f] for f in raw if f in PromptFramework.__members__]
        elif key == "examples":
            import json
            json_match = re.search(r'```json\s*(.*?)\s*```', value, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
                fields["examples"] = parsed if isinstance(parsed, list) else [parsed]
            else: fields["examples"] = []
        elif key in ("role_definition", "goal_template"):
            fields[key] = value
    
    fields.setdefault("instructions", [])
    fields.setdefault("output_schema", {})
    fields.setdefault("examples", [])
    fields.setdefault("frameworks", [])
    return PhasePromptTemplate(**fields)
```

---

## 8. Compatibility Modifications

### 8.1 PhasePromptTemplate.render()

Change `str.format` to `string.Template`:

```python
# Before
goal = self.goal_template.format(topic=topic, aspect=aspect)
# After
goal = Template(self.goal_template).safe_substitute(topic=topic, aspect=aspect)
```

Caller API unchanged.

### 8.2 Frameworks Defense

```python
fields["frameworks"] = [PromptFramework[f] for f in raw if f in PromptFramework.__members__]
```

Unknown frameworks are simply skipped, no string retention.

### 8.3 Variable Scope

`_render_with_includes()` does not pass `variables` to includes, all variables are uniformly replaced by the outer `safe_substitute()`. This is intentional by design.

### 8.4 $ Syntax Safety

`string.Template` only recognizes `$` + valid Python identifier (`[a-zA-Z_][a-zA-Z0-9_]*`).
`$10B`, `$100M` - `$1` followed by a digit is not a valid identifier, `safe_substitute` keeps as-is. LaTeX `$x^2$` similarly. No escaping needed.

---

## 9. Verification Strategy

```python
def test_prompt_migration():
    old = old_renderer(...)  # Hardcoded version
    new = PromptManager().render(...)  # File version
    if old != new:
        import difflib
        diff = '\n'.join(difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile="old", tofile="new", lineterm=""
        ))
        raise AssertionError(f"Difference:\n{diff}")
```

| Check Item | Pass Criteria |
|--------|---------|
| Render output diff | Character-by-character identical |
| Variable integrity | Check for `$` residues |
| Include working | Content correctly embedded |
| Agent Profile fields | Skills, config correctly parsed |

---

## 10. Implementation Steps

### Phase 0: Infrastructure
1. Create `prompts/{_shared,agents,tasks,phases}/` directories
2. Implement `PromptManager` + `AgentProfile` + `_parse_phase_md`
3. Unit tests

### Phase 1: Chain D (phase_prompts.py)
1. Write 5 phase .md files
2. Modify `_init_phase_prompts()` to load from files
3. Verify output consistency

### Phase 2: Chain C (orchestrator.py)
1. Write 4 agent .md files (with frontmatter skills)
2. Replace system_prompt f-strings
3. Verify output consistency

### Phase 3: Chain A (generic_agent.py)
1. Write 14 role .md files + 5 task .md files
2. Replace role_map and `_build_*` methods
3. Verify output consistency

### Phase 4: Chain B (strategies.py)
1. Write remaining templates
2. Replace `_build_*_prompt()` methods
3. Verify output consistency

### Phase 5: Dialogue + Intent Analysis + Section Analysis Prompts (Already Completed ✅)

Externalize remaining hardcoded prompts in `research_api.py`, `semantic_intent.py`, `task_structure.py`.

**Target Files:**

| Original Location | Migrated To | Description |
|--------|--------|------|
| `research_api.py` → `CONVERSATION_SYSTEM_PROMPT` | `prompts/agents/conversation.md` | With AgentProfile frontmatter |
| `semantic_intent.py` → `INTENT_ANALYSIS_*` | `prompts/agents/intent_analysis_system.md` + `intent_analysis_user.md` | system + user separated |
| `task_structure.py` → `SECTION_ANALYSIS_*` | `prompts/agents/section_analysis_system.md` + `section_analysis_user.md` | system + user separated |

**Cleanup Content:**

| Module | Lines Cleaned |
|------|---------|
| `research_api.py` | ~50 lines (CONVERSATION_SYSTEM_PROMPT) |
| `semantic_intent.py` | ~22 lines (INTENT_ANALYSIS_*_PROMPT) |
| `task_structure.py` | ~24 lines (SECTION_ANALYSIS_*_PROMPT) |
| `conversation_manager.py` | 234 lines (dead code, deleted) |

---

## 11. Cleanup Plan

| Phase | Cleanup Content | Lines |
|-------|---------|------|
| 1 | Delete `_init_phase_prompts()` hardcoding, replace with file loading | ~170 lines |
| 2 | Delete 4 system_prompt f-strings in orchestrator.py | ~80 lines |
| 3 | Delete role_map + format_rules + 4 f-strings in generic_agent.py | ~300 lines |
| 4 | Delete 6 `_build_*_prompt()` methods in strategies.py | ~250 lines |
| 5 | Delete hardcoding in research_api.py / semantic_intent.py / task_structure.py | ~96 lines |
| 5b | Delete dialogue/conversation_manager.py dead code | ~234 lines |

---

## 12. Unchanged Parts

| Module | Keep As-Is |
|------|---------|
| `PhasePromptTemplate` dataclass | Interface unchanged |
| `PhasePrompts` manager | `get_prompt()` API unchanged |
| `generic_agent.py` `_build_*` logic code | Condition branches, loops |
| `orchestrator.py` Agent creation logic | `_create_agents()` structure |
| `content_quality.py` regex filters | Not prompts |
| `skills/` skill prompts | Already independent modules |
| `config/agents.yaml` | Non-prompt configuration, don't touch |
