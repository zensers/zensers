"""
Survey Client

Provides a concise API for users.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from .models import (
    Survey, SurveyResponse, SurveyStatus,
    DistributionConfig, SurveyTask
)
from .backends.factory import BackendFactory
from .task_manager import SurveyTaskManager


class SurveyClient:
    """Survey Client"""
    
    def __init__(
        self,
        backend_type: str = "api_tencent",
        backend_config: Optional[Dict[str, Any]] = None,
        task_manager: Optional[SurveyTaskManager] = None
    ):
        """
        Initialize client
        
        Args:
            backend_type: Backend type
            backend_config: Backend configuration
            task_manager: Task manager
        """
        self.backend_type = backend_type
        self.backend_config = backend_config or {}
        self.task_manager = task_manager or SurveyTaskManager()
        self._backend = None
    
    @property
    def backend(self):
        """Lazy-load backend"""
        if self._backend is None:
            self._backend = BackendFactory.get_or_create(
                self.backend_type,
                **self.backend_config
            )
        return self._backend
    
    async def create_survey(
        self,
        title: str,
        questions: List[Dict[str, Any]],
        description: str = ""
    ) -> Survey:
        """
        Create survey
        
        Args:
            title: Survey title
            questions: Question list
            description: Survey description
            
        Returns:
            Survey object
        """
        from .models import Question, QuestionType, QuestionOption
        
        survey_id = f"survey_{uuid.uuid4().hex[:8]}"
        
        # Parse questions
        q_list = []
        for i, q_data in enumerate(questions):
            q_id = q_data.get("id", f"q_{i+1}")
            q_text = q_data.get("text", "")
            q_type = QuestionType(q_data.get("type", "single_choice"))
            q_options = None
            
            if q_data.get("options"):
                q_options = [
                    QuestionOption(
                        option_id=f"opt_{i}_{j}",
                        text=opt
                    )
                    for j, opt in enumerate(q_data["options"])
                ]
            
            q_list.append(Question(
                question_id=q_id,
                text=q_text,
                question_type=q_type,
                options=q_options,
                required=q_data.get("required", True),
                description=q_data.get("description"),
            ))
        
        return Survey(
            survey_id=survey_id,
            title=title,
            description=description,
            questions=q_list,
        )
    
    async def distribute(
        self,
        survey: Survey,
        target_count: int = 100,
        quota: Optional[Dict[str, Dict[str, int]]] = None,
        deadline: Optional[datetime] = None
    ) -> SurveyTask:
        """
        Distribute survey
        
        Args:
            survey: Survey object
            target_count: Target sample count
            quota: Quota settings
            deadline: Deadline
            
        Returns:
            Survey task
        """
        from .models import QuotaConfig
        
        # Create task
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        quota_config = None
        if quota:
            quota_config = QuotaConfig(dimensions=quota, target_count=target_count)
        
        config = DistributionConfig(
            target_count=target_count,
            quota=quota_config,
            deadline=deadline,
        )
        
        task = await self.task_manager.create_task(
            task_id=task_id,
            survey_id=survey.survey_id,
            backend_type=self.backend_type,
            config=config
        )
        
        try:
            # Call backend to create survey
            external_id = await self.backend.create_survey(survey)
            
            # Distribute survey
            share_url = await self.backend.distribute(external_id, config)
            
            # Update task status
            await self.task_manager.start_task(task_id, external_id, share_url)
            task.external_id = external_id
            task.share_url = share_url
            task.status = SurveyStatus.ACTIVE
            
        except Exception as e:
            # Close backend connection to prevent leaks
            if self._backend and hasattr(self._backend, 'close'):
                try:
                    await self._backend.close()
                except Exception as close_err:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to close backend after error: {close_err}"
                    )
                self._backend = None
            
            await self.task_manager.fail_task(task_id, str(e))
            task.status = SurveyStatus.FAILED
            task.error_message = str(e)
        
        return task
    
    async def get_status(self, task: SurveyTask) -> SurveyStatus:
        """Get task status"""
        if task.external_id:
            return await self.backend.get_status(task.external_id)
        return task.status
    
    async def get_results(
        self,
        task: SurveyTask,
        limit: Optional[int] = None
    ) -> List[SurveyResponse]:
        """Get survey results"""
        if not task.external_id:
            return []
        
        return await self.backend.get_results(
            task.external_id,
            limit=limit
        )
    
    async def close(self, task: SurveyTask) -> bool:
        """Stop collection"""
        if task.external_id:
            return await self.backend.close(task.external_id)
        return False
    
    async def get_statistics(self, task: SurveyTask) -> Dict[str, Any]:
        """Get statistics"""
        if task.external_id:
            return await self.backend.get_statistics(task.external_id)
        return {}
    
    @staticmethod
    def list_backends() -> List[Dict[str, Any]]:
        """List all available backends"""
        return BackendFactory.list_available()
    
    @staticmethod
    def get_backend_options() -> Dict[str, Dict[str, Any]]:
        """Get backend options info"""
        return {
            "api_tencent": {
                "name": "Tencent Survey",
                "type": "Third-party platform",
                "pros": ["Real respondents", "High data quality", "Complete API"],
                "cons": ["Premium plan required", "Paid features"],
                "cost": "Premium subscription",
                "duration": "3-7 days",
            },
            "ai_simulation": {
                "name": "AI Simulated Respondents",
                "type": "AI Generated",
                "pros": ["Low cost", "Fast speed", "Unlimited samples"],
                "cons": ["Needs calibration", "Exploratory use"],
                "cost": "LLM API Cost",
                "duration": "Minutes",
            },
        }