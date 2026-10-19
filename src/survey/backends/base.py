"""
Abstract Survey Backend Interface

All concrete survey implementations (API, AI simulation, crowdsourcing) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..models import (
    Survey, SurveyResponse, SurveyStatus,
    DistributionConfig, SurveyTask
)


class SurveyBackend(ABC):
    """
    Abstract Survey Backend Interface

    All concrete survey implementations (API, AI simulation, crowdsourcing) must implement this interface.
    This ensures that front-end code can uniformly handle different types of backends.
    """

    # ============== Metadata ==============

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """
        Backend type identifier

        Returns:
            e.g. 'api_tencent', 'api_wenjuanxing', 'ai_simulation', etc.
        """
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """
        Backend display name

        Returns:
            e.g. 'Tencent Survey', 'WJX', 'AI Simulated Respondent', etc.
        """
        pass

    @property
    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """
        Backend capabilities

        Returns:
            {
                "quota_control": True,      # Whether quota control is supported
                "pause_resume": True,       # Whether pause/resume is supported
                "webhook": True,            # Whether webhook is supported
                "real_time_status": True,   # Whether real-time status is supported
                "incentive": True,          # Whether incentives are supported
            }
        """
        pass

    # ============== Survey Operations ==============

    async def create_survey(self, survey: Survey) -> str:
        """
        Create a survey

        Args:
            survey: Survey object

        Returns:
            External survey ID (third-party platform survey ID)

        Raises:
            SurveyCreationError: Creation failed

        Note:
            Some backends (e.g. WJX) may not support API creation,
            you need to manually create them and use the external_id parameter
        """
        # Default implementation: some backends do not support creation
        raise NotImplementedError(f"{self.backend_name} does not support creating surveys via API")

    async def update_survey(self, external_id: str, survey: Survey) -> bool:
        """
        Update a survey

        Args:
            external_id: External survey ID
            survey: Updated survey object

        Returns:
            Whether successful
        """
        raise NotImplementedError(f"{self.backend_name} does not support updating surveys")

    async def delete_survey(self, external_id: str) -> bool:
        """
        Delete a survey

        Args:
            external_id: External survey ID

        Returns:
            Whether successful
        """
        raise NotImplementedError(f"{self.backend_name} does not support deleting surveys")

    # ============== Distribution Operations ==============

    @abstractmethod
    async def distribute(
        self,
        external_id: str,
        config: DistributionConfig
    ) -> str:
        """
        Distribute a survey

        Args:
            external_id: External survey ID
            config: Distribution configuration

        Returns:
            Distribution link (can be shared)

        Raises:
            DistributionError: Distribution failed
        """
        pass

    async def pause(self, external_id: str) -> bool:
        """
        Pause collection

        Args:
            external_id: External survey ID

        Returns:
            Whether successful
        """
        if not self.capabilities.get("pause_resume", False):
            raise NotImplementedError(f"{self.backend_name} does not support pause/resume")
        raise NotImplementedError()

    async def resume(self, external_id: str) -> bool:
        """
        Resume collection

        Args:
            external_id: External survey ID

        Returns:
            Whether successful
        """
        if not self.capabilities.get("pause_resume", False):
            raise NotImplementedError(f"{self.backend_name} does not support pause/resume")
        raise NotImplementedError()

    async def close(self, external_id: str) -> bool:
        """
        Close collection

        Args:
            external_id: External survey ID

        Returns:
            Whether successful
        """
        raise NotImplementedError(f"{self.backend_name} does not support closing collection")

    # ============== Status Query ==============

    @abstractmethod
    async def get_status(self, external_id: str) -> SurveyStatus:
        """
        Get survey status

        Args:
            external_id: External survey ID

        Returns:
            Current status
        """
        pass

    async def get_statistics(self, external_id: str) -> Dict[str, Any]:
        """
        Get statistics

        Args:
            external_id: External survey ID

        Returns:
            {
                "total_views": 1000,        # Total views
                "total_starts": 500,        # Total starts
                "total_completes": 450,     # Total completes
                "completion_rate": 0.90,    # Completion rate
                "avg_duration": 300,        # Average duration (seconds)
            }
        """
        raise NotImplementedError(f"{self.backend_name} does not support getting statistics")

    # ============== Result Retrieval ==============

    @abstractmethod
    async def get_results(
        self,
        external_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SurveyResponse]:
        """
        Get survey results

        Args:
            external_id: External survey ID
            limit: Maximum number of results
            offset: Offset (pagination)

        Returns:
            List of responses
        """
        pass

    async def export_results(
        self,
        external_id: str,
        format: str = "csv"  # "csv", "xlsx", "json"
    ) -> bytes:
        """
        Export results

        Args:
            external_id: External survey ID
            format: Export format

        Returns:
            File content (bytes)
        """
        raise NotImplementedError(f"{self.backend_name} does not support exporting results")

    # ============== Webhook Handling ==============

    async def handle_webhook(self, event: Dict[str, Any]) -> bool:
        """
        Handle webhook callback

        Args:
            event: Callback event data

        Returns:
            Whether processing was successful

        Note:
            Default implementation returns False, subclasses can override
        """
        return False

    # ============== Helper Methods ==============

    def get_info(self) -> Dict[str, Any]:
        """Get backend information"""
        return {
            "type": self.backend_type,
            "name": self.backend_name,
            "capabilities": self.capabilities,
        }
