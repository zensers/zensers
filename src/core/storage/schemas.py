# -*- coding: utf-8 -*-
"""
数据库 Schema 定义
==================

集中定义所有数据库表的 Schema。

使用方式：
    from src.core.storage.schemas import register_all_schemas
    from src.core.storage.schema_registry import SchemaRegistry
    
    # 注册所有 Schema
    register_all_schemas()
    
    # 创建所有表
    SchemaRegistry.create_all(conn)
"""

__all__ = [
    "register_all_schemas",
    
    # 知识库核心表
    "ENTITIES_SCHEMA",
    "RELATIONS_SCHEMA",
    "DATA_POINTS_SCHEMA",
    "INSIGHTS_SCHEMA",
    
    # 研究记忆表
    "RESEARCH_HISTORY_SCHEMA",
    "REQUIREMENTS_SCHEMA",
    "FRAMEWORKS_SCHEMA",
    
    # 学习系统表
    "LEARNINGS_SCHEMA",
    "ERRORS_SCHEMA",
    "FEATURE_REQUESTS_SCHEMA",
    
    # 知识管理表
    "KNOWLEDGE_VERSIONS_SCHEMA",
    "PROVENANCE_SCHEMA",
    "CONTRADICTIONS_SCHEMA",
    "KNOWLEDGE_PAGES_SCHEMA",
    
    # 会话管理表
    "SESSION_SNAPSHOTS_SCHEMA",
    "RAW_RESEARCH_DATA_SCHEMA",
    
    # 调研系统表（v2.0新增）
    "SURVEY_TASKS_SCHEMA",
    "SURVEY_RESPONSES_SCHEMA",
    "SURVEY_PERSONAS_SCHEMA",
    "SURVEY_CHECKPOINTS_SCHEMA",
]

from .schema_registry import (
    SchemaRegistry,
    TableSchema,
    ColumnDef,
    IndexDef,
    ForeignKeyDef,
)


# ============================================================
# 知识库核心表
# ============================================================

ENTITIES_SCHEMA = TableSchema(
    table_name="entities",
    version=1,
    description="实体表 - 存储所有已知实体（公司、人物、概念等）",
    columns=[
        ColumnDef("entity_id", "TEXT", primary_key=True),
        ColumnDef("entity_type", "TEXT", not_null=True),
        ColumnDef("name", "TEXT", not_null=True),  # 应有 UNIQUE 约束，在索引中实现
        ColumnDef("aliases", "TEXT"),  # JSON 数组
        ColumnDef("description", "TEXT"),
        ColumnDef("first_seen", "TIMESTAMP", not_null=True),
        ColumnDef("last_mentioned", "TIMESTAMP", not_null=True),
        ColumnDef("mention_count", "INTEGER", default=1),
        ColumnDef("importance_score", "REAL", default=0.5),
        ColumnDef("properties", "TEXT"),  # JSON 对象
    ],
    indexes=[
        IndexDef("idx_entities_type", "entities", ["entity_type"]),
        IndexDef("idx_entities_name_unique", "entities", ["name"], unique=True),  # UNIQUE 约束
    ],
)

