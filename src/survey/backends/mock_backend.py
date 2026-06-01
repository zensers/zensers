"""
Mock Survey Backend

For development testing, no real API credentials required.
"""

import random
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from .base import SurveyBackend
from ..models import (
    Survey, SurveyResponse, SurveyStatus,
    DistributionConfig, Answer, QuestionType
)


class MockSurveyBackend(SurveyBackend):
    """Mock Survey Backend - For Development Testing"""

    def __init__(self, response_delay: float = 0.1):
        """
        Initialize Mock Backend

        Args:
            response_delay: Simulated response delay (seconds)
        """
        self.response_delay = response_delay
        self._surveys: Dict[str, Survey] = {}
        self._responses: Dict[str, List[SurveyResponse]] = {}
        self._links: Dict[str, str] = {}

    @property
    def backend_type(self) -> str:
        return "mock"

    @property
    def backend_name(self) -> str:
        return "Mock Survey (Testing)"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "quota_control": True,
            "pause_resume": True,
            "webhook": True,
            "real_time_status": True,
            "incentive": True,
        }

    async def _simulate_delay(self):
        """Simulate network delay"""
        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)

    # ============== Survey Operations ==============

    async def create_survey(self, survey: Survey) -> str:
        """Create survey"""
        await self._simulate_delay()

        # Generate external ID
        external_id = f"mock_{uuid.uuid4().hex[:8]}"

        # Store survey
        self._surveys[external_id] = survey
        self._responses[external_id] = []

        # Generate mock link
        self._links[external_id] = f"https://mock-survey.example.com/s/{external_id}"

        return external_id

    async def update_survey(self, external_id: str, survey: Survey) -> bool:
        """Update survey"""
        await self._simulate_delay()

        if external_id in self._surveys:
            self._surveys[external_id] = survey
            return True
        return False

    async def delete_survey(self, external_id: str) -> bool:
        """Delete survey"""
        await self._simulate_delay()

        if external_id in self._surveys:
            del self._surveys[external_id]
            del self._responses[external_id]
            del self._links[external_id]
            return True
        return False

    # ============== Distribution Operations ==============

    async def distribute(
        self,
        external_id: str,
        config: DistributionConfig
    ) -> str:
        """Distribute survey"""
        await self._simulate_delay()

        if external_id not in self._surveys:
            raise Exception(f"Survey does not exist: {external_id}")

        # Return mock link
        return self._links.get(external_id, "")

    async def pause(self, external_id: str) -> bool:
        """Pause collection"""
        await self._simulate_delay()
        return True

    async def resume(self, external_id: str) -> bool:
        """Resume collection"""
        await self._simulate_delay()
        return True

    async def close(self, external_id: str) -> bool:
        """Close collection"""
        await self._simulate_delay()
        return True

    # ============== Status Queries ==============

    async def get_status(self, external_id: str) -> SurveyStatus:
        """Get survey status"""
        await self._simulate_delay()

        if external_id not in self._surveys:
            return SurveyStatus.FAILED

        # Return status based on response count
        responses = self._responses.get(external_id, [])
        if len(responses) >= 100:
            return SurveyStatus.COMPLETED

        return SurveyStatus.ACTIVE

    async def get_statistics(self, external_id: str) -> Dict[str, Any]:
        """Get statistics"""
        await self._simulate_delay()

        responses = self._responses.get(external_id, [])

        return {
            "total_views": len(responses) * 3,
            "total_starts": len(responses) * 2,
            "total_completes": len(responses),
            "completion_rate": 0.67,
            "avg_duration": random.randint(60, 300),
        }

    # ============== Result Retrieval ==============

    async def get_results(
        self,
        external_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SurveyResponse]:
        """Get survey results"""
        await self._simulate_delay()

        if external_id not in self._responses:
            return []

        responses = self._responses[external_id]

        # Apply pagination
        start = offset or 0
        end = start + limit if limit else None

        return responses[start:end]

    # ============== Mock Data Generation ==============

    async def generate_mock_responses(
        self,
        external_id: str,
        count: int = 10
    ) -> List[SurveyResponse]:
        """
        Generate mock responses

        Args:
            external_id: Survey external ID
            count: Number to generate
        """
        await self._simulate_delay()

        if external_id not in self._surveys:
            raise Exception(f"Survey does not exist: {external_id}")

        survey = self._surveys[external_id]
        responses = []

        for i in range(count):
            response = self._generate_single_response(survey, i)
            responses.append(response)
            self._responses[external_id].append(response)

        return responses

    def _generate_single_response(
        self,
        survey: Survey,
        index: int
    ) -> SurveyResponse:
        """Generate a single mock response"""

        response_id = f"mock_resp_{uuid.uuid4().hex[:8]}"
        answers: Dict[str, Answer] = {}

        # Generate answers for each question
        for question in survey.questions:
            answer = self._generate_answer(question)
            answers[question.question_id] = answer

        # Randomly generate timestamp
        completed_at = datetime.now() - timedelta(
            minutes=random.randint(1, 60),
            seconds=random.randint(0, 59)
        )

        return SurveyResponse(
            response_id=response_id,
            survey_id=survey.survey_id,
            respondent_id=f"mock_user_{index}",
            answers=answers,
            completed_at=completed_at,
            duration_seconds=random.randint(30, 300),
            quality_score=random.uniform(0.7, 1.0),
            is_valid=True,
            demographics={
                "age": random.randint(18, 60),
                "gender": random.choice(["Male", "Female"]),
                "city": random.choice(["Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou"]),
            },
            source_ip=f"192.168.{
                random.randint(
                    1, 255)}.{
                random.randint(
                    1, 255)}",
        )

    def _generate_answer(self, question: Any) -> Answer:
        """Generate answer based on question type"""

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
            scale_min = question.validation_rules.get("scale_min", 1)
            scale_max = question.validation_rules.get("scale_max", 5)
            return Answer(
                question_id=question.question_id,
                answer_value=random.randint(scale_min, scale_max),
            )

        elif question.question_type == QuestionType.YES_NO:
            # Yes/No question
            return Answer(
                question_id=question.question_id,
                answer_value=random.choice(["Yes", "No"]),
            )

        elif question.question_type == QuestionType.OPEN_ENDED:
            # Open-ended question
            templates = [
                "I think this is a great product, hope to see continued improvements.",
                "Overall pretty good, but there is room for improvement.",
                "Very satisfied, would recommend to friends.",
                "Average, nothing special.",
                "Not very satisfied, hope it can be improved.",
            ]
            return Answer(
                question_id=question.question_id,
                answer_value=random.choice(templates),
                answer_text=random.choice(templates),
            )

        elif question.question_type == QuestionType.DROPDOWN:
            # Dropdown question
            if question.options:
                selected = random.choice(question.options)
                return Answer(
                    question_id=question.question_id,
                    answer_value=selected.text,
                )

        elif question.question_type == QuestionType.RANKING:
            # Ranking question
            if question.options:
                shuffled = list(question.options)
                random.shuffle(shuffled)
                return Answer(
                    question_id=question.question_id,
                    answer_value=",".join([opt.text for opt in shuffled]),
                )

        # Default
        return Answer(
            question_id=question.question_id,
            answer_value="",
        )

    # ============== Cleanup ==============

    def clear_all(self):
        """Clear all mock data"""
        self._surveys.clear()
        self._responses.clear()
        self._links.clear()

    def get_survey_count(self) -> int:
        """Get survey count"""
        return len(self._surveys)

    def get_response_count(self, external_id: str) -> int:
        """Get response count"""
        return len(self._responses.get(external_id, []))
