# Search Keyword Dynamic Expansion System Design

> Version: v2.0
> Date: 2026-04-29
> Status: Pending Review
>
> Change History:
> - v1.0: Initial plan. SmartKeywordGenerator + MissingDataAnalyzer + LLMSkill
> - v1.1: Fixed "fully LLM-dependent" contradiction, changed to hybrid plan; MissingDataAnalyzer uses LLM
> - v2.0: Architecture restructured. Removed SmartKeywordGenerator/MissingDataAnalyzer, changed to Agent._call_llm_directly()

---

## 1. Problem Analysis

### 1.1 Core Problem

Current search keyword expansion has a serious **hardcoding problem**, leading to:

1. **Keyword Exhaustion**: After hardcoded keywords are used up, cannot dynamically generate new ones
2. **Domain Limitation**: Cannot adapt to new research domains
3. **Quality Stagnation**: When search quality doesn't meet standards, cannot intelligently expand

### 1.2 Problem Identification

| Problem | Location | Impact |
|------|------|------|
| **LLM keyword generation not used** | `generic_agent.py:1255-1329` | `_generate_smart_queries_with_llm()` exists but never called |
| **Supplementary queries hardcoded** | `generic_agent.py:1065-1159` | Keyword matching + template string concatenation, cannot adapt to new domains |
| **Prompt hardcoded** | `generic_agent.py:1284` | Hardcoded "industry research expert", doesn't match other domains |

### 1.3 Research Domain Classification

Research types supported by the system are passed through `RequirementAnalysisAgent`, including market research, investment research, policy analysis, competitive analysis, technology research, industry analysis, etc.

---

## 2. Design Principles

### 2.1 Core Principles

1. **Agent calls LLM itself**: Don't rely on LLMSkill, avoid responsibility confusion
2. **Role template + LLM dynamic expansion**: Preset roles provide domain context, LLM generates specific keywords
3. **Quality-driven**: Trigger LLM expansion when search quality stagnates
4. **Cost control**: Limit LLM call count per task
5. **Bilingual support**: All templates support both Chinese and English

### 2.2 Solution Positioning

This solution is a hybrid of "role templates + Agent internal LLM calls":

```
LLMSkill → Fallback content generation on search failure (single responsibility)
Agent._call_llm_directly() → Keyword expansion (independent capability)
```

Two responsibilities separated, avoiding output pollution from LLMSkill doing both keyword expansion and content generation.

### 2.3 Key Problem Solutions

| Problem | Solution |
|------|----------|
| Preset keywords only in Chinese | All templates also have English versions |
| Search count vs keyword count mismatch | LLM generates enough keywords (min_queries x 1.5) |
| Infinite loop risk | Added max search limit (MAX_QUERIES) |
| Hardcoded fallback contradicts flexibility | Accept current data when LLM expansion fails |

---

## 3. System Architecture

### 3.1 Overall Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Search Keyword Dynamic Expansion System             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Requirements │───▶│ Search Exec  │───▶│ Quality Eval │      │
│  │ Phase        │    │ Phase        │    │ Phase        │      │
│  │              │    │              │    │              │      │
│  │ Type Identify│    │ Initial Query│    │ Score Calc   │      │
│  │ Domain Infer │    │ LLM Expand   │    │ Stagnation   │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                  │              │
│                      ┌───────────────────────────┘              │
│                      │                                         │
│                      ▼                                         │
│              ┌───────────────┐                                 │
│              │ Stagnant &    │                                 │
│              │ Under Limit   │                                 │
│              └───────┬───────┘                                 │
│                      │ YES                                      │
│                      ▼                                         │
│              ┌──────────────────────────────┐                   │
│              │ GenericAgent._call_llm       │                   │
│              │   _directly()                │                   │
│              │     ↓                         │                   │
│              │   _generate_smart_queries     │                   │
│              │   _with_llm()                 │                   │
│              └──────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Core Components

#### 3.2.1 DomainRoleInferrer

**Supports bilingual**: All templates include both Chinese and English versions.