RELATIONS_SCHEMA = TableSchema(
    table_name="relations",
    version=1,
    description="关系表 - 存储实体之间的关系",
    columns=[
        ColumnDef("relation_id", "TEXT", primary_key=True),
        ColumnDef("source_entity", "TEXT", not_null=True, references="entities(entity_id)"),
        ColumnDef("target_entity", "TEXT", not_null=True, references="entities(entity_id)"),
        ColumnDef("relation_type", "TEXT", not_null=True),
        ColumnDef("context", "TEXT"),
        ColumnDef("source_ref", "TEXT"),
        ColumnDef("valid_from", "TIMESTAMP", not_null=True),
        ColumnDef("valid_until", "TIMESTAMP"),
        ColumnDef("confidence", "TEXT", default="medium"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_relations_source", "relations", ["source_entity"]),
        IndexDef("idx_relations_target", "relations", ["target_entity"]),
        IndexDef("idx_relations_type", "relations", ["relation_type"]),
    ],
)

DATA_POINTS_SCHEMA = TableSchema(
    table_name="data_points",
    version=1,
    description="数据点表 - 存储实体的数值数据",
    columns=[
        ColumnDef("data_id", "TEXT", primary_key=True),
        ColumnDef("entity_id", "TEXT", not_null=True, references="entities(entity_id)"),
        ColumnDef("metric_name", "TEXT", not_null=True),
        ColumnDef("metric_value", "TEXT", not_null=True),
        ColumnDef("unit", "TEXT"),
        ColumnDef("time_period", "TEXT"),
        ColumnDef("source_ref", "TEXT"),
        ColumnDef("confidence", "TEXT", default="medium"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_data_points_entity", "data_points", ["entity_id"]),
        IndexDef("idx_data_points_metric", "data_points", ["metric_name"]),
    ],
)

INSIGHTS_SCHEMA = TableSchema(
    table_name="insights",
    version=1,
    description="洞察表 - 存储研究过程中的关键发现",
    columns=[
        ColumnDef("insight_id", "TEXT", primary_key=True),
        ColumnDef("research_id", "TEXT", not_null=True, references="research_history(research_id)"),
        ColumnDef("topic", "TEXT"),
        ColumnDef("content", "TEXT", not_null=True),
        ColumnDef("supporting_data", "TEXT"),  # JSON 数组
        ColumnDef("source_ref", "TEXT"),
        ColumnDef("confidence", "TEXT", default="medium"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_insights_research", "insights", ["research_id"]),
        IndexDef("idx_insights_topic", "insights", ["topic"]),
    ],
)


# ============================================================
# 研究记忆表
# ============================================================

RESEARCH_HISTORY_SCHEMA = TableSchema(
    table_name="research_history",
    version=1,
    description="研究历史表 - 存储研究记录",
    columns=[
        ColumnDef("research_id", "TEXT", primary_key=True),
        ColumnDef("title", "TEXT"),
        ColumnDef("topic", "TEXT"),
        ColumnDef("entities", "TEXT"),  # JSON 数组
        ColumnDef("insights", "TEXT"),  # JSON 数组
        ColumnDef("framework", "TEXT"),  # JSON 对象
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
        ColumnDef("report_path", "TEXT"),
    ],
    indexes=[
        IndexDef("idx_research_history_topic", "research_history", ["topic"]),
        IndexDef("idx_research_history_created", "research_history", ["created_at"]),
    ],
)

REQUIREMENTS_SCHEMA = TableSchema(
    table_name="requirements",
    version=1,
    description="需求记忆表 - 存储用户需求分析结果",
    columns=[
        ColumnDef("requirement_id", "TEXT", primary_key=True),
        ColumnDef("research_id", "TEXT", not_null=True, references="research_history(research_id)"),
        ColumnDef("raw_input", "TEXT", not_null=True),
        ColumnDef("entities", "TEXT"),  # JSON 对象
        ColumnDef("clarifications", "TEXT"),  # JSON 数组
        ColumnDef("confirmed_scope", "TEXT"),  # JSON 对象
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_requirements_research", "requirements", ["research_id"]),
    ],
)

FRAMEWORKS_SCHEMA = TableSchema(
    table_name="frameworks",
    version=1,
    description="框架记忆表 - 存储报告框架",
    columns=[
        ColumnDef("framework_id", "TEXT", primary_key=True),
        ColumnDef("research_id", "TEXT", not_null=True, references="research_history(research_id)"),
        ColumnDef("version", "INTEGER", default=1),
        ColumnDef("sections", "TEXT"),  # JSON 数组
        ColumnDef("confirmed", "BOOLEAN", default=False),
        ColumnDef("user_modifications", "TEXT"),  # JSON 数组
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_frameworks_research", "frameworks", ["research_id"]),
    ],
)


# ============================================================
# 学习系统表
# ============================================================

LEARNINGS_SCHEMA = TableSchema(
    table_name="learnings",
    version=1,
    description="学习记录表 - 存储系统学习到的知识",
    columns=[
        ColumnDef("learning_id", "TEXT", primary_key=True),
        ColumnDef("user_id", "TEXT", not_null=True),
        ColumnDef("session_id", "TEXT"),
        ColumnDef("session_ids", "TEXT"),  # JSON 数组
        ColumnDef("category", "TEXT", not_null=True),
        ColumnDef("pattern_key", "TEXT"),
        ColumnDef("content", "TEXT", not_null=True),
        ColumnDef("priority", "TEXT", default="medium"),
        ColumnDef("status", "TEXT", default="pending"),
        ColumnDef("recurrence_count", "INTEGER", default=1),
        ColumnDef("first_seen", "TEXT", not_null=True),
        ColumnDef("last_seen", "TEXT", not_null=True),
        ColumnDef("promoted_to", "TEXT"),
        ColumnDef("metadata", "TEXT"),  # JSON 对象
        ColumnDef("created_at", "TEXT", default="CURRENT_TIMESTAMP"),
    ],
    indexes=[
        IndexDef("idx_learnings_user", "learnings", ["user_id"]),
        IndexDef("idx_learnings_pattern", "learnings", ["pattern_key"]),
        IndexDef("idx_learnings_status", "learnings", ["status"]),
        IndexDef("idx_learnings_category", "learnings", ["category"]),
        IndexDef("idx_learnings_recurrence", "learnings", ["recurrence_count"]),  # 用于查询晋升候选
    ],
)

ERRORS_SCHEMA = TableSchema(
    table_name="errors",
    version=1,
    description="错误记录表 - 存储系统遇到的错误",
    columns=[
        ColumnDef("error_id", "TEXT", primary_key=True),
        ColumnDef("user_id", "TEXT", not_null=True),
        ColumnDef("session_id", "TEXT"),
        ColumnDef("error_type", "TEXT", not_null=True),
        ColumnDef("error_message", "TEXT", not_null=True),
        ColumnDef("context", "TEXT"),  # JSON 对象
        ColumnDef("resolution", "TEXT"),
        ColumnDef("status", "TEXT", default="pending"),
        ColumnDef("recurrence_count", "INTEGER", default=1),
        ColumnDef("first_seen", "TEXT", not_null=True),
        ColumnDef("last_seen", "TEXT", not_null=True),
        ColumnDef("created_at", "TEXT", default="CURRENT_TIMESTAMP"),
    ],
    indexes=[
        IndexDef("idx_errors_user", "errors", ["user_id"]),
        IndexDef("idx_errors_type", "errors", ["error_type"]),
        IndexDef("idx_errors_status", "errors", ["status"]),
    ],
)

FEATURE_REQUESTS_SCHEMA = TableSchema(
    table_name="feature_requests",
    version=1,
    description="功能请求表 - 存储用户功能请求",
    columns=[
        ColumnDef("request_id", "TEXT", primary_key=True),
        ColumnDef("user_id", "TEXT", not_null=True),
        ColumnDef("session_id", "TEXT"),
        ColumnDef("capability", "TEXT", not_null=True),
        ColumnDef("user_context", "TEXT"),
        ColumnDef("complexity", "TEXT", default="medium"),
        ColumnDef("status", "TEXT", default="pending"),
        ColumnDef("frequency", "TEXT", default="first_time"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_feature_requests_user", "feature_requests", ["user_id"]),
        IndexDef("idx_feature_requests_status", "feature_requests", ["status"]),
    ],
)


# ============================================================
# 知识管理表
# ============================================================

KNOWLEDGE_VERSIONS_SCHEMA = TableSchema(
    table_name="knowledge_versions",
    version=1,
    description="知识版本表 - 追踪知识变更历史",
    columns=[
        ColumnDef("version_id", "TEXT", primary_key=True),
        ColumnDef("entity_id", "TEXT", not_null=True),
        ColumnDef("attribute", "TEXT", not_null=True),
        ColumnDef("old_value", "TEXT"),
        ColumnDef("new_value", "TEXT", not_null=True),
        ColumnDef("change_reason", "TEXT"),
        ColumnDef("source_ref", "TEXT"),
        ColumnDef("valid_from", "TIMESTAMP", not_null=True),
        ColumnDef("valid_until", "TIMESTAMP"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_knowledge_versions_entity", "knowledge_versions", ["entity_id"]),
        IndexDef("idx_knowledge_versions_valid", "knowledge_versions", ["valid_from", "valid_until"]),
    ],
)

PROVENANCE_SCHEMA = TableSchema(
    table_name="provenance",
    version=1,
    description="来源追溯表 - 追踪知识来源",
    columns=[
        ColumnDef("provenance_id", "TEXT", primary_key=True),
        ColumnDef("entity_id", "TEXT"),
        ColumnDef("relation_id", "TEXT"),
        ColumnDef("data_id", "TEXT"),
        ColumnDef("source_type", "TEXT", not_null=True),
        ColumnDef("source_ref", "TEXT", not_null=True),
        ColumnDef("confidence", "REAL", default=0.8),
        ColumnDef("extracted_at", "TIMESTAMP", not_null=True),
        ColumnDef("verified_at", "TIMESTAMP"),
    ],
    indexes=[
        IndexDef("idx_provenance_entity", "provenance", ["entity_id"]),
        IndexDef("idx_provenance_source", "provenance", ["source_ref"]),
    ],
)

CONTRADICTIONS_SCHEMA = TableSchema(
    table_name="contradictions",
    version=1,
    description="矛盾记录表 - 存储知识矛盾",
    columns=[
        ColumnDef("contradiction_id", "TEXT", primary_key=True),
        ColumnDef("entity_name", "TEXT", not_null=True),
        ColumnDef("attribute", "TEXT", not_null=True),
        ColumnDef("value_1", "TEXT", not_null=True),
        ColumnDef("source_1", "TEXT", not_null=True),
        ColumnDef("as_of_1", "TIMESTAMP"),
        ColumnDef("value_2", "TEXT", not_null=True),
        ColumnDef("source_2", "TEXT", not_null=True),
        ColumnDef("as_of_2", "TIMESTAMP"),
        ColumnDef("contradiction_type", "TEXT"),
        ColumnDef("resolution_status", "TEXT", default="pending"),
        ColumnDef("resolution_note", "TEXT"),
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_contradictions_entity", "contradictions", ["entity_name"]),
        IndexDef("idx_contradictions_status", "contradictions", ["resolution_status"]),
    ],
)

KNOWLEDGE_PAGES_SCHEMA = TableSchema(
    table_name="knowledge_pages",
    version=1,
    description="知识页表 - Markdown 文件索引",
    columns=[
        ColumnDef("page_id", "TEXT", primary_key=True),
        ColumnDef("page_type", "TEXT", not_null=True),
        ColumnDef("title", "TEXT", not_null=True),
        ColumnDef("file_path", "TEXT", not_null=True),
        ColumnDef("backlinks", "TEXT"),  # JSON 数组
        ColumnDef("compiled_from", "TEXT"),
        ColumnDef("compiled_at", "TIMESTAMP", not_null=True),
        ColumnDef("updated_at", "TIMESTAMP"),
    ],
    indexes=[
        IndexDef("idx_knowledge_pages_type", "knowledge_pages", ["page_type"]),
        IndexDef("idx_knowledge_pages_title", "knowledge_pages", ["title"]),
    ],
)


# ============================================================
# 会话管理表
# ============================================================

SESSION_SNAPSHOTS_SCHEMA = TableSchema(
    table_name="session_snapshots",
    version=1,
    description="会话快照表 - 用于崩溃恢复",
    columns=[
        ColumnDef("snapshot_id", "TEXT", primary_key=True),
        ColumnDef("session_id", "TEXT", not_null=True),
        ColumnDef("user_id", "TEXT", not_null=True),
        ColumnDef("step_name", "TEXT"),
        ColumnDef("step_index", "INTEGER"),
        ColumnDef("state_data", "TEXT"),  # JSON 对象
        ColumnDef("created_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_snapshots_session", "session_snapshots", ["session_id", "step_index"]),
    ],
)

RAW_RESEARCH_DATA_SCHEMA = TableSchema(
    table_name="raw_research_data",
    version=1,
    description="原始研究数据表 - 存储研究过程中的原始数据",
    columns=[
        ColumnDef("data_id", "TEXT", primary_key=True),
        ColumnDef("research_id", "TEXT", not_null=True),
        ColumnDef("source_type", "TEXT", not_null=True),
        ColumnDef("source_url", "TEXT"),
        ColumnDef("content", "TEXT", not_null=True),
        ColumnDef("metadata", "TEXT"),  # JSON 对象
        ColumnDef("collected_at", "TIMESTAMP", not_null=True),
    ],
    indexes=[
        IndexDef("idx_raw_data_research", "raw_research_data", ["research_id"]),
    ],
)


# ============================================================
# 调研系统表（v2.0新增）
# ============================================================

SURVEY_TASKS_SCHEMA = TableSchema(
    table_name="survey_tasks",
    version=1,
    description="调研任务表 - 存储调研任务的完整生命周期",
    columns=[
        ColumnDef("task_id", "TEXT", primary_key=True),
        ColumnDef("survey_id", "TEXT", not_null=True),
        ColumnDef("topic", "TEXT", not_null=True),
        ColumnDef("mode", "TEXT", not_null=True),  # 'third_party' | 'ai_simulation'
        ColumnDef("backend_type", "TEXT"),
        ColumnDef("status", "TEXT", not_null=True),  # 'draft' | 'active' | 'completed' | 'failed'
        ColumnDef("parent_task_id", "TEXT"),
        ColumnDef("parent_phase", "TEXT"),
        ColumnDef("config", "TEXT"),  # JSON: DistributionConfig
        ColumnDef("questions", "TEXT"),  # JSON: 问题列表
        ColumnDef("target_count", "INTEGER", default=100),
        ColumnDef("collected_count", "INTEGER", default=0),
        ColumnDef("valid_count", "INTEGER", default=0),
        ColumnDef("external_id", "TEXT"),  # 第三方平台问卷ID
        ColumnDef("share_url", "TEXT"),
        ColumnDef("created_at", "TEXT", not_null=True),
        ColumnDef("started_at", "TEXT"),
        ColumnDef("completed_at", "TEXT"),
        ColumnDef("error_message", "TEXT"),
        ColumnDef("questionnaire_docx_path", "TEXT"),
        ColumnDef("checkpoint_id", "TEXT"),
        ColumnDef("last_checkpoint_at", "TEXT"),
    ],
    indexes=[
        IndexDef("idx_survey_tasks_parent", "survey_tasks", ["parent_task_id"]),
        IndexDef("idx_survey_tasks_status", "survey_tasks", ["status"]),
        IndexDef("idx_survey_tasks_created", "survey_tasks", ["created_at"]),
    ],
)

SURVEY_RESPONSES_SCHEMA = TableSchema(
    table_name="survey_responses",
    version=1,
    description="调研响应表 - 存储问卷回答数据",
    columns=[
        ColumnDef("response_id", "TEXT", primary_key=True),
        ColumnDef("task_id", "TEXT", not_null=True),
        ColumnDef("survey_id", "TEXT", not_null=True),
        ColumnDef("respondent_id", "TEXT"),
        ColumnDef("persona_id", "TEXT"),  # AI模拟时的人物画像ID
        ColumnDef("answers", "TEXT", not_null=True),  # JSON: {question_id: answer}
        ColumnDef("quality_score", "REAL", default=1.0),
        ColumnDef("is_valid", "INTEGER", default=1),
        ColumnDef("duration_seconds", "INTEGER", default=0),
        ColumnDef("source", "TEXT"),  # 'ai_simulation' | 'third_party'
        ColumnDef("source_ip", "TEXT"),
        ColumnDef("demographics", "TEXT"),  # JSON
        ColumnDef("raw_data", "TEXT"),  # 原始平台响应JSON（用于审计）
        ColumnDef("completed_at", "TEXT", not_null=True),
    ],
    indexes=[
        IndexDef("idx_survey_responses_task", "survey_responses", ["task_id"]),
        IndexDef("idx_survey_responses_quality", "survey_responses", ["quality_score"]),
    ],
    foreign_keys=[
        ForeignKeyDef(["task_id"], "survey_tasks", ["task_id"]),
    ],
)

SURVEY_PERSONAS_SCHEMA = TableSchema(
    table_name="survey_personas",
    version=1,
    description="AI人物画像表 - 存储AI模拟的虚拟受访者画像",
    columns=[
        ColumnDef("persona_id", "TEXT", primary_key=True),
        ColumnDef("task_id", "TEXT", not_null=True),
        ColumnDef("name", "TEXT"),
        ColumnDef("age", "INTEGER"),
        ColumnDef("gender", "TEXT"),
        ColumnDef("city", "TEXT"),
        ColumnDef("occupation", "TEXT"),
        ColumnDef("income", "TEXT"),
        ColumnDef("education", "TEXT"),
        ColumnDef("personality_traits", "TEXT"),  # JSON array
        ColumnDef("interests", "TEXT"),  # JSON array
        ColumnDef("value_preferences", "TEXT"),  # JSON array (renamed from 'values' - SQL reserved word)
        ColumnDef("decision_style", "TEXT"),
        ColumnDef("background_story", "TEXT"),
        ColumnDef("contradictions", "TEXT"),  # JSON array
        ColumnDef("template", "TEXT"),  # 使用的人物模板
        ColumnDef("created_at", "TEXT", not_null=True),
    ],
    indexes=[
        IndexDef("idx_survey_personas_task", "survey_personas", ["task_id"]),
    ],
    foreign_keys=[
        ForeignKeyDef(["task_id"], "survey_tasks", ["task_id"]),
    ],
)

SURVEY_CHECKPOINTS_SCHEMA = TableSchema(
    table_name="survey_checkpoints",
    version=1,
    description="调研检查点表 - 用于任务中断恢复",
    columns=[
        ColumnDef("checkpoint_id", "TEXT", primary_key=True),
        ColumnDef("task_id", "TEXT", not_null=True),
        ColumnDef("step_name", "TEXT", not_null=True),
        ColumnDef("step_index", "INTEGER"),
        ColumnDef("total_steps", "INTEGER"),
        ColumnDef("status", "TEXT", not_null=True),
        ColumnDef("progress_percent", "REAL"),
        ColumnDef("collected_count", "INTEGER"),
        ColumnDef("valid_count", "INTEGER"),
        ColumnDef("snapshot_data", "TEXT"),  # JSON
        ColumnDef("created_at", "TEXT", not_null=True),
    ],
    indexes=[
        IndexDef("idx_survey_checkpoints_task", "survey_checkpoints", ["task_id"]),
        IndexDef("idx_survey_checkpoints_time", "survey_checkpoints", ["created_at"]),
    ],
    foreign_keys=[
        ForeignKeyDef(["task_id"], "survey_tasks", ["task_id"]),
    ],
)


# ============================================================
# 注册函数
# ============================================================

def register_all_schemas() -> None:
    """
    注册所有 Schema 到 SchemaRegistry
    
    在应用启动时调用此函数，确保所有表定义都已注册。
    """
    schemas = [
        # 知识库核心表
        ENTITIES_SCHEMA,
        RELATIONS_SCHEMA,
        DATA_POINTS_SCHEMA,
        INSIGHTS_SCHEMA,
        
        # 研究记忆表
        RESEARCH_HISTORY_SCHEMA,
        REQUIREMENTS_SCHEMA,
        FRAMEWORKS_SCHEMA,
        
        # 学习系统表
        LEARNINGS_SCHEMA,
        ERRORS_SCHEMA,
        FEATURE_REQUESTS_SCHEMA,
        
        # 知识管理表
        KNOWLEDGE_VERSIONS_SCHEMA,
        PROVENANCE_SCHEMA,
        CONTRADICTIONS_SCHEMA,
        KNOWLEDGE_PAGES_SCHEMA,
        
        # 会话管理表
        SESSION_SNAPSHOTS_SCHEMA,
        RAW_RESEARCH_DATA_SCHEMA,
        
        # 调研系统表（v2.0新增）
        SURVEY_TASKS_SCHEMA,
        SURVEY_RESPONSES_SCHEMA,
        SURVEY_PERSONAS_SCHEMA,
        SURVEY_CHECKPOINTS_SCHEMA,
    ]
    
    for schema in schemas:
        SchemaRegistry.register(schema)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Registered {len(schemas)} table schemas")
