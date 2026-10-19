# -*- coding: utf-8 -*-
"""
Survey Data Storage Layer

Reuses the existing SQLiteStore base class, sharing the knowledge_bank.db database.

Store classes:
- SurveyTaskStore: Survey task storage
- SurveyResponseStore: Survey response storage
- SurveyPersonaStore: AI persona storage
- SurveyCheckpointStore: Checkpoint storage (for task recovery)
"""
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.core.storage import (
    SQLiteStore,
    ConnectionManager,
    NotFoundError,
)
from src.core.storage.schemas import (
    SURVEY_TASKS_SCHEMA,
    SURVEY_RESPONSES_SCHEMA,
    SURVEY_PERSONAS_SCHEMA,
    SURVEY_CHECKPOINTS_SCHEMA,
)

logger = logging.getLogger(__name__)


class SurveyTaskStore(SQLiteStore[Dict[str, Any]]):
    """Survey task storage"""
    
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_tasks",
        )
    
    def _create_table(self) -> None:
        """Create table"""
        SURVEY_TASKS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row) -> Dict[str, Any]:
        """Row to dict"""
        item = dict(row)
        # Parse JSON fields
        for field in ["config", "questions"]:
            if item.get(field) and isinstance(item[field], str):
                try:
                    item[field] = json.loads(item[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return item
    
    def _item_to_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Dict to storage format"""
        data = dict(item)
        # Serialize JSON fields (only when dict/list)
        for field in ["config", "questions"]:
            value = data.get(field)
            if value is not None and not isinstance(value, str):
                data[field] = json.dumps(value, ensure_ascii=False)
        return data
    
    def _get_id(self, item: Dict[str, Any]) -> str:
        return item.get("task_id", "")
    
    def _get_id_column(self) -> str:
        """Return ID column name"""
        return "task_id"
    
    # === Business methods ===
    
    def find_by_parent(self, parent_task_id: str) -> List[Dict[str, Any]]:
        """Find survey tasks associated with a master task"""
        cursor = self.db.execute(
            "SELECT * FROM survey_tasks WHERE parent_task_id = ?",
            (parent_task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def find_by_status(self, statuses: List[str]) -> List[Dict[str, Any]]:
        """Find tasks by status"""
        if not statuses:
            return []
        placeholders = ",".join("?" * len(statuses))
        cursor = self.db.execute(
            f"SELECT * FROM survey_tasks WHERE status IN ({placeholders})",
            statuses
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]


class SurveyResponseStore(SQLiteStore[Dict[str, Any]]):
    """Survey response storage"""
    
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_responses",
        )
    
    def _create_table(self) -> None:
        SURVEY_RESPONSES_SCHEMA.create(self.db)
    
    def _row_to_item(self, row) -> Dict[str, Any]:
        item = dict(row)
        for field in ["answers", "demographics", "raw_data"]:
            if item.get(field) and isinstance(item[field], str):
                try:
                    item[field] = json.loads(item[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return item
    
    def _item_to_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(item)
        for field in ["answers", "demographics", "raw_data"]:
            if data.get(field) and not isinstance(data[field], str):
                data[field] = json.dumps(data[field], ensure_ascii=False)
        return data
    
    def _get_id(self, item: Dict[str, Any]) -> str:
        return item.get("response_id", "")
    
    def _get_id_column(self) -> str:
        """Return ID column name"""
        return "response_id"
    
    # === Business methods ===
    
    def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all responses for a task"""
        cursor = self.db.execute(
            "SELECT * FROM survey_responses WHERE task_id = ? ORDER BY completed_at",
            (task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def count_by_task(self, task_id: str) -> int:
        """Count responses for a task"""
        cursor = self.db.execute(
            "SELECT COUNT(*) FROM survey_responses WHERE task_id = ?",
            (task_id,)
        )
        return cursor.fetchone()[0]
    
    def batch_add(self, items: List[Dict[str, Any]]) -> int:
        """Batch add responses"""
        count = 0
        for item in items:
            try:
                self.add(item)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to add response {item.get('response_id')}: {e}")
        return count


class SurveyPersonaStore(SQLiteStore[Dict[str, Any]]):
    """AI persona storage"""
    
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_personas",
        )
    
    def _create_table(self) -> None:
        SURVEY_PERSONAS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row) -> Dict[str, Any]:
        item = dict(row)
        for field in ["personality_traits", "interests", "value_preferences", "contradictions"]:
            if item.get(field) and isinstance(item[field], str):
                try:
                    item[field] = json.loads(item[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return item
    
    def _item_to_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(item)
        for field in ["personality_traits", "interests", "value_preferences", "contradictions"]:
            value = data.get(field)
            if value is not None and not isinstance(value, str):
                data[field] = json.dumps(value, ensure_ascii=False)
        return data
    
    def _get_id(self, item: Dict[str, Any]) -> str:
        return item.get("persona_id", "")
    
    def _get_id_column(self) -> str:
        """Return ID column name"""
        return "persona_id"
    
    # === Business methods ===
    
    def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all personas for a task"""
        cursor = self.db.execute(
            "SELECT * FROM survey_personas WHERE task_id = ? ORDER BY created_at",
            (task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]


class SurveyCheckpointStore(SQLiteStore[Dict[str, Any]]):
    """Survey checkpoint storage"""
    
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_checkpoints",
        )
    
    def _create_table(self) -> None:
        SURVEY_CHECKPOINTS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row) -> Dict[str, Any]:
        item = dict(row)
        if item.get("snapshot_data") and isinstance(item["snapshot_data"], str):
            try:
                item["snapshot_data"] = json.loads(item["snapshot_data"])
            except (json.JSONDecodeError, TypeError):
                pass
        return item
    
    def _item_to_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(item)
        if data.get("snapshot_data") and not isinstance(data["snapshot_data"], str):
            data["snapshot_data"] = json.dumps(data["snapshot_data"], ensure_ascii=False)
        return data
    
    def _get_id(self, item: Dict[str, Any]) -> str:
        return item.get("checkpoint_id", "")
    
    def _get_id_column(self) -> str:
        """Return ID column name"""
        return "checkpoint_id"
    
    # === Business methods ===
    
    def get_latest(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get latest checkpoint"""
        cursor = self.db.execute(
            "SELECT * FROM survey_checkpoints WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
    
    def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all checkpoints for a task"""
        cursor = self.db.execute(
            "SELECT * FROM survey_checkpoints WHERE task_id = ? ORDER BY created_at",
            (task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]