```python
class DomainRoleInferrer:
    """Domain role inference based on research type (bilingual support)"""

    ROLE_TEMPLATES = {
        "market_research": {
            "role": {
                "zh": "Senior Market Research Analyst",
                "en": "Senior Market Research Analyst",
            },
            "expertise": {
                "zh": ["Quantitative Market Analysis", "Market Sizing", "Competitive Landscape", "Consumer Insights"],
                "en": ["Quantitative Market Analysis", "Market Sizing", "Competitive Landscape", "Consumer Insights"],
            },
            "data_focus": {
                "zh": ["market size", "growth rate", "market share", "consumer data"],
                "en": ["market size", "growth rate", "market share", "consumer data"],
            },
        },
        "investment": {
            "role": {
                "zh": "Senior Investment Analyst",
                "en": "Senior Investment Analyst",
            },
            "expertise": {
                "zh": ["Financial Analysis", "Valuation Modeling", "Risk Assessment", "ROI Analysis"],
                "en": ["Financial Analysis", "Valuation Modeling", "Risk Assessment", "ROI Analysis"],
            },
            "data_focus": {
                "zh": ["financial data", "valuation metrics", "funding news", "investment cases"],
                "en": ["financial data", "valuation metrics", "funding news", "investment cases"],
            },
        },
        # ... other templates follow same pattern
    }

    def infer(self, research_type: str, topic: str, language: str = "zh") -> Dict[str, Any]:
        template = self.ROLE_TEMPLATES.get(research_type, self.ROLE_TEMPLATES["market_research"])
        return {
            "role": template["role"].get(language, template["role"]["zh"]),
            "expertise": template["expertise"].get(language, template["expertise"]["zh"]),
            "data_focus": template["data_focus"].get(language, template["data_focus"]["zh"]),
        }
```

#### 3.2.2 GenericAgent._call_llm_directly()

Agent directly calls LLM capability, bypassing LLMSkill.

```python
class GenericAgent:

    async def _call_llm_directly(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Agent calls LLM directly (independent of LLMSkill).
        Used for Agent internal capabilities like keyword expansion, decision support.
        """
        from openai import AsyncOpenAI
        from src.config import settings

        try:
            client = AsyncOpenAI(
                api_key=settings.llm.api_key,
                base_url=settings.llm.base_url,
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            model = settings.llm.cheap_model or settings.llm.model
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return {"success": True, "content": content}

        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: LLM call failed: {e}")
            return {"success": False, "content": "", "error": str(e)}
```

#### 3.2.3 GenericAgent._generate_smart_queries_with_llm()

**Modify existing method**: Change parameter from `llm_skill` to using Agent's internal `_call_llm_directly()`.

```python
async def _generate_smart_queries_with_llm(
    self,
    topic: str,
    aspect: str,
    existing_queries: Optional[List[str]] = None,
    role_info: Optional[Dict] = None,  # New parameter
) -> List[str]:
    """
    Use LLM to intelligently generate search keywords (Agent internal capability).
    Search for raw data, not existing reports or analysis conclusions.
    
    **Change Notes**:
    - Removed llm_skill parameter, now uses Agent's internal _call_llm_directly()
    - Added role_info parameter to receive DomainRoleInferrer's inferred role info
    """
    if not role_info:
        role_info = {
            "role": "Senior Research Analyst",
            "expertise": ["Data Analysis", "Information Collection"],
            "data_focus": ["Data", "Statistics", "News"],
        }

    prompt = f"""You are a {role_info['role']} specializing in {topic} research.

## Research Task
- Topic: {topic}
- Dimension: {aspect or 'Comprehensive Analysis'}

## Your Expertise
{chr(10).join(f'- {e}' for e in role_info['expertise'])}

## Data Types to Focus On
{chr(10).join(f'- {d}' for d in role_info['data_focus'])}

## Already Used Search Terms (Do Not Repeat)
{chr(10).join(f'- {q}' for q in (existing_queries or [])[:10]) if existing_queries else 'None'}

## Task
Generate 5-8 search queries for raw data.

**Important Principles**:
1. Search for raw data (news, announcements, statistics), not existing reports
2. Forbidden terms: report, analysis, research, forecast, trend analysis
3. Should search: {', '.join(role_info['data_focus'][:5])}
4. Consider different data source angles
5. Support bilingual keywords

## Output Format
One query per line, format: topic + data type + time/scope

Query List:"""

    result = await self._call_llm_directly(prompt)

    if not result.get("success"):
        return []

    queries = self._parse_llm_queries(result.get("content", ""), existing_queries)
    logger.info(f"GenericAgent {self.agent_id}: LLM generated {len(queries)} keywords")
    return queries
```

---

## 4. Integration Plan

### 4.1 Modify `_do_deep_research()`

Trigger LLM expansion when search stagnates, rather than completely replacing existing logic.

