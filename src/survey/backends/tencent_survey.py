"""
Tencent Survey API Backend Implementation

Official documentation: https://wj.qq.com/docs/openapi/
Version requirement: Premium (paid feature)

Configuration system integration:
- Can read configuration from settings.platforms.tencent_survey
- Supports environment variable override
"""

import httpx
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import logging

from .base import SurveyBackend
from ..models import (
    Survey, SurveyResponse, SurveyStatus,
    DistributionConfig, Answer, QuestionType
)

# Configuration system
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TencentSurveyConfig:
    """Tencent Survey Configuration"""
    appid: str                              # App ID
    secret: str                             # App Secret
    access_token: str                       # Access Token
    org_id: int                             # Org ID
    user_id: int                            # User ID
    base_url: str = "https://wj.qq.com/api"  # API Base URL


class TencentSurveyBackend(SurveyBackend):
    """Tencent Survey API Backend"""

    def __init__(self, config: TencentSurveyConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-loaded HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0
            )
        return self._client

    @property
    def backend_type(self) -> str:
        return "api_tencent"

    @property
    def backend_name(self) -> str:
        return "Tencent Survey"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "quota_control": True,
            "pause_resume": False,
            "webhook": True,
            "real_time_status": True,
            "incentive": False,
        }

    def _get_params(self) -> Dict[str, str]:
        """Get authentication parameters"""
        return {
            "appid": self.config.appid,
            "access_token": self.config.access_token
        }

    # ============== Survey Operations ==============

    async def create_survey(self, survey: Survey) -> str:
        """Create survey"""
        # Convert to Tencent Survey text format
        text = self._convert_to_text_format(survey)

        payload = {
            "org": self.config.org_id,
            "user_id": self.config.user_id,
            "text": text
        }

        response = await self.client.post(
            "/api/surveys",
            params=self._get_params(),
            json=payload
        )

        data = response.json()

        if data.get("code") != "OK":
            error_type = data.get("error", {}).get("type", "unknown")
            raise Exception(f"Failed to create survey: {error_type}")

        return str(data["data"]["survey_id"])

    async def get_survey_url(self, external_id: str) -> str:
        """Get survey URL"""
        response = await self.client.get(
            f"/api/surveys/{external_id}/url",
            params=self._get_params()
        )

        data = response.json()

        if data.get("code") != "OK":
            raise Exception("Failed to get survey URL")

        return data["data"]["url"]

    # ============== Distribution Operations ==============

    async def distribute(
        self,
        external_id: str,
        config: DistributionConfig
    ) -> str:
        """Distribute survey - Return survey URL"""
        # Tencent Survey is automatically accessible after creation, return URL
        return await self.get_survey_url(external_id)

    async def close(self, external_id: str) -> bool:
        """Close collection"""
        response = await self.client.put(
            f"/api/surveys/{external_id}/settings",
            params=self._get_params(),
            json={"status": "closed"}
        )

        data = response.json()
        return data.get("code") == "OK"

    # ============== Status Queries ==============

    async def get_status(self, external_id: str) -> SurveyStatus:
        """Get survey status"""
        response = await self.client.get(
            f"/api/surveys/{external_id}",
            params=self._get_params()
        )

        data = response.json()

        if data.get("code") != "OK":
            return SurveyStatus.FAILED

        survey_data = data.get("data", {})
        status_str = survey_data.get("status", "active")

        status_map = {
            "draft": SurveyStatus.DRAFT,
            "active": SurveyStatus.ACTIVE,
            "paused": SurveyStatus.PAUSED,
            "closed": SurveyStatus.COMPLETED,
        }

        return status_map.get(status_str, SurveyStatus.ACTIVE)

    async def get_statistics(self, external_id: str) -> Dict[str, Any]:
        """Get statistics"""
        response = await self.client.get(
            f"/api/surveys/{external_id}/report/overview",
            params=self._get_params()
        )

        data = response.json()

        if data.get("code") != "OK":
            return {}

        return data.get("data", {})

    # ============== Result Retrieval ==============

    async def get_results(
        self,
        external_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SurveyResponse]:
        """Get survey results"""
        responses = []
        last_answer_id = 0
        per_page = min(limit or 100, 100)
        collected = 0

        while True:
            params = {
                **self._get_params(),
                "per_page": per_page,
                "last_answer_id": last_answer_id
            }

            response = await self.client.get(
                f"/api/surveys/{external_id}/answers",
                params=params
            )

            data = response.json()

            if data.get("code") != "OK":
                break

            answer_list = data.get("data", {}).get("list", [])

            if not answer_list:
                break

            for ans in answer_list:
                survey_response = self._convert_response(ans, external_id)
                responses.append(survey_response)
                collected += 1

                if limit and collected >= limit:
                    return responses

            last_answer_id = data.get("data", {}).get("last_answer_id", 0)

            if not last_answer_id:
                break

        return responses

    # ============== Conversion Methods ==============

    def _convert_to_text_format(self, survey: Survey) -> str:
        """Convert to Tencent Survey text format"""
        lines = [survey.title]

        if survey.description:
            lines.append("")
            lines.append(survey.description)

        for q in survey.questions:
            lines.append("")

            # Question title
            title = q.text

            # Question type mapping
            type_map = {
                QuestionType.SINGLE_CHOICE: "Single Choice",
                QuestionType.MULTIPLE_CHOICE: "Multiple Choice",
                QuestionType.DROPDOWN: "Dropdown",
                QuestionType.OPEN_ENDED: "Single-line Text",
                QuestionType.LIKERT: "Likert Scale",
                QuestionType.SCALE: "Scale",
                QuestionType.RANKING: "Ranking",
                QuestionType.MATRIX: "Matrix Single Choice",
            }

            q_type = type_map.get(q.question_type, "Single-line Text")
            title += f"[{q_type}]"

            # Add description
            if q.description:
                title += f"({q.description})"

            lines.append(title)

            # Options
            if q.options:
                for opt in q.options:
                    lines.append(opt.text)

            # Scale range
            if q.question_type in [QuestionType.LIKERT, QuestionType.SCALE]:
                scale_range = q.validation_rules.get("scale_range", "1~5")
                lines.append(scale_range)

        return "\n".join(lines)

    def _convert_response(
        self,
        raw_data: Dict[str, Any],
        survey_id: str
    ) -> SurveyResponse:
        """Convert Tencent Survey response to unified format"""
        response_id = str(raw_data.get("answer_id", ""))

        answers: Dict[str, Answer] = {}

        # Parse answer content
        answer_pages = raw_data.get("answer", [])

        for page in answer_pages:
            questions = page.get("questions", [])

            for q in questions:
                question_id = q.get("id", "")
                q_type = q.get("type", "")

                # Parse answer based on question type
                if q_type in ["radio", "select", "checkbox"]:
                    # Choice questions
                    options = q.get("options", [])
                    selected = [opt.get("text", "")
                                for opt in options if opt.get("checked")]
                    answer_value = ",".join(selected) if selected else ""

                    answers[question_id] = Answer(
                        question_id=question_id,
                        answer_value=answer_value,
                    )

                elif q_type in ["text", "textarea"]:
                    # Text questions
                    answers[question_id] = Answer(
                        question_id=question_id,
                        answer_value=q.get("text", ""),
                        answer_text=q.get("text", ""),
                    )

                elif q_type in ["star", "nps"]:
                    # Scale questions
                    answers[question_id] = Answer(
                        question_id=question_id,
                        answer_value=int(q.get("text", "0")),
                    )

                elif q_type == "matrix_radio":
                    # Matrix single choice
                    groups = q.get("groups", [])
                    matrix_answers = {}
                    for g in groups:
                        g_id = g.get("id", "")
                        opts = g.get("options", [])
                        selected = [opt.get("text", "")
                                    for opt in opts if opt.get("checked")]
                        matrix_answers[g_id] = selected[0] if selected else ""

                    answers[question_id] = Answer(
                        question_id=question_id,
                        answer_value=matrix_answers,
                    )

        # Parse time
        started_at = raw_data.get("started_at", "")
        ended_at = raw_data.get("ended_at", "")
        duration = raw_data.get("duration", 0)

        return SurveyResponse(
            response_id=response_id,
            survey_id=survey_id,
            respondent_id=str(raw_data.get("respondent_id", "")),
            answers=answers,
            completed_at=datetime.fromisoformat(
                ended_at) if ended_at else datetime.now(),
            duration_seconds=duration,
            source_ip=raw_data.get("ip", ""),
            demographics={
                "country": raw_data.get("country"),
                "province": raw_data.get("province"),
                "city": raw_data.get("city"),
            } if raw_data.get("country") else None,
        )

    async def close_client(self):
        """Close HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - Ensure client is closed"""
        await self.close_client()
        return False


