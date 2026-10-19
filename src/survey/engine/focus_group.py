"""
Focus Group Simulator

Simulates a group of Agents with different personas discussing a topic.
Supports moderator guidance, free discussion, viewpoint conflict detection,
and meeting minutes generation.

Literature references:
- Generative Agents Park et al. (2023): 25-Agent social simulation
- AgentSociety (2025): 10k+ agents social experiment
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from ..models import Question
from .persona_models import PersonaV2, PersonaType
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


@dataclass
class FocusGroupMessage:
    """Single focus group message."""
    speaker_id: str
    speaker_name: str
    content: str
    round: int
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return {
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "content": self.content,
            "round": self.round,
        }


@dataclass
class FocusGroupTranscript:
    """Focus group discussion transcript."""
    topic: str
    moderator: PersonaV2
    participants: List[PersonaV2]
    messages: List[FocusGroupMessage] = field(default_factory=list)
    summary: str = ""
    key_insights: List[str] = field(default_factory=list)
    consensus_points: List[str] = field(default_factory=list)
    disagreement_points: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "moderator": self.moderator.name,
            "participant_count": len(self.participants),
            "participants": [p.name for p in self.participants],
            "messages": [m.to_dict() for m in self.messages],
            "summary": self.summary,
            "key_insights": self.key_insights,
            "consensus_points": self.consensus_points,
            "disagreement_points": self.disagreement_points,
        }


class FocusGroupSimulator:
    """Focus group simulator."""

    MODERATOR_SYSTEM_PROMPT = """You are a professional focus group moderator.
Your responsibilities are:
1. Guide the discussion and ensure every participant has a chance to speak
2. Gently steer the discussion back when it goes off-topic
3. Probe interesting viewpoints to uncover deeper insights
4. Identify consensus points and areas of disagreement
5. Control the discussion pace to ensure completion within the allotted time

Stay neutral and professional. Do not express personal opinions."""

    PARTICIPANT_SYSTEM_PROMPT = """You are participating in a focus group discussion.
