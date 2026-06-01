# -*- coding: utf-8 -*-
"""
Preview Revision Workflow
=========================

Orchestrates the preview-revision loop, providing a unified workflow entry point.

Design doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/PHASE8_DEVELOPMENT_PLAN.md
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..adjustment.revision_handler import (
    RevisionHandler,
    RevisionRequest,
    RevisionResult,
)
from ..preview.preview_generator import PreviewGenerator, PreviewResult

logger = logging.getLogger(__name__)

# Constants
MAX_REVISION_ROUNDS = 10
DEFAULT_PREVIEW_FORMAT = "html"


class WorkflowStatus(str, Enum):
    """Workflow status"""
    IDLE = "idle"
    PREVIEWING = "previewing"
    WAITING_FEEDBACK = "waiting_feedback"
    REVISING = "revising"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class WorkflowState:
    """Workflow state"""
    loop_id: str
    task_id: str
    document_path: str
    status: WorkflowStatus = WorkflowStatus.IDLE
    current_round: int = 0
    max_rounds: int = MAX_REVISION_ROUNDS
    preview_result: Optional[PreviewResult] = None
    last_revision: Optional[RevisionResult] = None
    revision_history: List[RevisionResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "document_path": self.document_path,
            "status": self.status.value,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "preview_result": self.preview_result.to_dict() if self.preview_result else None,
            "last_revision": self.last_revision.to_dict() if self.last_revision else None,
            "revision_count": len(self.revision_history),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
        }


@dataclass
class FeedbackRequest:
    """User feedback request"""
    accepted: bool
    revision_type: Optional[str] = None
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    keywords: Optional[List[str]] = None
    user_feedback: Optional[str] = None
    target_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PreviewRevisionWorkflow:
    """
    Preview Revision Workflow
    
    Orchestrates the preview-revision loop, supporting:
    1. Generate preview
    2. Wait for user feedback
    3. Execute revision
    4. Loop until confirmed or limit reached
    
    Usage example:
        workflow = PreviewRevisionWorkflow()
        
        # Start workflow
        state = workflow.start(
            task_id="task_123",
            document_path="/path/to/report.md",
        )
        
        # Get preview
        preview = workflow.get_preview(state.loop_id)
        
        # Submit feedback
        state = workflow.submit_feedback(
            loop_id=state.loop_id,
            feedback=FeedbackRequest(
                accepted=False,
                revision_type="section",
                section_title="Market Size",
                user_feedback="Data needs updating",
                target_content="New content...",
            )
        )
        
        # Confirm finalization
        state = workflow.confirm(state.loop_id)
    """
    
    def __init__(
        self,
        preview_generator: Optional[PreviewGenerator] = None,
        revision_handler: Optional[RevisionHandler] = None,
        preview_format: str = DEFAULT_PREVIEW_FORMAT,
    ):
        """
        Initialize workflow
        
        Args:
            preview_generator: Preview generator
            revision_handler: Revision handler
            preview_format: Preview format
        """
        self.preview_generator = preview_generator or PreviewGenerator()
        self.revision_handler = revision_handler or RevisionHandler()
        self.preview_format = preview_format
        
        # Workflow state store
        self._workflows: Dict[str, WorkflowState] = {}
        
        # Content generation callback (for phase/full revision)
        self._content_generator_callback: Optional[Callable] = None
        
        logger.info("PreviewRevisionWorkflow initialized")
    
    def set_content_generator_callback(self, callback: Callable) -> None:
        """Set content generation callback"""
        self._content_generator_callback = callback
    
    def _generate_loop_id(self) -> str:
        """Generate workflow ID"""
        return f"loop_{uuid.uuid4().hex[:8]}"
    
    def start(
        self,
        task_id: str,
        document_path: str,
        max_rounds: int = MAX_REVISION_ROUNDS,
    ) -> WorkflowState:
        """
        Start workflow
        
        Args:
            task_id: Task ID
            document_path: Document path
            max_rounds: Maximum revision rounds
            
        Returns:
            WorkflowState workflow state
        """
        loop_id = self._generate_loop_id()
        
        state = WorkflowState(
            loop_id=loop_id,
            task_id=task_id,
            document_path=document_path,
            max_rounds=max_rounds,
        )
        
        self._workflows[loop_id] = state
        
        logger.info(f"Started workflow: {loop_id} for task {task_id}")
        
        return state
    
    def get_state(self, loop_id: str) -> Optional[WorkflowState]:
        """Get workflow state"""
        return self._workflows.get(loop_id)
    
    def generate_preview(
        self,
        loop_id: str,
    ) -> PreviewResult:
        """
        Generate preview
        
        Args:
            loop_id: Workflow ID
            
        Returns:
            PreviewResult preview result
        """
        state = self._workflows.get(loop_id)
        if not state:
            return PreviewResult(
                success=False,
                error=f"Workflow not found: {loop_id}",
                error_code="WORKFLOW_NOT_FOUND",
            )
        
        state.status = WorkflowStatus.PREVIEWING
        state.updated_at = datetime.now()
        
        # Generate preview
        result = self.preview_generator.generate_preview(
            document_path=state.document_path,
            format=self.preview_format,
        )
        
        if result.success:
            state.preview_result = result
            state.status = WorkflowStatus.WAITING_FEEDBACK
            logger.info(f"Generated preview for workflow {loop_id}")
        else:
            state.status = WorkflowStatus.FAILED
            state.error = result.error
            logger.error(f"Preview generation failed: {result.error}")
        
        state.updated_at = datetime.now()
        return result
    
    def submit_feedback(
        self,
        loop_id: str,
        feedback: FeedbackRequest,
    ) -> WorkflowState:
        """
        Submit user feedback
        
        Args:
            loop_id: Workflow ID
            feedback: User feedback
            
        Returns:
            WorkflowState updated state
        """
        state = self._workflows.get(loop_id)
        if not state:
            raise ValueError(f"Workflow not found: {loop_id}")
        
        # If user confirms, complete directly
        if feedback.accepted:
            state.status = WorkflowStatus.COMPLETED
            state.updated_at = datetime.now()
            logger.info(f"Workflow {loop_id} completed by user acceptance")
            return state
        
        # Check revision round limit
        if state.current_round >= state.max_rounds:
            state.status = WorkflowStatus.FAILED
            state.error = f"Maximum revision rounds ({state.max_rounds}) reached"
            state.updated_at = datetime.now()
            logger.warning(f"Workflow {loop_id} reached max rounds")
            return state
        
        # Execute revision
        state.status = WorkflowStatus.REVISING
        state.updated_at = datetime.now()
        
        revision_request = RevisionRequest(
            task_id=state.task_id,
            revision_type=feedback.revision_type or "minor",
            section_id=feedback.section_id,
            section_title=feedback.section_title,
            keywords=feedback.keywords,
            user_feedback=feedback.user_feedback or "",
            target_content=feedback.target_content,
            metadata=feedback.metadata,
        )
        
        revision_result = self.revision_handler.handle_revision(
            document_path=state.document_path,
            request=revision_request,
        )
        
        state.last_revision = revision_result
        state.revision_history.append(revision_result)
        state.current_round += 1
        
        if revision_result.success:
            state.status = WorkflowStatus.WAITING_FEEDBACK
            logger.info(
                f"Revision completed for workflow {loop_id}, "
                f"round {state.current_round}"
            )
        else:
            state.status = WorkflowStatus.FAILED
            state.error = revision_result.error
            logger.error(f"Revision failed: {revision_result.error}")
        
        state.updated_at = datetime.now()
        return state
    
    def confirm(self, loop_id: str) -> WorkflowState:
        """
        Confirm finalization
        
        Args:
            loop_id: Workflow ID
            
        Returns:
            WorkflowState updated state
        """
        state = self._workflows.get(loop_id)
        if not state:
            raise ValueError(f"Workflow not found: {loop_id}")
        
        state.status = WorkflowStatus.COMPLETED
        state.updated_at = datetime.now()
        
        logger.info(f"Workflow {loop_id} confirmed and completed")
        return state
    
    def cancel(self, loop_id: str) -> WorkflowState:
        """
        Cancel workflow
        
        Args:
            loop_id: Workflow ID
            
        Returns:
            WorkflowState updated state
        """
        state = self._workflows.get(loop_id)
        if not state:
            raise ValueError(f"Workflow not found: {loop_id}")
        
        state.status = WorkflowStatus.CANCELLED
        state.updated_at = datetime.now()
        
        logger.info(f"Workflow {loop_id} cancelled")
        return state
    
    def get_revision_history(
        self,
        loop_id: str,
    ) -> List[RevisionResult]:
        """Get revision history"""
        state = self._workflows.get(loop_id)
        if not state:
            return []
        return state.revision_history
    
    def list_active_workflows(self) -> List[WorkflowState]:
        """List active workflows"""
        return [
            state for state in self._workflows.values()
            if state.status in [
                WorkflowStatus.IDLE,
                WorkflowStatus.PREVIEWING,
                WorkflowStatus.WAITING_FEEDBACK,
                WorkflowStatus.REVISING,
            ]
        ]
    
    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed workflows
        
        Args:
            max_age_hours: Maximum retention time (hours)
            
        Returns:
            Number of cleaned workflows
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_remove = [
            loop_id for loop_id, state in self._workflows.items()
            if state.status in [
                WorkflowStatus.COMPLETED,
                WorkflowStatus.CANCELLED,
                WorkflowStatus.FAILED,
            ] and state.updated_at < cutoff
        ]
        
        for loop_id in to_remove:
            del self._workflows[loop_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed workflows")
        
        return len(to_remove)
    
    async def run_interactive_loop(
        self,
        task_id: str,
        document_path: str,
        feedback_callback: Callable[[PreviewResult], FeedbackRequest],
        max_rounds: int = MAX_REVISION_ROUNDS,
    ) -> WorkflowState:
        """
        Run interactive loop (async)
        
        This is a convenience method for running the complete preview-revision cycle
        in an async environment.
        
        Args:
            task_id: Task ID
            document_path: Document path
            feedback_callback: User feedback callback function
            max_rounds: Maximum revision rounds
            
        Returns:
            WorkflowState final state
        """
        # Start workflow
        state = self.start(task_id, document_path, max_rounds)
        
        while state.status not in [
            WorkflowStatus.COMPLETED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        ]:
            # Generate preview
            preview = self.generate_preview(state.loop_id)
            if not preview.success:
                break
            
            # Wait for user feedback
            state.status = WorkflowStatus.WAITING_FEEDBACK
            feedback = await asyncio.get_running_loop().run_in_executor(
                None, feedback_callback, preview
            )
            
            # Process feedback
            state = self.submit_feedback(state.loop_id, feedback)
            
            # Check if confirmed
            if feedback.accepted:
                state = self.confirm(state.loop_id)
                break
        
        return state


__all__ = [
    "WorkflowStatus",
    "WorkflowState",
    "FeedbackRequest",
    "PreviewRevisionWorkflow",
]
