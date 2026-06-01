"""
V2 Simulation Engine

Integrates PersonaGeneratorV2 + PromptBuilder + CostTracker + RetryHandler
for AI survey simulation.

Error handling strategy:
- Failed Fast: LLM configuration errors fail immediately
- Retry with backoff: Temporary failures are retried
- Graceful degradation: Individual failures don't stop batch processing
"""

import asyncio
import logging
import random
import re
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import tiktoken

from ..models import Survey, SurveyResponse, Answer, Question, QuestionType
from .persona_models import PersonaV2, PromptLevel
from .persona_generator import PersonaGeneratorV2
from .prompt_builder import SimulationPromptBuilder, PromptResult
from .cost_monitor import LLMCostTracker, RetryHandler
from .errors import (
    LLMTemporaryFailure,
    LLMConfigurationError,
    BudgetExceededError,
    SimulationQualityError,
)

logger = logging.getLogger(__name__)


class SimulationExecutor:
    """
    Simulation Executor for AI survey.

    Execution flow:
    1. Pre-flight check: Validate LLM, configuration
    2. Generate personas (PersonaGeneratorV2)
    3. Simulate survey (SimulationEngine)
    4. Collect responses
    5. Generate report
    """

    def __init__(
        self,
        llm_skill=None,
        prompt_level: PromptLevel = PromptLevel.ENHANCED,
        min_fidelity: float = 0.0,
        budget_limit: float = 5.0,
        random_seed: Optional[int] = None,
    ):
        self._llm_skill = llm_skill
        self._prompt_level = prompt_level
        self._min_fidelity = min_fidelity
        self._budget_limit = budget_limit
        self._random_seed = random_seed

        self._generator = PersonaGeneratorV2(llm_skill=llm_skill, random_seed=random_seed)
        self._prompt_builder = SimulationPromptBuilder()
        self._cost_tracker: Optional[LLMCostTracker] = None

    # ---------------------------------------------------------------- #
    # Main execution
    # ---------------------------------------------------------------- #
    async def execute(
        self,
        survey: Survey,
        template_name: str = "white_collar",
        persona_type: str = "consumer",
        target_count: int = 200,
        survey_context: str = "",
    ) -> Dict[str, Any]:
        """
        Execute AI survey simulation.

        Args:
            survey: Survey object
            template_name: Persona template name
            persona_type: Persona type (consumer/expert)
            target_count: Target sample count
            survey_context: Research context

        Returns:
            {
                "success": True,
                "personas": [PersonaV2],
                "responses": [SurveyResponse],
                "cost_report": {...},
                "quality_report": {...},
            }

        Raises:
            LLMTemporaryFailure: LLM temporary failure
            BudgetExceededError: Budget exceeded
        """
        # Apply random seed for reproducibility
        if self._random_seed is not None:
            random.seed(self._random_seed)
            import numpy as np
            try:
                np.random.seed(self._random_seed)
            except Exception:
                pass

        task_id = f"sim_{uuid.uuid4().hex[:8]}"
        self._cost_tracker = LLMCostTracker(
            task_id=task_id, budget_limit=self._budget_limit
        )

        logger.info(
            f"Starting simulation: task={task_id}, template={template_name}, n={target_count}"
        )

        # Phase 1: Pre-flight check
        self._preflight_check()

        # Phase 2: Generate personas
        logger.info("Phase 1/3: Generating personas...")
        personas, gen_stats = await self._generator.generate_batch(
            template_name=template_name,
            count=target_count,
            persona_type=persona_type,
            context=survey_context,
        )

        if not personas:
            raise SimulationQualityError(
                metric="persona_count",
                actual=0,
                threshold=1,
                detail={"reason": "Persona generation did not produce valid personas"},
            )

        logger.info(
            f"Generated personas -> {len(personas)} "
            f"(LLM={gen_stats['llm_success']}, rule-based={gen_stats['rule_fallback']})"
        )

        # Phase 3: Simulate survey
        logger.info("Phase 2/3: Simulating survey...")
        responses = await self._simulate_all(personas, survey, survey_context)

        # Generate report
        cost_report = self._cost_tracker.get_report()

        logger.info(
            f"Phase 3/3: Completed. "
            f"Responses={len(responses)}, Cost=${cost_report['total_cost']:.2f}, "
            f"LLM calls={cost_report['total_calls']}"
        )

        return {
            "success": True,
            "task_id": task_id,
            "personas": personas,
            "responses": responses,
            "cost_report": cost_report,
            "generation_stats": gen_stats,
        }

    # ---------------------------------------------------------------- #
    # Pre-flight check
    # ---------------------------------------------------------------- #
    def _preflight_check(self):
        """Pre-flight validation check. Only required when LLM simulation is used."""
        if not self._llm_skill:
            logger.info("No LLM skill configured - simulation will use rule-based mode")
            return

        if hasattr(self._llm_skill, "is_available"):
            if not self._llm_skill.is_available():
                raise LLMConfigurationError(
                    detail={"reason": "LLM service unavailable"}
                )

    # ---------------------------------------------------------------- #
    # Survey simulation
    # ---------------------------------------------------------------- #
    async def _simulate_all(
        self,
        personas: List[PersonaV2],
        survey: Survey,
        context: str,
        max_concurrent: int = 10,
    ) -> List[SurveyResponse]:
        """
        Simulate all personas.

        Error handling: Fail Fast strategy.
        - LLMTemporaryFailure / BudgetExceededError → Propagate immediately
        - Other errors → Log and continue (graceful degradation)
        """
        sem = asyncio.Semaphore(max_concurrent)

        async def sim_one(persona: PersonaV2) -> SurveyResponse:
            async with sem:
                return await self._simulate_persona(persona, survey, context)

        tasks = [sim_one(p) for p in personas]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses: List[SurveyResponse] = []
        errors: List[Dict] = []

        for i, r in enumerate(results):
            if isinstance(r, SurveyResponse):
                responses.append(r)
            elif isinstance(r, (LLMTemporaryFailure, BudgetExceededError)):
                # Critical errors: propagate immediately
                raise r
            elif isinstance(r, Exception):
                logger.warning(f"Persona #{i} failed: {r}")
                errors.append({"persona_index": i, "error": str(r)})

        if errors:
            logger.warning(
                f"Simulation completed with errors: {len(responses)} success, {len(errors)} failed"
            )

        return responses

    async def _simulate_persona(
        self,
        persona: PersonaV2,
        survey: Survey,
        context: str,
    ) -> SurveyResponse:
        """Simulate single persona survey, respecting skip logic."""
        answers: Dict[str, Answer] = {}
        history: List[Tuple[Question, Answer]] = []

        for question in survey.questions:
            # Check skip logic
            if self._is_skipped(question, answers):
                answer = Answer(
                    question_id=question.question_id,
                    answer_value="__skipped__",
                    answer_text=None,
                )
            else:
                answer = await self._answer_question(persona, question, history, context)
                answers[question.question_id] = answer
                history.append((question, answer))

        return SurveyResponse(
            response_id=f"r_{persona.persona_id}_{survey.survey_id}",
            survey_id=survey.survey_id,
            respondent_id=persona.persona_id,
            answers=answers,
            completed_at=datetime.now(),
            quality_score=1.0,
            is_valid=True,
        )

    @staticmethod
    def _is_skipped(question: Question, answers: Dict[str, Answer]) -> bool:
        """Check if a question should be skipped based on skip_logic."""
        logic = question.skip_logic
        if not logic:
            return False

        depends_on = logic.get("depends_on", "")
        condition = logic.get("condition", "equals")
        value = logic.get("value")
        effect = logic.get("effect", "show")

        # If the dependent question hasn't been answered yet, don't skip
        if depends_on not in answers:
            return False

        prev_answer = str(answers[depends_on].answer_value)

        # Evaluate condition
        met = False
        if condition == "equals":
            met = prev_answer == str(value)
        elif condition == "not_equals":
            met = prev_answer != str(value)
        elif condition == "in":
            met = prev_answer in [str(v) for v in (value or [])]
        elif condition == "greater_than":
            try:
                met = float(prev_answer) > float(value)
            except (ValueError, TypeError):
                met = False
        elif condition == "less_than":
            try:
                met = float(prev_answer) < float(value)
            except (ValueError, TypeError):
                met = False

        # If effect is "hide", skip when condition IS met
        # If effect is "show", skip when condition is NOT met
        return met if effect == "hide" else not met

    async def _answer_question(
        self,
        persona: PersonaV2,
        question: Question,
        history: List[Tuple[Question, Answer]],
        context: str,
    ) -> Answer:
        """
        Answer single question. Uses rule-based fallback when no LLM is available.
        """
        if not self._llm_skill:
            return self._answer_with_rules(persona, question)

        prompt = self._prompt_builder.build_prompt(
            persona=persona, question=question, history=history,
            survey_context=context, level=self._prompt_level,
        )

        result = await self._call_llm_with_retry(prompt, question)

        self._record_estimated_cost(prompt, result.get("content", ""), question.question_id)

        answer_value = self._parse_response(result.get("content", ""), question)

        return Answer(
            question_id=question.question_id,
            answer_value=answer_value,
            answer_text=answer_value if question.question_type == QuestionType.OPEN_ENDED else None,
        )

    def _answer_with_rules(self, persona: PersonaV2, question: Question) -> Answer:
        """Simple rule-based answer when no LLM is available."""
        import random
        if question.options:
            selected = random.choice(question.options)
            return Answer(question_id=question.question_id, answer_value=selected.option_id)
        return Answer(question_id=question.question_id, answer_value="42")

    # ---------------------------------------------------------------- #
    # LLM call (with retry)
    # ---------------------------------------------------------------- #
    async def _call_llm_with_retry(
        self,
        prompt: PromptResult,
        question: Question,
    ) -> Dict:
        """Call LLM with retry logic."""
        last_error = None

        for attempt in range(1, RetryHandler.MAX_RETRIES + 1):
            try:
                if not self._llm_skill:
                    raise LLMConfigurationError({"reason": "LLM not configured"})

                result = await asyncio.wait_for(
                    self._llm_skill.execute(
                        prompt=prompt.user_prompt,
                        system_prompt=prompt.system_prompt,
                        temperature=prompt.temperature,
                        max_tokens=512,
                    ),
                    timeout=RetryHandler.TIMEOUT,
                )

                if result.get("success") and result.get("content"):
                    return result

                raise ValueError(f"LLM returned empty: {result.get('error', 'unknown')}")

            except asyncio.TimeoutError:
                last_error = LLMTemporaryFailure(
                    attempt=attempt,
                    max_retries=RetryHandler.MAX_RETRIES,
                    detail={"reason": "LLM timeout"},
                )
                if attempt < RetryHandler.MAX_RETRIES:
                    wait = RetryHandler.get_backoff(attempt)
                    logger.warning(f"LLM timeout (attempt {attempt}), retrying in {wait}s")
                    await asyncio.sleep(wait)

            except Exception as e:
                if RetryHandler.should_retry(e) and attempt < RetryHandler.MAX_RETRIES:
                    wait = RetryHandler.get_backoff(attempt)
                    logger.warning(f"LLM error (attempt {attempt}): {e}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    last_error = e
                else:
                    raise

        # All retries exhausted
        raise last_error or LLMTemporaryFailure(
            attempt=RetryHandler.MAX_RETRIES,
            max_retries=RetryHandler.MAX_RETRIES,
            detail={"reason": "Retries exhausted"},
        )

    # ---------------------------------------------------------------- #
    # Helper methods
    # ---------------------------------------------------------------- #
    def _record_estimated_cost(
        self, prompt: PromptResult, response: str, qid: str
    ):
        """Record estimated cost for tracking."""
        if not self._cost_tracker:
            return

        input_text = prompt.system_prompt + prompt.user_prompt
        output_text = response or ""
        input_tokens = self._count_tokens(input_text)
        output_tokens = self._count_tokens(output_text)

        self._cost_tracker.record_call(
            model="gpt-4o-mini",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            phase=f"q_{qid}",
        )

    @staticmethod
    def _count_tokens(text: str) -> int:
        """Count tokens using tiktoken (cl100k_base for GPT-4/4o)."""
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
        # Fallback: CJK ~1.5 tokens/char, ASCII ~0.25 tokens/char
        cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", text))
        ascii_chars = len(re.findall(r"[a-zA-Z0-9\s]", text))
        other = max(0, len(text) - cjk - ascii_chars)
        return max(1, int(cjk * 1.5 + ascii_chars * 0.25 + other * 0.5))

    def _parse_response(self, content: str, question: Question) -> Any:
        """Parse LLM response to answer value."""
        if not content:
            return ""

        content = content.strip()

        # Try to match option id or text
        if question.options:
            # First: try to match option_id directly (e.g., "1", "2", "a", "b")
            content_lower = content.strip().lower()
            for opt in question.options:
                if opt.option_id == content_lower:
                    return opt.option_id

            # Second: try to match option text (LLM usually outputs full text)
            for opt in question.options:
                if opt.text.lower() in content_lower:
                    return opt.option_id

            # Third: try to match option number (1-indexed)
            nums = re.findall(r"\d+", content)
            if nums:
                idx = int(nums[0]) - 1
                if 0 <= idx < len(question.options):
                    return question.options[idx].option_id

        # For Likert/Scale questions, extract number
        if question.question_type in (QuestionType.LIKERT, QuestionType.SCALE):
            nums = re.findall(r"\d+", content)
            if nums:
                return int(nums[0])

        return content[:500]

    def get_cost_report(self) -> Optional[Dict]:
        """Get cost report."""
        return self._cost_tracker.get_report() if self._cost_tracker else None