```python
async def _do_deep_research(
    self,
    topic: str,
    aspect: str,
    aspects: List[str],
    skill_registry: Any,
) -> Dict[str, Any]:
    """Execute deep research"""

    search_skill = skill_registry.get("web_search") or skill_registry.get("search_skill")
    web_scraper = skill_registry.get("web_scraper")

    research_type = self._context.get("research_type", "market_research")
    role_info = DomainRoleInferrer().infer(research_type, topic)

    llm_call_count = 0
    MAX_LLM_CALLS = 3
    last_llm_call_time = 0
    MIN_CALL_INTERVAL = 5.0

    while True:
        # ... existing search logic ...

        quality_score = self._evaluate_data_quality(all_results)

        if quality_score >= MIN_QUALITY_SCORE and high_quality_count >= MIN_SOURCES:
            break

        # When quality stagnates, use Agent's own LLM capability to expand keywords
        if stagnation_count >= 2 and llm_call_count < MAX_LLM_CALLS:
            elapsed = time.time() - last_llm_call_time
            if elapsed < MIN_CALL_INTERVAL:
                await asyncio.sleep(MIN_CALL_INTERVAL - elapsed)

            llm_queries = await self._generate_smart_queries_with_llm(
                topic=topic,
                aspect=aspect,
                existing_queries=list(executed_queries),
                role_info=role_info,
            )

            if llm_queries:
                queries.extend(llm_queries)
                llm_call_count += 1
                last_llm_call_time = time.time()
                continue

        # LLM can't expand, fall back to hardcoded supplementary queries
        if not pending_queries:
            new_queries = self._generate_supplementary_queries(
                topic, aspect, all_results, executed_queries
            )
            if not new_queries:
                break
            queries.extend(new_queries)
```

---

## 5. Implementation Plan

### 5.1 Phase Breakdown

| Phase | Task | Estimated Time | Priority |
|------|------|----------|--------|
| Phase 1 | Create `DomainRoleInferrer` | 0.5 day | P0 |
| | Add `_call_llm_directly()` | 0.5 day | P0 |
| | Modify `_generate_smart_queries_with_llm()` | 0.5 day | P0 |
| Phase 2 | Modify `_do_deep_research()` call logic | 0.5 day | P0 |
| | Modify `RequirementAnalysisAgent` | 0.5 day | P1 |
| Phase 3 | Unit tests + Integration tests | 1.5 days | P0 |

### 5.2 File Change List

| File | Change Type | Description |
|------|----------|------|
| `src/core/search/` | New directory | Store search-related components |
| `src/core/search/__init__.py` | New | Module initialization |
| `src/core/search/domain_role_inferrer.py` | New | Domain role inferrer |
| `src/core/agents/generic_agent.py` | Modify | 1. Add `_call_llm_directly()` method<br>2. Modify `_generate_smart_queries_with_llm()` signature and implementation<br>3. Add `_parse_llm_queries()` and `_validate_query()`<br>4. Modify `_do_deep_research()` call logic |
| `src/agents/fixed_agents/requirement_analysis_agent.py` | Modify | Pass `domain_context` to `_context` |

---

## 6. Test Plan

### 6.1 Unit Tests

```python
# tests/unit/search/test_keyword_expansion.py

async def test_call_llm_directly_success():
    """Test successful LLM call"""
    agent = GenericAgent(...)
    result = await agent._call_llm_directly("Generate 3 search queries")
    assert result.get("success")

async def test_call_llm_directly_failure():
    """Test LLM failure returns empty"""
    agent = GenericAgent(...)
    result = await agent._call_llm_directly("")
    assert not result.get("success")

async def test_generate_smart_queries():
    """Test keyword generation"""
    agent = GenericAgent(...)
    queries = await agent._generate_smart_queries_with_llm(
        topic="Electric Vehicles", aspect="Market Size",
        role_info={"role": "Analyst", "expertise": [], "data_focus": ["sales", "data"]},
    )
    assert len(queries) > 0

def test_validate_query():
    """Test query validation"""
    agent = GenericAgent(...)
    assert agent._validate_query("EV sales 2024")
    assert not agent._validate_query("EV analysis report")
    assert not agent._validate_query("ab")

def test_parse_llm_queries():
    """Test query parsing"""
    agent = GenericAgent(...)
    content = "1. EV sales\n2. EV policy\ndescription text"
    queries = agent._parse_llm_queries(content)
    assert len(queries) == 2
    assert "EV policy" in queries
```

---

## 7. Key Problem Solutions

### 7.1 Problem 1: Preset Keywords Only in Chinese

**Problem**: `DomainRoleInferrer.ROLE_TEMPLATES` `data_focus` only had Chinese, couldn't support English research.

**Solution**: All templates now include both Chinese and English versions.

