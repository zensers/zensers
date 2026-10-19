"""Durable persistence for the survey MVP API.

The existing task stores cover distribution tasks, while the MVP API also
needs to retain the survey definition and AI simulation snapshots.  This
module keeps those API-owned records in SQLite so a process restart does not
make a survey disappear.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.storage import ConnectionConfig, ConnectionManager
from src.core.storage.schema_registry import SchemaRegistry
from src.core.storage.schemas import (
    SURVEY_STORAGE_META_SCHEMA,
    SURVEY_DEFINITIONS_SCHEMA,
    SURVEY_SIMULATION_RUNS_SCHEMA,
    SURVEY_SIMULATION_RUN_HISTORY_SCHEMA,
)

from .models import Survey, SurveyResponse


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class SurveyPersistence:
    """SQLite-backed persistence for survey definitions and simulation runs."""

    _SCHEMA_COMPONENT = "survey_api"
    _SCHEMA_VERSION = 2

    def __init__(self, connection_manager=None, db_path: Optional[str] = None):
        self._owns_connection_manager = connection_manager is None
        if connection_manager is None:
            configured = db_path or os.getenv("SURVEY_DB_PATH", "data/surveys.db")
            db_path_obj = Path(configured)
            self._connection_manager = ConnectionManager.from_path(
                db_path_obj,
                ConnectionConfig(timeout=30.0),
            )
            self._connection_name = db_path_obj.stem
        else:
            self._connection_manager = connection_manager
            self._connection_name = "surveys"
        self._ensure_schema()

    def _connect(self):
        return self._connection_manager.get_connection(self._connection_name, shared=True)

    def _close_if_owned(self, conn) -> None:
        # ConnectionManager owns the shared connection and closes it during
        # application shutdown. Never close it after an individual operation.
        return None

    def close(self) -> None:
        if self._owns_connection_manager:
            self._connection_manager.close_all()

    def get_schema_version(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT schema_version FROM survey_storage_meta WHERE component = ?",
                (self._SCHEMA_COMPONENT,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Survey storage schema metadata is missing")
            return int(row["schema_version"])
        finally:
            self._close_if_owned(conn)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            had_runs_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("survey_simulation_runs",),
            ).fetchone() is not None
            schemas = (
                SURVEY_STORAGE_META_SCHEMA,
                SURVEY_DEFINITIONS_SCHEMA,
                SURVEY_SIMULATION_RUNS_SCHEMA,
                SURVEY_SIMULATION_RUN_HISTORY_SCHEMA,
            )
            for schema in schemas:
                SchemaRegistry.register(schema)
                schema.create(conn)
            row = conn.execute(
                "SELECT schema_version FROM survey_storage_meta WHERE component = ?",
                (self._SCHEMA_COMPONENT,),
            ).fetchone()
            if row is None:
                current = 1 if had_runs_table else self._SCHEMA_VERSION
                conn.execute(
                    """
                    INSERT INTO survey_storage_meta(component, schema_version, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (self._SCHEMA_COMPONENT, current, datetime.now().isoformat()),
                )
            else:
                current = int(row["schema_version"])
            if current > self._SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported survey storage schema version: {current}"
                )
            if current < self._SCHEMA_VERSION:
                self._migrate_schema(conn, current, self._SCHEMA_VERSION)
                conn.execute(
                    """
                    UPDATE survey_storage_meta
                    SET schema_version = ?, updated_at = ?
                    WHERE component = ?
                    """,
                    (self._SCHEMA_VERSION, datetime.now().isoformat(), self._SCHEMA_COMPONENT),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._close_if_owned(conn)

    @staticmethod
    def _table_columns(conn, table_name: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}

    def _migrate_schema(self, conn, current: int, target: int) -> None:
        """Apply explicit, idempotent survey storage migrations."""
        if current < 1 or target < current:
            raise RuntimeError(f"Invalid survey storage migration: {current} -> {target}")
        if current == 1 and target >= 2:
            run_columns = self._table_columns(conn, "survey_simulation_runs")
            history_columns = self._table_columns(conn, "survey_simulation_run_history")
            additions = {
                "survey_simulation_runs": {
                    "run_id": "TEXT",
                    "started_at": "TEXT",
                    "finished_at": "TEXT",
                    "error_message": "TEXT",
                },
                "survey_simulation_run_history": {
                    "started_at": "TEXT",
                    "finished_at": "TEXT",
                    "error_message": "TEXT",
                },
            }
            for column, definition in additions["survey_simulation_runs"].items():
                if column not in run_columns:
                    conn.execute(
                        f"ALTER TABLE survey_simulation_runs ADD COLUMN {column} {definition}"
                    )
            for column, definition in additions["survey_simulation_run_history"].items():
                if column not in history_columns:
                    conn.execute(
                        f"ALTER TABLE survey_simulation_run_history ADD COLUMN {column} {definition}"
                    )
            return
        if current != target:
            raise RuntimeError(f"No migration path for survey storage: {current} -> {target}")

    def save_survey(self, survey: Survey) -> None:
        conn = self._connect()
        try:
            now = datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO survey_definitions
                    (survey_id, title, description, questions_json,
                     created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(survey_id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    questions_json=excluded.questions_json,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    survey.survey_id,
                    survey.title,
                    survey.description,
                    json.dumps([q.to_dict() for q in survey.questions], ensure_ascii=False),
                    survey.created_at.isoformat(),
                    now,
                    json.dumps(survey.metadata, default=_json_default, ensure_ascii=False),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._close_if_owned(conn)

    def get_survey(self, survey_id: str) -> Optional[Survey]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM survey_definitions WHERE survey_id = ?", (survey_id,)
            ).fetchone()
            if not row:
                return None
            return Survey.from_dict(
                {
                    "survey_id": row["survey_id"],
                    "title": row["title"],
                    "description": row["description"],
                    "questions": json.loads(row["questions_json"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "metadata": json.loads(row["metadata_json"]),
                }
            )
        finally:
            self._close_if_owned(conn)

    def list_surveys(self) -> List[Survey]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT survey_id FROM survey_definitions ORDER BY created_at DESC"
            ).fetchall()
            return [self.get_survey(row["survey_id"]) for row in rows]
        finally:
            self._close_if_owned(conn)

    def save_run(self, survey_id: str, run: Dict[str, Any]) -> None:
        responses = [
            item.to_dict() if hasattr(item, "to_dict") else item
            for item in run.get("responses", [])
        ]
        personas = [
            item.to_dict() if hasattr(item, "to_dict") else item
            for item in run.get("personas", [])
        ]
        result = run.get("result", {})
        run_id = str(run.get("run_id") or result.get("task_id") or uuid.uuid4().hex)
        now = datetime.now().isoformat()
        started_at = run.get("started_at") or now
        finished_at = run.get("finished_at")
        error_message = run.get("error_message") or result.get("error")
        conn = self._connect()
        try:
            values = (
                survey_id,
                run.get("status", "completed"),
                int(run.get("target_count", len(responses))),
                json.dumps(responses, default=_json_default, ensure_ascii=False),
                json.dumps(personas, default=_json_default, ensure_ascii=False),
                json.dumps(result, default=_json_default, ensure_ascii=False),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO survey_simulation_run_history
                    (run_id, survey_id, status, target_count, responses_json,
                     personas_json, result_json, created_at, started_at,
                     finished_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, *values, now, started_at, finished_at, error_message),
            )
            conn.execute(
                """
                INSERT INTO survey_simulation_runs
                    (survey_id, status, target_count, responses_json,
                     personas_json, result_json, updated_at, run_id,
                     started_at, finished_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(survey_id) DO UPDATE SET
                    run_id=excluded.run_id,
                    status=excluded.status,
                    target_count=excluded.target_count,
                    responses_json=excluded.responses_json,
                    personas_json=excluded.personas_json,
                    result_json=excluded.result_json,
                    updated_at=excluded.updated_at,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    error_message=excluded.error_message
                """,
                (
                    survey_id,
                    run.get("status", "completed"),
                    int(run.get("target_count", len(responses))),
                    json.dumps(responses, default=_json_default, ensure_ascii=False),
                    json.dumps(personas, default=_json_default, ensure_ascii=False),
                    json.dumps(result, default=_json_default, ensure_ascii=False),
                    now,
                    run_id,
                    started_at,
                    finished_at,
                    error_message,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._close_if_owned(conn)

    def get_run(self, survey_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM survey_simulation_runs WHERE survey_id = ?",
                (survey_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "run_id": row["run_id"],
                "status": row["status"],
                "target_count": row["target_count"],
                "responses": [
                    SurveyResponse.from_dict(item)
                    for item in json.loads(row["responses_json"])
                ],
                "personas": json.loads(row["personas_json"]),
                "result": json.loads(row["result_json"]),
                "updated_at": row["updated_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "error_message": row["error_message"],
            }
        finally:
            self._close_if_owned(conn)

    def list_runs(self, survey_id: str) -> List[Dict[str, Any]]:
        """Return immutable simulation history, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT run_id, status, target_count, responses_json,
                       personas_json, result_json, created_at, started_at,
                       finished_at, error_message
                FROM survey_simulation_run_history
                WHERE survey_id = ?
                ORDER BY created_at DESC
                """,
                (survey_id,),
            ).fetchall()
            items = []
            for row in rows:
                items.append({
                    "run_id": row["run_id"],
                    "status": row["status"],
                    "target_count": row["target_count"],
                    "responses": [
                        SurveyResponse.from_dict(item)
                        for item in json.loads(row["responses_json"])
                    ],
                    "personas": json.loads(row["personas_json"]),
                    "result": json.loads(row["result_json"]),
                    "updated_at": row["created_at"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "error_message": row["error_message"],
                })
            return items
        finally:
            self._close_if_owned(conn)

    def list_run_summaries(self, survey_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return lightweight run metadata without response/persona payloads."""
        limit = max(1, min(int(limit), 200))
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT run_id, status, target_count, responses_json, result_json
                FROM survey_simulation_run_history
                WHERE survey_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (survey_id, limit),
            ).fetchall()
            summaries = []
            for row in rows:
                result = json.loads(row["result_json"])
                cost_report = result.get("cost_report") or {}
                summaries.append({
                    "run_id": row["run_id"],
                    "status": row["status"],
                    "target_count": row["target_count"],
                    "response_count": len(json.loads(row["responses_json"])),
                    "cost": float(cost_report.get("total_cost", 0.0) or 0.0),
                })
            return summaries
        finally:
            self._close_if_owned(conn)
