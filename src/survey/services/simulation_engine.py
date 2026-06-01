"""
Simulation Engine

Allows personas to answer survey questions.
"""

from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime

from .persona_factory import Persona
from ..models import Survey, SurveyResponse, Answer, QuestionType


class SimulationEngine:
    """Simulation Engine"""
    
    def __init__(self, llm_skill=None):
        self.llm_skill = llm_skill
    
    async def simulate_survey(
        self,
        personas: List[Persona],
        survey: Survey,
        parallel: bool = True,
        max_concurrent: int = 10
    ) -> List[SurveyResponse]:
        """
        Batch simulate survey responses

        Args:
            personas: List of personas
            survey: Survey
            parallel: Whether to execute in parallel
            max_concurrent: Maximum concurrency
        """
        if parallel:
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def limited_simulate(persona: Persona):
                async with semaphore:
                    return await self._simulate_single(persona, survey)
            
            tasks = [limited_simulate(p) for p in personas]
            responses = await asyncio.gather(*tasks)
        else:
            responses = []
            for persona in personas:
                response = await self._simulate_single(persona, survey)
                responses.append(response)
        
        return responses
    
    async def _simulate_single(
        self,
        persona: Persona,
        survey: Survey
    ) -> SurveyResponse:
        """Simulate single person response"""
        
        answers: Dict[str, Answer] = {}
        answer_history = []  # Maintain consistency
        
        for question in survey.questions:
            answer = await self._answer_question(
                persona, question, answer_history
            )
            answers[question.question_id] = answer
            answer_history.append((question, answer))
        
        return SurveyResponse(
            response_id=f"sim_{persona.persona_id}_{survey.survey_id}",
            survey_id=survey.survey_id,
            respondent_id=persona.persona_id,
            answers=answers,
            completed_at=datetime.now(),
        )
    
    async def _answer_question(
        self,
        persona: Persona,
        question: Any,
        history: List[tuple]
    ) -> Answer:
        """Answer a single question"""
        
        # If LLM is available, use it to generate the answer
        if self.llm_skill:
            return await self._answer_with_llm(persona, question, history)
        
        # Otherwise use rule-based generation
        return self._answer_with_rules(persona, question)
    
    async def _answer_with_llm(
        self,
        persona: Persona,
        question: Any,
        history: List[tuple]
    ) -> Answer:
        """Use LLM to generate answer"""
        
        # Build system prompt (persona profile)
        system_prompt = persona.to_prompt()
        
        # Build user prompt (question)
        prompt = f"Now please answer the following survey question:\n\n"
        prompt += f"Question: {question.text}\n"
        
        if question.options:
            prompt += f"\nOptions:\n"
            for i, opt in enumerate(question.options, 1):
                prompt += f"{i}. {opt.text}\n"
        
        if history:
            prompt += "\n[Your Previous Answers]\n"
            for prev_q, prev_a in history[-3:]:
                prompt += f"Q: {prev_q.text}\n"
                prompt += f"A: {prev_a.answer_value}\n\n"
        
        prompt += """
[Response Requirements]
1. Your answer must match your persona's characteristics
2. Answer naturally and realistically, not too "perfect"
3. If there are options, only return the option number or content
4. Maintain consistency with previous answers
"""
        
        # Call LLM
        try:
            if self.llm_skill and hasattr(self.llm_skill, 'execute'):
                # Properly pass kwargs
                response = await self.llm_skill.execute(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=512
                )
                
                # Parse LLM response
                if response.get("success"):
                    llm_content = response.get("content", "")
                    answer_value = self._parse_llm_response(llm_content, question)
                else:
                    # LLM returned failure, fall back to rules
                    answer_value = self._answer_with_rules(persona, question).answer_value
            else:
                # LLM not available, use rules
                answer_value = self._answer_with_rules(persona, question).answer_value
        except Exception:
            # LLM failed, fall back to rules
            answer_value = self._answer_with_rules(persona, question).answer_value
        
        return Answer(
            question_id=question.question_id,
            answer_value=answer_value,
        )
    
    def _answer_with_rules(
        self,
        persona: Persona,
        question: Any
    ) -> Answer:
        """Generate answer using rules"""
        
        import random
        
        if question.question_type == QuestionType.SINGLE_CHOICE:
            # Single choice
            if question.options:
                selected = random.choice(question.options)
                return Answer(
                    question_id=question.question_id,
                    answer_value=selected.text,
                )
        
        elif question.question_type == QuestionType.MULTIPLE_CHOICE:
            # Multiple choice
            if question.options:
                count = random.randint(1, min(3, len(question.options)))
                selected = random.sample(question.options, count)
                return Answer(
                    question_id=question.question_id,
                    answer_value=",".join([opt.text for opt in selected]),
                )
        
        elif question.question_type in [QuestionType.LIKERT, QuestionType.SCALE]:
            # Scale
            score = random.randint(1, 5)
            return Answer(
                question_id=question.question_id,
                answer_value=score,
            )
        
        elif question.question_type == QuestionType.OPEN_ENDED:
            # Open-ended
            templates = [
                "I think this is a very good question.",
                "Based on my experience, I tend to...",
                "I don't know much about this, but I think...",
                "My view is...",
            ]
            return Answer(
                question_id=question.question_id,
                answer_value=random.choice(templates),
                answer_text=random.choice(templates),
            )
        
        # Default
        return Answer(
            question_id=question.question_id,
            answer_value="",
        )
    
    def _parse_llm_response(
        self,
        response: str,
        question: Any
    ) -> Any:
        """Parse LLM response"""
        
        response = response.strip()
        
        if question.question_type in [QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE]:
            if question.options:
                # Try to match options
                for opt in question.options:
                    if opt.text in response:
                        return opt.text
                
                # Try to parse numbers
                import re
                numbers = re.findall(r'\d+', response)
                if numbers:
                    idx = int(numbers[0]) - 1
                    if 0 <= idx < len(question.options):
                        return question.options[idx].text
        
        elif question.question_type in [QuestionType.LIKERT, QuestionType.SCALE]:
            import re
            numbers = re.findall(r'\d+', response)
            if numbers:
                return int(numbers[0])
        
        return response
