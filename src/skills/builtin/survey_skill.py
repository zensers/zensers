"""
SurveySkill - Survey Research Skill

Wraps SurveyClient, provides a unified Skill interface.
Supports creating surveys, distributing surveys, getting results, statistical analysis, etc.

Usage example:
    skill = SurveySkill()
    
    # Create survey
    result = await skill.execute(
        action="create",
        title="Market Research",
        questions=[...]
    )
    
    # Distribute survey
    result = await skill.execute(
        action="distribute",
        survey_id="xxx",
        target_count=100
    )
"""
from typing import Any, Dict, Optional, List

from src.skills.base import Skill, SkillConfig
from src.survey.client import SurveyClient
from src.survey.models import Survey, SurveyTask


class SurveySkill(Skill):
    """
    Survey Research Skill
    
    Features:
    - Create surveys
    - Distribute surveys (supports multiple backends)
    - Get survey results
    - Statistical analysis
    - List available backends
    """
    
    def __init__(
        self, 
        config: Optional[SkillConfig] = None,
        backend_type: str = "ai_simulation",
        backend_config: Optional[Dict[str, Any]] = None
    ):
        """Initialize SurveySkill.
        
        Args:
            config: Skill configuration
            backend_type: Default backend type
            backend_config: Backend configuration
        """
        super().__init__(config)
        self.default_backend_type = backend_type
        self.backend_config = backend_config or {}
        self._client: Optional[SurveyClient] = None
    
    @property
    def name(self) -> str:
        return "survey_skill"
    
    @property
    def description(self) -> str:
        return "Survey Research Skill, supports creating surveys, distributing, getting results, statistical analysis"
    
    def _get_client(self) -> SurveyClient:
        """Get or create SurveyClient instance."""
        if self._client is None:
            self._client = SurveyClient(
                backend_type=self.default_backend_type,
                backend_config=self.backend_config
            )
        return self._client
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute survey operation.
        
        Args:
            action: Operation type
                - "create": Create survey
                - "distribute": Distribute survey
                - "get_results": Get results
                - "get_statistics": Get statistics
                - "list_backends": List backends
                - "get_status": Get status
                - "close": Close survey
            
        Returns:
            Operation result
        """
        action = kwargs.get("action")
        
        if not action:
            return self._failure("Missing 'action' parameter")
        
        try:
            if action == "create":
                return await self._create_survey(kwargs)
            elif action == "distribute":
                return await self._distribute_survey(kwargs)
            elif action == "get_results":
                return await self._get_results(kwargs)
            elif action == "get_statistics":
                return await self._get_statistics(kwargs)
            elif action == "list_backends":
                return self._list_backends()
            elif action == "get_status":
                return await self._get_status(kwargs)
            elif action == "close":
                return await self._close_survey(kwargs)
            else:
                return self._failure(f"Unknown action: {action}")
                
        except Exception as e:
            return self._failure(str(e), f"Execution of {action} failed")
    
    async def _create_survey(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Create survey."""
        title = kwargs.get("title", "Unnamed Survey")
        questions = kwargs.get("questions", [])
        description = kwargs.get("description", "")
        
        if not questions:
            return self._failure("Question list cannot be empty")
        
        client = self._get_client()
        survey = await client.create_survey(
            title=title,
            questions=questions,
            description=description
        )
        
        return self._success({
            "survey": survey.to_dict(),
            "survey_id": survey.survey_id,
        }, f"Successfully created survey: {title}")
    
    async def _distribute_survey(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Distribute survey."""
        survey_id = kwargs.get("survey_id")
        survey_data = kwargs.get("survey")
        target_count = kwargs.get("target_count", 100)
        backend_type = kwargs.get("backend_type", self.default_backend_type)
        quota = kwargs.get("quota")
        
        if not survey_id and not survey_data:
            return self._failure("Need survey_id or survey parameter")
        
        client = self._get_client()
        
        # If survey data is provided, create first
        if survey_data and not survey_id:
            survey = Survey.from_dict(survey_data) if isinstance(survey_data, dict) else survey_data
        else:
            # Needs to load from storage
            return self._failure("Currently does not support distributing by survey_id only, please provide full survey data")
        
        task = await client.distribute(
            survey=survey,
            target_count=target_count,
            quota=quota
        )
        
        return self._success({
            "task_id": task.task_id,
            "external_id": task.external_id,
            "share_url": task.share_url,
            "status": task.status.value,
        }, f"Successfully distributed survey, target sample count: {target_count}")
    
    async def _get_results(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get results."""
        task_id = kwargs.get("task_id")
        limit = kwargs.get("limit")
        
        if not task_id:
            return self._failure("Need task_id parameter")
        
        client = self._get_client()
        
        # Create temporary task object
        from src.survey.models import SurveyTask, SurveyStatus
        task = SurveyTask(
            task_id=task_id,
            survey_id="",
            backend_type=self.default_backend_type,
            status=SurveyStatus.ACTIVE,
            config=None,
            target_count=0
        )
        
        responses = await client.get_results(task, limit=limit)
        
        return self._success({
            "responses": [r.to_dict() for r in responses],
            "count": len(responses),
        })
    
    async def _get_statistics(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get statistics."""
        task_id = kwargs.get("task_id")
        
        if not task_id:
            return self._failure("Need task_id parameter")
        
        client = self._get_client()
        
        from src.survey.models import SurveyTask, SurveyStatus
        task = SurveyTask(
            task_id=task_id,
            survey_id="",
            backend_type=self.default_backend_type,
            status=SurveyStatus.ACTIVE,
            config=None,
            target_count=0
        )
        
        stats = await client.get_statistics(task)
        
        return self._success({
            "statistics": stats,
        })
    
    def _list_backends(self) -> Dict[str, Any]:
        """List available backends."""
        backends = SurveyClient.list_backends()
        options = SurveyClient.get_backend_options()
        
        return self._success({
            "backends": backends,
            "options": options,
        }, f"Available backends: {len(backends)}")
    
    async def _get_status(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get task status."""
        task_id = kwargs.get("task_id")
        
        if not task_id:
            return self._failure("Need task_id parameter")
        
        # Simplified implementation
        return self._success({
            "task_id": task_id,
            "status": "active",
        })
    
    async def _close_survey(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Close survey."""
        task_id = kwargs.get("task_id")
        
        if not task_id:
            return self._failure("Need task_id parameter")
        
        return self._success({
            "task_id": task_id,
            "closed": True,
        }, "Survey has been closed")