Participate in the first person, fully embodying your respondent identity.
Your responses must align with your background, personality, and viewpoints.
You may agree or disagree with others' opinions, but stay authentic.
Do not recite your persona information — express your views directly."""

    def __init__(self):
        pass

    async def simulate(
        self,
        topic: str,
        personas: List[PersonaV2],
        max_rounds: int = 4,
        moderator: Optional[PersonaV2] = None,
    ) -> FocusGroupTranscript:
        """
        Simulate a focus group discussion.

        Args:
            topic: Discussion topic
            personas: Participant personas (recommended 6-10)
            max_rounds: Maximum discussion rounds
            moderator: Moderator (None = auto-generate)

        Returns:
            FocusGroupTranscript: Complete discussion record
        """
        if len(personas) < 2:
            raise ValueError(
                f"Focus group requires at least 2 participants, but got {len(personas)}"
            )

        mod = moderator or self._create_default_moderator()
        transcript = FocusGroupTranscript(
            topic=topic,
            moderator=mod,
            participants=personas,
        )

        # Phase 1: Moderator opening + each person's initial stance
        opening = await self._phase_opening(mod, personas, topic)
        transcript.messages.extend(opening)

        # Phase 2: Multiple rounds of free discussion
        for round_num in range(1, max_rounds + 1):
            round_msgs = await self._phase_discussion(
                mod, personas, topic, transcript, round_num
            )
            transcript.messages.extend(round_msgs)

            # Moderator round summary (every 2 rounds)
            if round_num % 2 == 0:
                summary_msg = await self._generate_round_summary(
                    mod, transcript, topic, round_num
                )
                if summary_msg:
                    transcript.messages.append(summary_msg)

        # Phase 3: Moderator summary + generate minutes
        summary = await self._generate_final_summary(mod, transcript, topic)
        transcript.summary = summary

        consensus, disagreements = await self._extract_insights(mod, transcript, topic)
        transcript.key_insights = consensus[:5]
        transcript.consensus_points = [c for c in consensus if c not in disagreements]
        transcript.disagreement_points = disagreements

        logger.info(
            f"Focus group completed: topic={topic}, participants={len(personas)}, "
            f"messages={len(transcript.messages)}, rounds={max_rounds}"
        )

        return transcript

    # ---------------------------------------------------------------- #
    # Discussion phases
    # ---------------------------------------------------------------- #
    async def _phase_opening(
        self, moderator: PersonaV2, personas: List[PersonaV2], topic: str
    ) -> List[FocusGroupMessage]:
        """Moderator opening + each person's initial stance."""
        messages = []

        # Moderator opening
        opening = await self._llm_call(
            system=self.MODERATOR_SYSTEM_PROMPT,
            prompt=(
                f"Discussion topic: {topic}\n\n"
                f"Participants: {', '.join(p.name for p in personas)}\n\n"
                f"Please open with a brief introduction of the topic, then invite each participant to speak in turn. "
                f"Each person should respond in 1-2 sentences."
            ),
            temperature=0.7,
        )
        if opening:
            messages.append(
                FocusGroupMessage(
                    speaker_id=moderator.persona_id,
                    speaker_name=moderator.name,
                    content=opening,
                    round=0,
                )
            )

        # Each person's initial stance
        for p in personas:
            reply = await self._llm_call(
                system=self.PARTICIPANT_SYSTEM_PROMPT + f"\n\nYour persona:\n{p.to_prompt('interview')}",
                prompt=f"Discussion topic: {topic}\n\nPlease express your first reaction to this topic in under 30 characters.",
                temperature=0.8,
            )
            if reply:
                messages.append(
                    FocusGroupMessage(
                        speaker_id=p.persona_id,
                        speaker_name=p.name,
                        content=reply,
                        round=0,
                    )
                )

        return messages

    async def _phase_discussion(
        self,
        moderator: PersonaV2,
        personas: List[PersonaV2],
        topic: str,
        transcript: FocusGroupTranscript,
        round_num: int,
    ) -> List[FocusGroupMessage]:
        """One round of free discussion."""
        messages = []
        recent = transcript.messages[-max(len(personas) * 2, 6):]
        recent_text = "\n".join(
            f"{m.speaker_name}: {m.content}" for m in recent[-8:]
        )

        for p in personas:
            # Each person speaks based on current discussion progress
            reply = await self._llm_call(
                system=self.PARTICIPANT_SYSTEM_PROMPT + f"\n\nYour persona:\n{p.to_prompt('interview')}",
                prompt=(
                    f"Discussion topic: {topic}\n\n"
                    f"Current discussion progress:\n{recent_text}\n\n"
                    f"Please share your views based on your identity and the current discussion. "
                    f"You may support, counter, or build upon the previous person's point. "
                    f"Limit to 50 characters."
                ),
                temperature=0.9,
            )
            if reply:
                msg = FocusGroupMessage(
                    speaker_id=p.persona_id,
                    speaker_name=p.name,
                    content=reply,
                    round=round_num,
                )
                messages.append(msg)

        return messages

    async def _generate_round_summary(
        self,
        moderator: PersonaV2,
        transcript: FocusGroupTranscript,
        topic: str,
        round_num: int,
    ) -> Optional[FocusGroupMessage]:
        """Moderator interim summary."""
        recent = transcript.messages[-12:]
        recent_text = "\n".join(
            f"{m.speaker_name}: {m.content}" for m in recent
        )

        summary = await self._llm_call(
            system=self.MODERATOR_SYSTEM_PROMPT,
            prompt=(
                f"Discussion topic: {topic}\n\n"
                f"Recent discussion:\n{recent_text}\n\n"
                f"Please provide a brief summary of the above discussion, highlighting emerging consensus and disagreements, then guide the group into the next round. Limit to 60 characters."
            ),
            temperature=0.5,
        )

        if summary:
            return FocusGroupMessage(
                speaker_id=moderator.persona_id,
                speaker_name=moderator.name,
                content=summary,
                round=round_num,
            )
        return None

    # ---------------------------------------------------------------- #
    # Summary
    # ---------------------------------------------------------------- #
    async def _generate_final_summary(
        self, moderator: PersonaV2, transcript: FocusGroupTranscript, topic: str
    ) -> str:
        """Generate final summary."""
        all_text = "\n".join(
            f"{m.speaker_name}: {m.content}" for m in transcript.messages[-20:]
        )

        summary = await self._llm_call(
            system=self.MODERATOR_SYSTEM_PROMPT,
            prompt=(
                f"Discussion topic: {topic}\n\n"
                f"Full discussion record:\n{all_text}\n\n"
                f"Please summarize the entire discussion in under 100 characters."
            ),
            temperature=0.4,
        )
        return summary or "Discussion concluded."

    async def _extract_insights(
        self,
        moderator: PersonaV2,
        transcript: FocusGroupTranscript,
        topic: str,
    ) -> Tuple[List[str], List[str]]:
        """Extract consensus points and disagreements."""
        all_text = "\n".join(
            f"{m.speaker_name}: {m.content}" for m in transcript.messages
        )

        result = await self._llm_call(
            system=self.MODERATOR_SYSTEM_PROMPT,
            prompt=(
                f"Discussion topic: {topic}\n\n"
                f"Full discussion record:\n{all_text}\n\n"
                f"Please analyze the above discussion and output in JSON format:\n"
                f'{{"consensus": ["consensus1", "consensus2"], "disagreements": ["disagreement1", "disagreement2"]}}'
            ),
            temperature=0.3,
        )

        if result:
            try:
                # Extract JSON
                match = re.search(r'\{.*\}', result, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    return data.get("consensus", []), data.get("disagreements", [])
            except Exception:
                pass

        return [], []

    # ---------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------- #
    def _create_default_moderator(self) -> PersonaV2:
        """Create a default moderator."""
        return PersonaV2(
            persona_id="moderator_001",
            persona_type=PersonaType.HYBRID,
            name="Moderator",
            age=40,
            gender="Female",
            city="Beijing",
            occupation="Market Research Director",
            education="Master's",
            personality_traits=["Neutral", "Professional", "Skilled at facilitating", "Insightful"],
            decision_style="Rational",
        )

    async def _llm_call(
        self, system: str, prompt: str, temperature: float = 0.7
    ) -> Optional[str]:
        """LLM call (no retry — a single failure in focus group does not affect the whole)."""
        try:
            result = await asyncio.wait_for(
                call_llm(
                    prompt=prompt,
                    system_prompt=system,
                    temperature=temperature,
                    max_tokens=256,
                ),
                timeout=15,
            )
            if result.get("success") and result.get("content"):
                return result["content"].strip()
        except Exception as e:
            logger.debug(f"Focus group LLM call failed: {e}")
        return None
