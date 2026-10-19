"""
Survey Task Manager

Responsible for task persistence, recovery, and management.
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiofiles

from .models import SurveyTask, SurveyStatus, DistributionConfig
from .backends.factory import BackendFactory


class TaskStore:
    """Task persistent storage"""
    
    def __init__(self, storage_path: str = "data/survey_tasks"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    async def save(self, task: SurveyTask) -> None:
        """Save task"""
        task_file = self.storage_path / f"{task.task_id}.json"
        
        task_dict = task.to_dict()
        
        # Atomic write
        temp_file = task_file.with_suffix('.tmp')
        async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(task_dict, indent=2, ensure_ascii=False))
        
        # Rename
        temp_file.replace(task_file)
    
    async def load(self, task_id: str) -> Optional[SurveyTask]:
        """Load task"""
        task_file = self.storage_path / f"{task_id}.json"
        
        if not task_file.exists():
            return None
        
        async with aiofiles.open(task_file, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        data = json.loads(content)
        return SurveyTask.from_dict(data)
    
    async def update(self, task_id: str, updates: Dict[str, Any]) -> None:
        """Update task"""
        task = await self.load(task_id)
        if task:
            # Update fields
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            await self.save(task)
    
    async def delete(self, task_id: str) -> bool:
        """Delete task"""
        task_file = self.storage_path / f"{task_id}.json"
        if task_file.exists():
            task_file.unlink()
            return True
        return False
    
    async def list_all(self) -> List[SurveyTask]:
        """List all tasks"""
        tasks = []
        for task_file in self.storage_path.glob("*.json"):
            task = await self.load(task_file.stem)
            if task:
                tasks.append(task)
        return tasks
    
    async def list_by_status(self, status: SurveyStatus) -> List[SurveyTask]:
        """List tasks by status"""
        tasks = []
        for task_file in self.storage_path.glob("*.json"):
            task = await self.load(task_file.stem)
            if task and task.status == status:
                tasks.append(task)
        return tasks


class SurveyTaskManager:
    """Survey task manager"""
    
    def __init__(self, storage_path: str = "data/survey_tasks"):
        self.store = TaskStore(storage_path)
        self._webhook_handlers: Dict[str, Any] = {}
    
    async def create_task(
        self,
        task_id: str,
        survey_id: str,
        backend_type: str,
        config: DistributionConfig
    ) -> SurveyTask:
        """Create task"""
        task = SurveyTask(
            task_id=task_id,
            survey_id=survey_id,
            backend_type=backend_type,
            status=SurveyStatus.DRAFT,
            config=config,
            target_count=config.target_count,
        )
        await self.store.save(task)
        return task
    
    async def start_task(
        self,
        task_id: str,
        external_id: str,
        share_url: str
    ) -> None:
        """Start task"""
        await self.store.update(task_id, {
            "status": SurveyStatus.ACTIVE,
            "external_id": external_id,
            "share_url": share_url,
            "started_at": datetime.now(),
        })
    
    async def pause_task(self, task_id: str) -> None:
        """Pause task"""
        task = await self.store.load(task_id)
        if not task:
            return
        
        # Call backend to pause
        if task.external_id:
            try:
                backend = BackendFactory.get_or_create(task.backend_type)
                await backend.pause(task.external_id)
            except Exception:
                pass
        
        await self.store.update(task_id, {"status": SurveyStatus.PAUSED})
    
    async def resume_task(self, task_id: str) -> None:
        """Resume task"""
        task = await self.store.load(task_id)
        if not task:
            return
        
        # Call backend to resume
        if task.external_id:
            try:
                backend = BackendFactory.get_or_create(task.backend_type)
                await backend.resume(task.external_id)
            except Exception:
                pass
        
        await self.store.update(task_id, {"status": SurveyStatus.ACTIVE})
    
    async def complete_task(self, task_id: str) -> None:
        """Complete task"""
        await self.store.update(task_id, {
            "status": SurveyStatus.COMPLETED,
            "completed_at": datetime.now(),
        })
    
    async def fail_task(self, task_id: str, error_message: str) -> None:
        """Mark task as failed"""
        await self.store.update(task_id, {
            "status": SurveyStatus.FAILED,
            "error_message": error_message,
        })
    
    async def get_task(self, task_id: str) -> Optional[SurveyTask]:
        """Get task"""
        return await self.store.load(task_id)
    
    async def list_active_tasks(self) -> List[SurveyTask]:
        """List active tasks"""
        active = await self.store.list_by_status(SurveyStatus.ACTIVE)
        paused = await self.store.list_by_status(SurveyStatus.PAUSED)
        return active + paused
    
    async def resume_on_startup(self) -> List[str]:
        """Resume active tasks on system startup"""
        active_tasks = await self.list_active_tasks()
        resumed = []
        
        for task in active_tasks:
            try:
                if task.status == SurveyStatus.PAUSED:
                    await self.resume_task(task.task_id)
                resumed.append(task.task_id)
            except Exception as e:
                print(f"Failed to resume task {task.task_id}: {e}")
        
        return resumed
    
    async def update_progress(
        self, 
        task_id: str, 
        collected_count: int,
        valid_count: int
    ) -> None:
        """Update progress"""
        await self.store.update(task_id, {
            "collected_count": collected_count,
            "valid_count": valid_count,
        })
    
    async def delete_task(self, task_id: str) -> bool:
        """Delete task"""
        return await self.store.delete(task_id)
    
    # ============== Webhook Handling ==============
    
    async def handle_webhook(
        self,
        backend_type: str,
        event: Dict[str, Any]
    ) -> bool:
        """Handle webhook event"""
        action = event.get("action", "")
        
        if action == "answer.create":
            # New answer submitted
            payload = event.get("payload", {})
            survey_id = payload.get("survey_id")
            answer_id = payload.get("answer_id")
            
            # Find corresponding task
            all_tasks = await self.store.list_all()
            for task in all_tasks:
                if task.external_id == str(survey_id):
                    # Update progress
                    task.collected_count += 1
                    await self.store.save(task)
                    break
            
            return True
        
        return False


# Global singleton
_task_manager: Optional[SurveyTaskManager] = None


def get_task_manager() -> SurveyTaskManager:
    """Get global task manager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = SurveyTaskManager()
    return _task_manager