**Language Detection**: Auto-detect language from `topic`, or have `RequirementAnalysisAgent` pass `language` parameter.

### 7.2 Problem 2: Search Count vs Keyword Count Mismatch

**Solution**: LLM generates sufficient keyword quantity:
```python
prompt = f"""...
Generate {max(10, min_queries * 1.5)} search keywords...
"""
```

### 7.3 Problem 3: Infinite Loop Risk

**Solution**: Added max search count limit.

```python
MAX_QUERIES = 50  # Max searches (hard limit)
MAX_ITERATIONS = 20  # Max iteration rounds

if len(executed_queries) >= MAX_QUERIES:
    logger.warning(f"GenericAgent {self.agent_id}: Reached max search count {MAX_QUERIES}, force stop")
    break

if iteration >= MAX_ITERATIONS:
    logger.warning(f"GenericAgent {self.agent_id}: Reached max iterations {MAX_ITERATIONS}, force stop")
    break
```

**Complete Search Stop Conditions**:

| Condition | Trigger | Behavior | Priority |
|------|------|------|--------|
| Quality met | Queries >= min AND score >= threshold | Normal end | P0 |
| Quality stagnant | stagnation_count >= STAGNATION_LIMIT (10 rounds) | Accept current data | P1 |
| Keywords exhausted | Cannot generate new queries | Accept current data | P2 |
| Max searches | executed_queries >= MAX_QUERIES (50) | Force stop | P3 |
| Max iterations | iteration >= MAX_ITERATIONS (20) | Force stop | P4 |

### 7.4 Problem 4: Hardcoded Fallback Contradicts Flexibility

**Solution**: LLM expansion first, hardcoded as final fallback.

```python
# 1. LLM expansion (priority)
if stagnation_count >= 2 and llm_call_count < MAX_LLM_CALLS:
    llm_queries = await self._generate_smart_queries_with_llm(...)
    if llm_queries:
        queries.extend(llm_queries)
        continue

# 2. Hardcoded fallback (final fallback)
if not pending_queries:
    new_queries = self._generate_supplementary_queries(...)
    if not new_queries:
        break
    queries.extend(new_queries)
```

---

## 8. Risks and Mitigation

### 8.1 Risk Analysis

| Risk | Impact | Probability | Mitigation |
|------|------|------|----------|
| LLM generates invalid keywords | Search efficiency drops | Medium | `_validate_query()` validation |
| LLM call latency | Search time increases | High | Frequency limit + hardcoded fallback |
| LLM call cost | Budget overrun | Medium | Max 3/task + cheap model |
| API config missing | Feature unavailable | Low | Fallback on `_call_llm_directly()` failure |
| Infinite loop | System freeze | Solved | `MAX_QUERIES` and `MAX_ITERATIONS` hard limits |
| Keyword exhaustion | Search failure | Medium | Accept current data + LLMSkill fallback |

### 8.2 Rollback Strategy

- Keep `_generate_supplementary_queries()` as fallback
- `_call_llm_directly()` failure doesn't affect search loop
- `enable_llm_keyword_expansion` config toggle to enable/disable

---

## 9. Summary

### 9.1 Change List

| Change | Description |
|------|------|
| `DomainRoleInferrer` | New, provides role templates by research type (bilingual) |
| `_call_llm_directly()` | New, Agent directly calls LLM, doesn't depend on LLMSkill |
| `_generate_smart_queries_with_llm()` | Refactored, from LLMSkill to `_call_llm_directly()` |
| `_parse_llm_queries()` | New, parse + validate LLM output |
| `_validate_query()` | New, filter invalid keywords |
| `_do_deep_research()` | Modified, trigger LLM expansion on stagnation, add hard limits |
| `RequirementAnalysisAgent` | Modified, pass `domain_context` and `language` |
| LLM call frequency control | Max 3/task, min 5 second interval |
| Fallback mechanism | LLM failure → `_generate_supplementary_queries()` |
| Search stop conditions | New `MAX_QUERIES` and `MAX_ITERATIONS` hard limits |

### 9.2 Key Changes from v1.x

- Removed independent `SmartKeywordGenerator` and `MissingDataAnalyzer` classes
- All LLM calls unified through `Agent._call_llm_directly()`
- LLMSkill only does content generation fallback (single responsibility)
- Integration point only in `generic_agent.py`, no new files
- Added hard limits on search stop conditions to prevent infinite loops
- Supports bilingual (Chinese/English)

---

**Document Version**: v3.0
**Updated**: 2026-04-29
**Status**: Pending User Review
