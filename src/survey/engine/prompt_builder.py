"""
Prompt Builder Module

Interview-style research prompt builder.
Based on: ACL Findings EMNLP 2025 (name-based + interview format)
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass

from ..models import Question, Answer, QuestionType
from .persona_models import PersonaV2, PromptLevel


@dataclass
class PromptResult:
    """Prompt result container."""
    system_prompt: str
    user_prompt: str
    temperature: float
    level: PromptLevel


class TemperatureScheduler:
    """Temperature scheduler for different question types."""

    QUESTION_TYPE_TEMP = {
        QuestionType.SINGLE_CHOICE: 0.3,
        QuestionType.MULTIPLE_CHOICE: 0.3,
        QuestionType.LIKERT: 0.4,
        QuestionType.SCALE: 0.4,
        QuestionType.YES_NO: 0.2,
        QuestionType.OPEN_ENDED: 0.8,
        QuestionType.RANKING: 0.4,
        QuestionType.MATRIX: 0.4,
        QuestionType.DROPDOWN: 0.4,
    }

    @classmethod
    def get_temperature(cls, question_type: QuestionType) -> float:
        """Get temperature for a question type."""
        return cls.QUESTION_TYPE_TEMP.get(question_type, 0.7)


class SimulationPromptBuilder:
    """
    Simulation Prompt Builder.

    Prompt levels:
    - MINIMAL: Basic persona info
    - STANDARD: MINIMAL + traits
    - ENHANCED: STANDARD + history (default)
    - FULL: ENHANCED + background + decision context
    """

    SYSTEM_BASE = """You are participating in a market research survey.
