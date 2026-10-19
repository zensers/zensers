from datetime import datetime
import sqlite3

import pytest

from src.core.storage import ConnectionManager
from src.survey.models import Answer, Question, QuestionType, Survey, SurveyResponse
from src.survey.persistence import SurveyPersistence


def make_survey() -> Survey:
    return Survey(
        survey_id="survey_persist_1",
        title="Persistent survey",
        description="smoke test",
        questions=[
            Question(
                question_id="q_1",
                text="Recommend?",
                question_type=QuestionType.YES_NO,
            )
        ],
    )


def make_response() -> SurveyResponse:
    return SurveyResponse(
        response_id="response_1",
        survey_id="survey_persist_1",
        answers={
            "q_1": Answer(
                question_id="q_1",
                answer_value="yes",
                answered_at=datetime.now(),
            )
        },
    )


def test_survey_and_run_survive_new_persistence_instance(tmp_path):
    manager = ConnectionManager(tmp_path, auto_cleanup=False)
    first = SurveyPersistence(manager)
    survey = make_survey()
    response = make_response()

    first.save_survey(survey)
    first.save_run(
        survey.survey_id,
        {
            "status": "completed",
            "target_count": 1,
            "responses": [response],
            "personas": [{"persona_id": "persona_1"}],
            "result": {"success": True, "cost_report": {"total_cost": 0.0}},
        },
    )
    manager.close_all()

    second = SurveyPersistence(ConnectionManager(tmp_path, auto_cleanup=False))
    restored = second.get_survey(survey.survey_id)
    run = second.get_run(survey.survey_id)

    assert restored is not None
    assert restored.title == survey.title
    assert restored.questions[0].question_type is QuestionType.YES_NO
    assert run["status"] == "completed"
    assert run["target_count"] == 1
    assert len(run["responses"]) == 1
    assert run["responses"][0].get_answer("q_1").answer_value == "yes"


def test_upsert_updates_existing_survey_and_run(tmp_path):
    persistence = SurveyPersistence(ConnectionManager(tmp_path, auto_cleanup=False))
    survey = make_survey()
    persistence.save_survey(survey)
    survey.title = "Updated title"
    persistence.save_survey(survey)
    persistence.save_run(survey.survey_id, {"status": "failed", "responses": []})
    persistence.save_run(survey.survey_id, {"status": "completed", "responses": []})

    assert persistence.get_survey(survey.survey_id).title == "Updated title"
    assert persistence.get_run(survey.survey_id)["status"] == "completed"


def test_simulation_run_history_is_append_only(tmp_path):
    persistence = SurveyPersistence(ConnectionManager(tmp_path, auto_cleanup=False))
    survey = make_survey()
    persistence.save_survey(survey)
    persistence.save_run(
        survey.survey_id,
        {"status": "completed", "run_id": "run_1", "responses": []},
    )
    persistence.save_run(
        survey.survey_id,
        {"status": "failed", "run_id": "run_2", "responses": []},
    )

    history = persistence.list_runs(survey.survey_id)
    assert [item["run_id"] for item in history] == ["run_2", "run_1"]
    assert persistence.get_run(survey.survey_id)["status"] == "failed"


def test_run_summaries_do_not_load_response_payloads(tmp_path):
    persistence = SurveyPersistence(ConnectionManager(tmp_path, auto_cleanup=False))
    survey = make_survey()
    persistence.save_survey(survey)
    persistence.save_run(
        survey.survey_id,
        {
            "status": "completed",
            "run_id": "run_summary",
            "target_count": 1,
            "responses": [make_response()],
            "result": {"cost_report": {"total_cost": 0.12}},
        },
    )

    summaries = persistence.list_run_summaries(survey.survey_id)
    assert summaries == [{
        "run_id": "run_summary",
        "status": "completed",
        "target_count": 1,
        "response_count": 1,
        "cost": 0.12,
    }]


def test_storage_schema_version_is_recorded(tmp_path):
    persistence = SurveyPersistence(ConnectionManager(tmp_path, auto_cleanup=False))

    assert persistence.get_schema_version() == 2


def test_newer_storage_schema_is_rejected(tmp_path):
    manager = ConnectionManager(tmp_path, auto_cleanup=False)
    SurveyPersistence(manager)
    conn = manager.get_connection("surveys")
    conn.execute(
        "UPDATE survey_storage_meta SET schema_version = 3 WHERE component = ?",
        ("survey_api",),
    )
    conn.commit()

    with pytest.raises(RuntimeError, match="Unsupported survey storage schema version"):
        SurveyPersistence(manager)


def test_v1_storage_is_migrated_to_v2(tmp_path):
    db_path = tmp_path / "surveys.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE survey_definitions (
            survey_id TEXT PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', questions_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE survey_simulation_runs (
            survey_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            target_count INTEGER NOT NULL DEFAULT 0,
            responses_json TEXT NOT NULL DEFAULT '[]',
            personas_json TEXT NOT NULL DEFAULT '[]',
            result_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
        );
        CREATE TABLE survey_simulation_run_history (
            run_id TEXT PRIMARY KEY, survey_id TEXT NOT NULL,
            status TEXT NOT NULL, target_count INTEGER NOT NULL DEFAULT 0,
            responses_json TEXT NOT NULL DEFAULT '[]',
            personas_json TEXT NOT NULL DEFAULT '[]',
            result_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    persistence = SurveyPersistence(db_path=str(db_path))
    assert persistence.get_schema_version() == 2
    columns = {
        row["name"]
        for row in persistence._connect().execute(
            "PRAGMA table_info(survey_simulation_runs)"
        )
    }
    assert {"run_id", "started_at", "finished_at", "error_message"} <= columns
    persistence.close()
