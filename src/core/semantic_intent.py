# -*- coding: utf-8 -*-
"""
SemanticIntentAnalyzer - Deep Semantic Intent Analyzer.

Uses LLM for deep semantic analysis, replacing keyword matching.
Supports fallback to keyword matching when LLM is unavailable.
"""

import asyncio
import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .intent_types import IntentType, TaskComplexity, AgentCreationStrategy, IntentAnalysisResult
from .research_type import ResearchType
from .prompt_manager import PromptManager
from src.core.dialogue.sub_intent import SubIntent

logger = logging.getLogger(__name__)

# Shared thread pool for sync analyze() calls (D2 fix)
_SHARED_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=10,
    thread_name_prefix="intent_analyzer"
)


@dataclass
class DeepIntentResult:
    """Deep Intent Analysis Result - richer than IntentAnalysisResult."""

    primary_intent: IntentType
    intent_confidence: float
    intent_reasoning: str
    research_types: List[ResearchType] = field(default_factory=list)
    primary_research_type: Optional[ResearchType] = None
    secondary_research_types: List[ResearchType] = field(default_factory=list)
    task_scope: str = "medium"
    requires_primary_data: bool = False
    requires_secondary_data: bool = True
    domain_context: Dict[str, Any] = field(default_factory=dict)
    hidden_requirements: List[str] = field(default_factory=list)
    complexity: TaskComplexity = TaskComplexity.SINGLE
    aspect_count: int = 0
    estimated_effort: str = "standard"
    execution_preference: str = "sequential"
    output_mode: str = "staged"
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)
    recommended_skills: List[str] = field(default_factory=list)
    llm_model_used: str = ""
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    raw_llm_response: str = ""
    used_fallback: bool = False
    is_composite: bool = False
    sub_intents: List[SubIntent] = field(default_factory=list)
    orchestration_strategy: str = "sequential"
    core_question: str = ""

    def to_intent_analysis_result(self) -> IntentAnalysisResult:
        """Convert to compatible IntentAnalysisResult."""
        strategy = AgentCreationStrategy(
            intent=self.primary_intent, complexity=self.complexity,
            recommended_agents=self._infer_recommended_agents(),
            agent_count_estimate=self._estimate_agent_count(),
            parallel_execution=self.execution_preference == "parallel",
            skill_requirements=self.recommended_skills,
            creation_mode="dynamic" if self.aspect_count > 2 else "predefined",
            priority="medium", context_requirements=self.domain_context,
            clarification_needed=self.needs_clarification,
            clarification_questions=self.clarification_questions if self.needs_clarification else None)
        return IntentAnalysisResult(
            intent=self.primary_intent, complexity=self.complexity,
            strategy=strategy, confidence=self.intent_confidence,
            keywords_matched=[], reasoning=self.intent_reasoning)

    def _infer_recommended_agents(self) -> List[str]:
        agents = []
        if self.requires_secondary_data:
            agents.append("data-collection")
        if self.primary_intent == IntentType.RESEARCH:
            agents.append("market-analysis")
        if self.primary_intent in (IntentType.EVALUATION, IntentType.FIX):
            agents.append("quality-check")
        agents.append("report-generation")
        return list(set(agents))

    def _estimate_agent_count(self) -> int:
        base_count = self.aspect_count
        if self.requires_primary_data:
            base_count += 2
        if self.primary_research_type in (ResearchType.SWOT_ANALYSIS, ResearchType.PESTEL_ANALYSIS):
            base_count += 1
        return max(base_count, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {"primary_intent": self.primary_intent.value, "intent_confidence": self.intent_confidence,
                "intent_reasoning": self.intent_reasoning,
                "research_types": [rt.value for rt in self.research_types],
                "primary_research_type": self.primary_research_type.value if self.primary_research_type else None,
                "secondary_research_types": [rt.value for rt in self.secondary_research_types],
                "task_scope": self.task_scope, "requires_primary_data": self.requires_primary_data,
                "requires_secondary_data": self.requires_secondary_data, "domain_context": self.domain_context,
                "hidden_requirements": self.hidden_requirements, "complexity": self.complexity.value,
                "aspect_count": self.aspect_count, "estimated_effort": self.estimated_effort,
                "execution_preference": self.execution_preference, "output_mode": self.output_mode,
                "needs_clarification": self.needs_clarification,
                "clarification_questions": self.clarification_questions,
                "recommended_skills": self.recommended_skills, "llm_model_used": self.llm_model_used,
                "analysis_timestamp": self.analysis_timestamp.isoformat(), "used_fallback": self.used_fallback,
                "is_composite": self.is_composite,
                "sub_intents": [
                    {"intent_id": s.intent_id, "description": s.description,
                     "aspects": s.aspects, "research_types": s.research_types,
                     "dependency": s.dependency}
                    for s in self.sub_intents
                ],
                "orchestration_strategy": self.orchestration_strategy}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeepIntentResult":
        research_types = []
        for rt_str in data.get("research_types", []):
            try:
                research_types.append(ResearchType(rt_str))
            except ValueError:
                pass
        primary_rt = None
        if data.get("primary_research_type"):
            try:
                primary_rt = ResearchType(data["primary_research_type"])
            except ValueError:
                pass
        secondary_rts = []
        for rt_str in data.get("secondary_research_types", []):
            try:
                secondary_rts.append(ResearchType(rt_str))
            except ValueError:
                pass
        sub_intents = []
        for s in data.get("sub_intents", []):
            sub_intents.append(SubIntent(
                intent_id=s.get("intent_id", "sub_1"),
                description=s.get("description", ""),
                aspects=s.get("aspects", []),
                research_types=s.get("research_types", []),
                dependency=s.get("dependency", "none"),
            ))
        return cls(
            primary_intent=IntentType(data.get("primary_intent", "open_ended")),
            intent_confidence=data.get("intent_confidence", 0.5),
            intent_reasoning=data.get("intent_reasoning", ""),
            research_types=research_types,
            primary_research_type=primary_rt,
            secondary_research_types=secondary_rts,
            task_scope=data.get("task_scope", "medium"),
            requires_primary_data=data.get("requires_primary_data", False),
            requires_secondary_data=data.get("requires_secondary_data", True),
            domain_context=data.get("domain_context", {}),
            hidden_requirements=data.get("hidden_requirements", []),
            complexity=TaskComplexity(data.get("complexity", "single")),
            aspect_count=data.get("aspect_count", 0),
            estimated_effort=data.get("estimated_effort", "standard"),
            execution_preference=data.get("execution_preference", "sequential"),
            output_mode=data.get("output_mode", "staged"),
            needs_clarification=data.get("needs_clarification", False),
            clarification_questions=data.get("clarification_questions", []),
            recommended_skills=data.get("recommended_skills", []),
            llm_model_used=data.get("llm_model_used", ""),
            raw_llm_response=data.get("raw_llm_response", ""),
            used_fallback=data.get("used_fallback", False),
            is_composite=data.get("is_composite", False),
            sub_intents=sub_intents,
            orchestration_strategy=data.get("orchestration_strategy", "sequential"),
            analysis_timestamp=datetime.fromisoformat(data["analysis_timestamp"]) if data.get("analysis_timestamp") else datetime.now(),
        )


class SemanticIntentAnalyzer:
    """Deep Semantic Intent Analyzer - uses LLM or keyword fallback."""

    def __init__(self, use_llm=True, fallback_to_keyword=True, llm_model=None,
                 max_tokens=1024, temperature=0.1, enable_self_consistency=False,
                 self_consistency_samples=3):
        self._use_llm = use_llm
        self._fallback_to_keyword = fallback_to_keyword
        self._llm_model = llm_model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._enable_self_consistency = enable_self_consistency
        self._self_consistency_samples = self_consistency_samples
        self._llm_skill = None
        logger.info(f"SemanticIntentAnalyzer initialized: use_llm={use_llm}, fallback={fallback_to_keyword}")

    def _get_llm_skill(self):
        if self._llm_skill is None:
            try:
                from src.skills.llm_skill import LLMSkill
            except ImportError:
                import sys; from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent.parent.parent))
                from src.skills.llm_skill import LLMSkill
            self._llm_skill = LLMSkill()
        return self._llm_skill

    def _get_keyword_analyzer(self):
        logger.warning("Keyword fallback no longer available")
        return None

    async def analyze_async(self, user_request, requirement=None, conversation_history=None):
        """Asynchronously analyze user intent."""
        if not user_request:
            user_request = ""
        if requirement is None:
            requirement = {"topic": "", "aspects": []}

        if self._use_llm:
            try:
                if self._enable_self_consistency:
                    return await self._analyze_with_self_consistency(user_request, requirement, conversation_history)
                return await self._analyze_with_llm(user_request, requirement, conversation_history)
            except Exception as e:
                logger.warning(f"LLM intent analysis failed: {e}")
                if self._fallback_to_keyword:
                    logger.info("Falling back to keyword matching")
                    return self._analyze_with_keyword(user_request, requirement)
                raise
        return self._analyze_with_keyword(user_request, requirement)

    def analyze(self, user_request, requirement=None):
        """
        Synchronously analyze user intent.
        
        Note: This is a compatibility method. New code should prefer analyze_async().
        Uses shared thread pool to avoid resource exhaustion (D2 fix).
        """
        try:
            loop = asyncio.get_running_loop()
            # D2 fix: Use shared thread pool instead of creating new one each call
            future = _SHARED_EXECUTOR.submit(
                asyncio.run,
                self.analyze_async(user_request, requirement)
            )
            return future.result()
        except RuntimeError:
            # No running event loop
            return asyncio.run(self.analyze_async(user_request, requirement))
        except Exception as e:
            logger.error(f"[IntentAnalyzer] Sync analyze failed: {e}")
            raise

    def _load_intent_prompts(self):
        pm = PromptManager.get_instance()
        try:
            return pm.render("agents", "intent_analysis_system"), pm.render("agents", "intent_analysis_user")
        except FileNotFoundError:
            fallback_sys = "You are a professional market research requirement analysis expert."
            fallback_usr = 'Analyze intent: {user_request}\nRequirement: {requirement_json}\nOutput JSON.'
            return fallback_sys, fallback_usr

    @staticmethod
    def _format_intent_prompt(template, user_request, requirement):
        safe = user_request.replace("{", "{{").replace("}", "}}")
        return template.format(user_request=safe, requirement_json=json.dumps(requirement, ensure_ascii=False, indent=2))

    async def _analyze_with_llm(self, user_request, requirement, conversation_history=None):
        llm_skill = self._get_llm_skill()
        system_prompt, user_template = self._load_intent_prompts()
        prompt = self._format_intent_prompt(user_template, user_request, requirement)
        result = await llm_skill.execute(prompt=prompt, system_prompt=system_prompt,
                                          model=self._llm_model, max_tokens=self._max_tokens,
                                          temperature=self._temperature)
        if not result.get("success"):
            raise ValueError(f"LLM call failed: {result.get('error', 'Unknown')}")
        return self._build_result(llm_output=self._parse_llm_json(result["content"]),
                                   model_used=result.get("model", ""), raw_response=result["content"],
                                   used_fallback=False)

    async def _analyze_with_self_consistency(self, user_request, requirement, conversation_history=None):
        tasks = [self._call_llm_with_temp(user_request, requirement, self._temperature + i * 0.1)
                 for i in range(self._self_consistency_samples)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, dict)]
        if not valid:
            raise ValueError("All self-consistency samples failed")
        intent_counts = {}
        for r in valid:
            intent = r.get("primary_intent", "open_ended")
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
        best = max(intent_counts, key=lambda k: intent_counts[k])
        for r in valid:
            if r.get("primary_intent") == best:
                return self._build_result(llm_output=r, model_used="self_consistency",
                                           raw_response=json.dumps(valid, ensure_ascii=False),
                                           used_fallback=False)
        return self._build_result(llm_output=valid[0], model_used="self_consistency",
                                   raw_response=json.dumps(valid, ensure_ascii=False), used_fallback=False)

    async def _call_llm_with_temp(self, user_request, requirement, temperature):
        llm_skill = self._get_llm_skill()
        system_prompt, user_template = self._load_intent_prompts()
        prompt = self._format_intent_prompt(user_template, user_request, requirement)
        result = await llm_skill.execute(prompt=prompt, system_prompt=system_prompt,
                                          model=self._llm_model, max_tokens=self._max_tokens,
                                          temperature=temperature)
        if not result.get("success"):
            return None
        return self._parse_llm_json(result.get("content", ""))

    def _parse_llm_json(self, content):
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        import re
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(content[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass
        fixed = content.replace("'", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        fixed = re.sub(r',\s*([}\]])', r'\1', content)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        raise json.JSONDecodeError(
            f"Failed to parse LLM JSON after all recovery attempts: {content[:200]}",
            content, 0
        )

    def _build_result(self, llm_output, model_used, raw_response, used_fallback):
        intent_str = llm_output.get("primary_intent", "open_ended")
        try:
            primary_intent = IntentType(intent_str.lower())
        except ValueError:
            primary_intent = IntentType.OPEN_ENDED

        complexity_str = llm_output.get("complexity", "single")
        try:
            complexity = TaskComplexity(complexity_str.lower())
        except ValueError:
            complexity = TaskComplexity.SINGLE

        research_types = []
        primary_research_type = None
        secondary_research_types = []
        for rt_str in llm_output.get("research_types", []):
            try:
                rt = ResearchType(rt_str.lower())
                research_types.append(rt)
            except ValueError:
                pass
        if research_types:
            primary_research_type = research_types[0]
            secondary_research_types = research_types[1:] if len(research_types) > 1 else []

        requires_primary = llm_output.get("requires_primary_data", False)
        if any(rt.is_primary_research() for rt in research_types):
            requires_primary = True

        return DeepIntentResult(
            primary_intent=primary_intent, intent_confidence=llm_output.get("confidence", 0.7),
            intent_reasoning=llm_output.get("reasoning", ""),
            research_types=research_types, primary_research_type=primary_research_type,
            secondary_research_types=secondary_research_types,
            requires_primary_data=requires_primary,
            requires_secondary_data=llm_output.get("requires_secondary_data", True),
            complexity=complexity, aspect_count=llm_output.get("aspect_count", 0),
            estimated_effort=llm_output.get("estimated_effort", "standard"),
            execution_preference=llm_output.get("execution_preference", "sequential"),
            output_mode=llm_output.get("output_mode", "staged"),
            hidden_requirements=llm_output.get("hidden_requirements", []),
            domain_context=llm_output.get("domain_context", {}),
            recommended_skills=llm_output.get("recommended_skills", []),
            needs_clarification=llm_output.get("needs_clarification", False),
            clarification_questions=llm_output.get("clarification_questions", []),
            llm_model_used=model_used, raw_llm_response=raw_response, used_fallback=used_fallback,
            is_composite=llm_output.get("is_composite", False),
            sub_intents=[
                SubIntent(
                    intent_id=s.get("intent_id", f"sub_{i+1}"),
                    description=s.get("description", ""),
                    aspects=s.get("aspects", []),
                    research_types=s.get("research_types", []),
                    dependency=s.get("dependency", "none"),
                )
                for i, s in enumerate(llm_output.get("sub_intents", []))
                if isinstance(s, dict)
            ],
            orchestration_strategy=llm_output.get("orchestration_strategy", "sequential"))

    def _infer_skills_from_intent(self, intent: IntentType, hidden_requirements: List[str]) -> List[str]:
        skills = []
        if intent == IntentType.RESEARCH:
            skills.extend(["search_skill", "llm_skill"])
        elif intent == IntentType.EVALUATION:
            skills.extend(["llm_skill", "search_skill"])
        elif intent == IntentType.FIX:
            skills.extend(["llm_skill"])
        else:
            skills.extend(["llm_skill"])
        for req in hidden_requirements:
            req_lower = req.lower()
            if any(kw in req_lower for kw in ["收集", "数据", "搜索", "search", "data", "collect"]):
                if "search_skill" not in skills:
                    skills.append("search_skill")
            if any(kw in req_lower for kw in ["报告", "文档", "report", "document", "docx", "生成报告"]):
                if "docx_skill" not in skills:
                    skills.append("docx_skill")
            if any(kw in req_lower for kw in ["分析", "评估", "analysis", "evaluate"]):
                if "llm_skill" not in skills:
                    skills.append("llm_skill")
        return list(dict.fromkeys(skills))

    def _analyze_with_keyword(self, user_request, requirement):
        """Keyword matching fallback for intent analysis."""
        _survey_kw = ["survey", "questionnaire", "poll", "consumer research",
                      "user research", "market research", "survey study"]
        _has_survey = any(kw in user_request.lower() for kw in _survey_kw) if user_request else False
        return DeepIntentResult(
            primary_intent=IntentType.RESEARCH, intent_confidence=0.5,
            intent_reasoning="Keyword matching fallback",
            requires_primary_data=_has_survey, complexity=TaskComplexity.SINGLE,
            used_fallback=True, llm_model_used="keyword_matching")