Answer based on your persona (age, occupation, income, education, city tier).
Your demographic profile shapes your opinions. Most people with similar backgrounds to yours
tend to have consistent views. Answer as a typical person in your demographic group."""

    def build_prompt(
        self,
        persona: PersonaV2,
        question: Question,
        history: Optional[List[Tuple[Question, Answer]]] = None,
        survey_context: str = "",
        level: PromptLevel = PromptLevel.ENHANCED,
    ) -> PromptResult:
        """Build prompt for simulation."""
        if level == PromptLevel.MINIMAL:
            system, user = self._build_minimal(persona, question, survey_context)
        elif level == PromptLevel.STANDARD:
            system, user = self._build_standard(persona, question, survey_context)
        elif level == PromptLevel.ENHANCED:
            system, user = self._build_enhanced(persona, question, history, survey_context)
        else:
            system, user = self._build_full(persona, question, history, survey_context)

        temp = TemperatureScheduler.get_temperature(question.question_type)

        return PromptResult(
            system_prompt=system,
            user_prompt=user,
            temperature=temp,
            level=level,
        )

    # ---------------------------------------------------------------- #
    # MINIMAL
    # ---------------------------------------------------------------- #
    def _build_minimal(
        self,
        persona: PersonaV2,
        question: Question,
        context: str
    ) -> Tuple[str, str]:
        """Build minimal level prompt."""
        system = self.SYSTEM_BASE + f"\nResearch topic: {context}"
        user = (
            f"[Respondent] {persona.name}, {persona.age} years old, {persona.gender}, "
            f"{persona.city}, {persona.occupation}\n\n"
            f"[Question] {question.text}\n"
            f"{self._format_options(question)}\n"
            f"Please select the option that best fits you:"
        )
        return system, user

    # ---------------------------------------------------------------- #
    # STANDARD
    # ---------------------------------------------------------------- #
    def _build_standard(
        self,
        persona: PersonaV2,
        question: Question,
        context: str
    ) -> Tuple[str, str]:
        """Build standard level prompt."""
        system = self.SYSTEM_BASE + f"\nResearch topic: {context}"
        traits = "、".join(persona.personality_traits[:4]) if persona.personality_traits else "—"
        user = (
            f"[Respondent Profile]\n"
            f"Name: {persona.name}, {persona.age} years old, {persona.gender}\n"
            f"Occupation: {persona.occupation}, City: {persona.city}, Education: {persona.education}\n"
            f"Personality: {traits}\n"
            f"Decision style: {persona.decision_style}\n\n"
            f"[Question] {question.text}\n"
            f"{self._format_options(question)}\n"
            f"Please answer as {persona.name}:"
        )
        return system, user

    # ---------------------------------------------------------------- #
    # ENHANCED (with history)
    # ---------------------------------------------------------------- #
    def _build_enhanced(
        self,
        persona: PersonaV2,
        question: Question,
        history: Optional[List[Tuple[Question, Answer]]],
        context: str,
    ) -> Tuple[str, str]:
        """Build enhanced level prompt with history."""
        system = self.SYSTEM_BASE + f"\nResearch topic: {context}"

        profile = self._build_profile_section(persona)
        history_text = self._format_history(history)

        # Determine if price/income affects the answer
        income_context = ""
        if persona.income and any(k in str(persona.income) for k in ["100", "500", "80k", "100k", "40-60"]):
            income_context = " (higher income bracket)"
        elif persona.income and any(k in str(persona.income) for k in ["3-5", "5-10", "1-3"]):
            income_context = " (modest income)"

        user = (
            f"{profile}{income_context}\n\n"
            f"{history_text}\n\n"
            f"[Current Question]\n{question.text}\n"
            f"{self._format_options(question)}\n\n"
            f"As {persona.name}, choose one option. Output only the option number, nothing else."
        )
        return system, user

    # ---------------------------------------------------------------- #
    # FULL
    # ---------------------------------------------------------------- #
    def _build_full(
        self,
        persona: PersonaV2,
        question: Question,
        history: Optional[List[Tuple[Question, Answer]]],
        context: str,
    ) -> Tuple[str, str]:
        """Build full level prompt with all context."""
        system = self.SYSTEM_BASE + f"\nResearch topic: {context}"

        profile = self._build_profile_section(persona)
        history_text = self._format_history(history)
        bg = persona.background_story[:300] if persona.background_story else ""

        decision_context = ""
        if persona.price_sensitivity > 0.6:
            decision_context += "Price-conscious: you compare prices and look for deals.\n"
        elif persona.price_sensitivity < 0.3:
            decision_context += "Quality-focused: you prioritize quality over price.\n"

        if persona.income and any(k in str(persona.income) for k in ["100", "500", "80k", "100k"]):
            decision_context += "You have high disposable income and can afford premium options.\n"
        elif persona.income and any(k in str(persona.income) for k in ["3-5", "5-10", "low"]):
            decision_context += "Your budget is limited and you look for value.\n"

        if persona.digital_literacy > 0.7:
            decision_context += "You are digitally savvy and regularly research products online.\n"
        elif persona.digital_literacy < 0.3:
            decision_context += "You prefer traditional shopping channels and trust face-to-face interactions.\n"

        user = (
            f"[Respondent Background]\n{bg}\n\n"
            f"{profile}\n\n"
            f"[Decision Characteristics]\n{decision_context}"
            f"{history_text}\n\n"
            f"[Current Question]\n{question.text}\n"
            f"{self._format_options(question)}\n\n"
            f"Please answer as {persona.name}, combining your background and previous answers, select the option that best fits you."
        )
        return system, user

    # ---------------------------------------------------------------- #
    # Helper methods
    # ---------------------------------------------------------------- #
    def _build_profile_section(self, persona: PersonaV2) -> str:
        """Build profile section for prompt."""
        lines = ["[Respondent Profile]"]
        lines.append(
            f"Name: {persona.name}, {persona.age} years old, {persona.gender}"
        )
        lines.append(
            f"Occupation: {persona.occupation}, City: {persona.city}, "
            f"Education: {persona.education}, Income: {persona.income}"
        )

        if persona.consumption_habits:
            habits = "、".join(persona.consumption_habits[:4])
            ps = (
                "High" if persona.price_sensitivity > 0.6
                else "Medium" if persona.price_sensitivity > 0.3
                else "Low"
            )
            lines.append(f"Consumption: {habits}, Price sensitivity: {ps}")

        if persona.personality_traits:
            lines.append(f"Personality: {'、'.join(persona.personality_traits[:4])}")

        lines.append(f"Decision style: {persona.decision_style}")

        return "\n".join(lines)

    def _format_options(self, question: Question) -> str:
        """Format question options for prompt."""
        if not question.options:
            return ""
        lines = ["\n[Options]"]
        for i, opt in enumerate(question.options, 1):
            lines.append(f"{i}. {opt.text}")
        return "\n".join(lines)

    def _format_history(
        self,
        history: Optional[List[Tuple[Question, Answer]]],
        max_entries: int = 5
    ) -> str:
        """Format answer history for prompt."""
        if not history:
            return "[Previous Answers] (This is the first question)"

        entries = history[-max_entries:]
        lines = ["[Your Previous Answers]"]
        for q, a in entries:
            q_text = q.text[:60] + "..." if len(q.text) > 60 else q.text
            lines.append(f"Q: {q_text} → A: {a.answer_value}")

        return "\n".join(lines)