def create_tencent_config_from_settings() -> Optional[TencentSurveyConfig]:
    """
    Create Tencent Survey config from settings.

    Reads configuration from settings.platforms.tencent_survey.
    Returns None if config is unavailable or disabled.

    Returns:
        Configured TencentSurveyConfig instance, or None
    """
    if not SETTINGS_AVAILABLE:
        logger.warning("Configuration system unavailable, cannot create Tencent Survey config")
        return None

    if "tencent_survey" not in settings.platforms:
        logger.info("tencent_survey config not found in configuration system")
        return None

    platform_config = settings.platforms["tencent_survey"]

    if not platform_config.enabled:
        logger.info("Tencent Survey platform not enabled")
        return None

    # Check required configuration
    if not platform_config.app_id or not platform_config.app_secret:
        logger.warning("Tencent Survey config missing app_id or app_secret")
        return None

    return TencentSurveyConfig(
        appid=platform_config.app_id,
        secret=platform_config.app_secret,
        access_token=platform_config.secret,  # Uses secret as access_token
        org_id=int(
            platform_config.webhook) if platform_config.webhook.isdigit() else 0,
        user_id=0,  # Needs to be obtained from config or other sources
        base_url=platform_config.api_url or "https://wj.qq.com/api",
    )


def create_tencent_backend_from_settings() -> Optional[TencentSurveyBackend]:
    """
    Create Tencent Survey backend instance from settings.

    Returns:
        Configured TencentSurveyBackend instance, or None
    """
    config = create_tencent_config_from_settings()
    if config:
        logger.info("Successfully created Tencent Survey backend from configuration system")
        return TencentSurveyBackend(config)
    return None
