# 调研交互集成开发计划（修订版）

> 版本: 2.2  
> 日期: 2026-04-18  
> 状态: **已完成** ✅  
> 修订说明: 完成所有功能实施和测试验证

---

## 一、需求概述

### 1.1 目标

完善调研系统与主控Orchestrator的交互集成，实现：
1. **工作流简化**：仅保留两种核心调研模式（第三方分发 / AI模拟）
2. **用户交互配置**：用户可在交互流程中配置调研参数
3. **问卷设计审核**：用户审核和确认问卷设计
4. **调研结果深度整合**：调研结果作为独立章节整合到研究报告
5. **数据库持久化存储**：调研数据存储到SQLite，支持任务中断恢复
6. **数据追溯规范**：问卷文档和原始数据保留底稿，便于追溯

### 1.2 用户反馈核心问题

| 问题 | 说明 | 解决方案 |
|------|------|----------|
| quick_survey 无价值 | 自动生成问题过于简单，缺乏实际调研价值 | 取消，并入AI模拟工作流 |
| "完整调研"概念模糊 | 用户不知道具体是什么 | 简化为两种明确模式：第三方分发、AI模拟 |
| 问卷文档缺失 | 用户无法查看完整问卷设计 | 生成Word文档保存到本地 |
| 原始数据缺失 | AI模拟的回答数据无底稿 | 保存原始响应数据为JSON/Excel |
| 数据管理混乱 | 调研数据分散，难以追溯 | 建立统一的数据目录结构 |
| **任务中断无法恢复** | AI模拟数据未入库，中断后需重新执行 | 使用SQLite持久化存储，支持断点续传 |
| **第三方数据未入库** | 第三方平台反馈数据仅存文件 | 统一存储到数据库，便于查询和分析 |

### 1.3 当前状态

| 功能 | 状态 | 说明 |
|------|------|------|
| 调研自动触发 | ✅ 已完成 | `include_survey: True` 可触发调研 |
| 调研执行 | ✅ 已完成 | SurveyIntegrationAgent 可执行调研 |
| 工作流简化 | ✅ 已完成 | 四种工作流 → 两种核心模式 |
| 调研配置交互 | ✅ 已完成 | SmartClarifier.configure_survey() |
| 问卷设计审核 | ✅ 已完成 | survey_design_review 交互步骤 |
| 问卷文档生成 | ✅ 已完成 | questionnaire_word.html 模板 |
| 原始数据存储 | ✅ 已完成 | survey_responses 表含 raw_data 字段 |
| **数据库持久化** | ✅ 已完成 | 4张调研表，继承 SQLiteStore |
| **任务恢复机制** | ✅ 已完成 | survey_checkpoints 表 + 检查点逻辑 |
| 调研结果整合 | ✅ 已完成 | _build_survey_section() 深度整合 |

---

## 二、工作流架构重构

### 2.1 现有工作流问题分析

**现有四种工作流**:
```
1. full_survey（完整调研）    - 概念模糊，用户不知道具体是什么
2. quick_survey（快速调研）   - 问题自动生成太简单，无实际价值
3. optimized_survey（优化调研）- 与full_survey重叠
4. ai_simulation（AI模拟）    - 与quick_survey重叠
```

**核心问题**:
1. `quick_survey` 自动生成的问题过于通用（如"您对X的整体看法如何？"），缺乏针对性
2. 工作流之间存在大量代码重复
3. 用户难以理解各工作流的区别
4. 第三方平台集成框架存在但未实际对接

### 2.2 新架构：两种核心模式

```
┌─────────────────────────────────────────────────────────────┐
│                      调研工作流                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐    ┌──────────────────────┐       │
│  │  模式A：第三方分发     │    │  模式B：AI Agent模拟   │       │
│  │                      │    │                      │       │
│  │  适用场景：           │    │  适用场景：           │       │
│  │  - 需要真实用户数据   │    │  - 快速原型验证       │       │
│  │  - 正式市场调研      │    │  - 无真实受众时       │       │
│  │  - 高可信度要求      │    │  - 预研阶段          │       │
│  │                      │    │                      │       │
│  │  执行流程：           │    │  执行流程：           │       │
│  │  1. 设计问卷         │    │  1. 设计问卷         │       │
│  │  2. 用户审核确认      │    │  2. 用户审核确认      │       │
│  │  3. 分发到第三方平台  │    │  3. 生成AI人物画像    │       │
│  │  4. 等待真实用户填写  │    │  4. AI模拟回答       │       │
│  │  5. 收集数据         │    │  5. 分析结果        │       │
│  │  6. 分析结果         │    │                      │       │
│  │                      │    │  输出：              │       │
│  │  输出：              │    │  - 问卷Word文档      │       │
│  │  - 问卷Word文档      │    │  - AI响应原始数据    │       │
│  │  - 发放链接          │    │  - 分析报告         │       │
│  │  - 收集进度          │    │                      │       │
│  │  - 分析报告          │    │                      │       │
│  └──────────────────────┘    └──────────────────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 工作流接口设计

**统一入口参数**:
```python
{
    "workflow": "third_party" | "ai_simulation",  # 必选：调研模式
    "topic": "研究主题",                            # 必选
    "questions": [...],                            # 可选：用户可自定义问题
    "target_count": 100,                           # 目标样本数
    "timeout_days": 7,                             # 超时天数（第三方模式）
    "backend": "api_tencent" | "api_wenjuanxing", # 第三方平台（第三方模式）
    "persona_template": "一线白领",                 # 人物画像模板（AI模拟模式）
}
```

**统一输出结果**:
```python
{
    "success": True,
    "survey_id": "survey_xxx",
    "mode": "third_party" | "ai_simulation",
    
    # 问卷文档
    "survey_document": {
        "path": "output/survey/survey_xxx/questionnaire.docx",
        "generated_at": "2026-04-18T10:30:00",
    },
    
    # 执行状态
    "task_status": "completed" | "waiting" | "failed",
    "collected_count": 100,
    "valid_count": 98,
    
    # 原始数据
    "raw_data_path": "output/survey/survey_xxx/responses.json",
    
    # 分析结果
    "analysis": {...},
    "report_section": {...},
}
```

---

## 三、数据存储架构

### 3.1 复用现有存储基础设施

**设计原则**：复用现有 `SQLiteStore` 基类和 `SchemaRegistry`，不新建独立数据库。

```
┌─────────────────────────────────────────────────────────────┐
│              现有存储基础设施（复用）                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  src/core/storage/                                           │
│  ├── base_store.py          # SQLiteStore 基类 ← 复用        │
│  ├── connection_manager.py  # 连接管理器 ← 复用              │
│  ├── schema_registry.py     # Schema注册表 ← 复用            │
│  └── schemas.py             # 表定义 ← 扩展                  │
│                                                              │
│  data/knowledge_bank.db    # 现有数据库（共享）               │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              调研存储扩展（新增）                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  src/survey/                                                 │
│  └── stores.py              # 调研相关Store类（继承基类）      │
│      ├── SurveyTaskStore(SQLiteStore)                       │
│      ├── SurveyResponseStore(SQLiteStore)                   │
│      ├── SurveyPersonaStore(SQLiteStore)                    │
│      └── SurveyCheckpointStore(SQLiteStore)                 │
│                                                              │
│  src/core/storage/schemas.py                                 │
│  └── 新增: SURVEY_TASKS_SCHEMA, SURVEY_RESPONSES_SCHEMA...  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 扩展 SchemaRegistry

**在 `src/core/storage/schemas.py` 中新增调研表定义**：

```python
# ============================================================
# 调研系统表（新增）
# ============================================================

SURVEY_TASKS_SCHEMA = TableSchema(
    table_name="survey_tasks",
    version=1,
    description="调研任务表",
    columns=[
        ColumnDef("task_id", "TEXT", primary_key=True),
        ColumnDef("survey_id", "TEXT", not_null=True),
        ColumnDef("topic", "TEXT", not_null=True),
        ColumnDef("mode", "TEXT", not_null=True),  # 'ai_simulation' | 'third_party'
        ColumnDef("backend_type", "TEXT"),
        ColumnDef("status", "TEXT", not_null=True),
        ColumnDef("parent_task_id", "TEXT"),
        ColumnDef("parent_phase", "TEXT"),
        ColumnDef("config", "TEXT"),  # JSON
        ColumnDef("questions", "TEXT"),  # JSON
        ColumnDef("target_count", "INTEGER", default=100),
        ColumnDef("collected_count", "INTEGER", default=0),
        ColumnDef("valid_count", "INTEGER", default=0),
        ColumnDef("external_id", "TEXT"),
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
    ],
)

SURVEY_RESPONSES_SCHEMA = TableSchema(
    table_name="survey_responses",
    version=1,
    description="调研响应表",
    columns=[
        ColumnDef("response_id", "TEXT", primary_key=True),
        ColumnDef("task_id", "TEXT", not_null=True),
        ColumnDef("survey_id", "TEXT", not_null=True),
        ColumnDef("respondent_id", "TEXT"),
        ColumnDef("persona_id", "TEXT"),
        ColumnDef("answers", "TEXT", not_null=True),  # JSON
        ColumnDef("quality_score", "REAL", default=1.0),
        ColumnDef("is_valid", "INTEGER", default=1),
        ColumnDef("duration_seconds", "INTEGER", default=0),
        ColumnDef("source", "TEXT"),
        ColumnDef("demographics", "TEXT"),  # JSON
        ColumnDef("completed_at", "TEXT", not_null=True),
    ],
    indexes=[
        IndexDef("idx_survey_responses_task", "survey_responses", ["task_id"]),
    ],
    foreign_keys=[
        ForeignKeyDef("survey_responses", ["task_id"], "survey_tasks", ["task_id"]),
    ],
)

SURVEY_PERSONAS_SCHEMA = TableSchema(
    table_name="survey_personas",
    version=1,
    description="AI人物画像表",
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
        ColumnDef("personality_traits", "TEXT"),  # JSON
        ColumnDef("interests", "TEXT"),  # JSON
        ColumnDef("values", "TEXT"),  # JSON
        ColumnDef("decision_style", "TEXT"),
        ColumnDef("background_story", "TEXT"),
        ColumnDef("template", "TEXT"),
        ColumnDef("created_at", "TEXT", not_null=True),
    ],
    indexes=[
        IndexDef("idx_survey_personas_task", "survey_personas", ["task_id"]),
    ],
    foreign_keys=[
        ForeignKeyDef("survey_personas", ["task_id"], "survey_tasks", ["task_id"]),
    ],
)

SURVEY_CHECKPOINTS_SCHEMA = TableSchema(
    table_name="survey_checkpoints",
    version=1,
    description="调研检查点表（用于任务恢复）",
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
        ForeignKeyDef("survey_checkpoints", ["task_id"], "survey_tasks", ["task_id"]),
    ],
)


def register_all_schemas():
    """注册所有 Schema"""
    # ... 现有注册 ...
    
    # 调研系统表（新增）
    SchemaRegistry.register(SURVEY_TASKS_SCHEMA)
    SchemaRegistry.register(SURVEY_RESPONSES_SCHEMA)
    SchemaRegistry.register(SURVEY_PERSONAS_SCHEMA)
    SchemaRegistry.register(SURVEY_CHECKPOINTS_SCHEMA)
```

### 3.3 实现 Store 类（继承 SQLiteStore）

**新建 `src/survey/stores.py`**：

```python
"""调研数据存储层

复用现有 SQLiteStore 基类，共享 knowledge_bank.db 数据库。
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

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
from src.survey.models import SurveyTask, SurveyResponse, SurveyStatus


class SurveyTaskStore(SQLiteStore[SurveyTask]):
    """调研任务存储"""
    
    def __init__(self, connection_manager: ConnectionManager):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",  # 共享现有数据库
            table_name="survey_tasks",
        )
    
    def _create_table(self) -> None:
        """创建表"""
        SURVEY_TASKS_SCHEMA.create(self.db)
    
    def _row_to_item(self, row) -> SurveyTask:
        """行转对象"""
        return SurveyTask(
            task_id=row["task_id"],
            survey_id=row["survey_id"],
            backend_type=row["backend_type"],
            status=SurveyStatus(row["status"]),
            # ... 其他字段
        )
    
    def _item_to_dict(self, item: SurveyTask) -> Dict[str, Any]:
        """对象转字典"""
        return {
            "task_id": item.task_id,
            "survey_id": item.survey_id,
            "topic": item.topic,
            "mode": item.mode,
            "status": item.status.value,
            "config": json.dumps(item.config.to_dict()) if item.config else None,
            # ... 其他字段
        }
    
    def _get_id(self, item: SurveyTask) -> str:
        return item.task_id
    
    # === 业务方法 ===
    
    def find_by_parent(self, parent_task_id: str) -> List[SurveyTask]:
        """查找关联的任务"""
        cursor = self.db.execute(
            "SELECT * FROM survey_tasks WHERE parent_task_id = ?",
            (parent_task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def find_by_status(self, statuses: List[str]) -> List[SurveyTask]:
        """按状态查找"""
        placeholders = ",".join("?" * len(statuses))
        cursor = self.db.execute(
            f"SELECT * FROM survey_tasks WHERE status IN ({placeholders})",
            statuses
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]


class SurveyResponseStore(SQLiteStore[SurveyResponse]):
    """调研响应存储"""
    
    def __init__(self, connection_manager: ConnectionManager):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_responses",
        )
    
    def _create_table(self) -> None:
        SURVEY_RESPONSES_SCHEMA.create(self.db)
    
    # ... 其他实现
    
    def list_by_task(self, task_id: str) -> List[SurveyResponse]:
        """获取任务的所有响应"""
        cursor = self.db.execute(
            "SELECT * FROM survey_responses WHERE task_id = ? ORDER BY completed_at",
            (task_id,)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def count_by_task(self, task_id: str) -> int:
        """统计任务响应数"""
        cursor = self.db.execute(
            "SELECT COUNT(*) FROM survey_responses WHERE task_id = ?",
            (task_id,)
        )
        return cursor.fetchone()[0]


class SurveyCheckpointStore(SQLiteStore[Dict[str, Any]]):
    """调研检查点存储"""
    
    def __init__(self, connection_manager: ConnectionManager):
        super().__init__(
            connection_manager=connection_manager,
            connection_name="knowledge_bank",
            table_name="survey_checkpoints",
        )
    
    def _create_table(self) -> None:
        SURVEY_CHECKPOINTS_SCHEMA.create(self.db)
    
    # ... 其他实现
    
    def get_latest(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取最新检查点"""
        cursor = self.db.execute(
            "SELECT * FROM survey_checkpoints WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
```

### 3.4 文件存储结构（仅存文档）

```
output/
└── survey/
    └── {survey_id}/
        ├── questionnaire.docx    # 问卷Word文档
        ├── responses.xlsx        # Excel导出
        └── analysis_report.docx  # 分析报告
```

**注意**：原始数据存储在数据库中，文件层仅存储用户可见的文档格式。

### 3.5 第三方平台数据格式处理

#### 3.5.1 现有架构（复用）

**后端抽象层**已实现格式转换：

```
第三方平台原始数据
        ↓
SurveyBackend._convert_response()  ← 各平台实现
        ↓
统一 SurveyResponse 对象
        ↓
SurveyResponseStore 存储
```

**现有转换器**：

| 平台 | 文件 | 转换方法 |
|------|------|----------|
| 腾讯问卷 | `backends/tencent_survey.py` | `_convert_response()` |
| Mock后端 | `backends/mock_backend.py` | 直接返回标准格式 |
| AI模拟 | `services/simulation_engine.py` | 直接生成标准格式 |

#### 3.5.2 数据格式映射表

**腾讯问卷 → 统一格式映射**：

| 腾讯问卷字段 | 统一格式字段 | 说明 |
|-------------|-------------|------|
| `answer_id` | `response_id` | 响应ID |
| `respondent_id` | `respondent_id` | 受访者ID |
| `answer[].questions[]` | `answers` | 回答列表 |
| `questions[].id` | `question_id` | 问题ID |
| `questions[].type` | 题型判断 | radio/text/star等 |
| `questions[].options[].checked` | `answer_value` | 选中项 |
| `questions[].text` | `answer_text` | 文本回答 |
| `duration` | `duration_seconds` | 答题时长 |
| `ip` | `source_ip` | 来源IP |
| `country/province/city` | `demographics` | 地理信息 |

**题型映射**：

```python
# 腾讯问卷 → 统一题型
QUESTION_TYPE_MAP = {
    "radio": QuestionType.SINGLE_CHOICE,
    "checkbox": QuestionType.MULTIPLE_CHOICE,
    "select": QuestionType.DROPDOWN,
    "text": QuestionType.OPEN_ENDED,
    "textarea": QuestionType.OPEN_ENDED,
    "star": QuestionType.SCALE,
    "nps": QuestionType.SCALE,
    "matrix_radio": QuestionType.MATRIX,
}
```

#### 3.5.3 Webhook回传数据处理流程

```
┌─────────────────────────────────────────────────────────────┐
│              第三方平台Webhook回传流程                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 第三方平台触发Webhook                                     │
│     ↓                                                        │
│  2. SurveyWebhookHandler.handle_webhook()                   │
│     ├── 验证HMAC签名（安全）                                  │
│     ├── 验证时间戳（防重放）                                  │
│     └── 速率限制检查                                          │
│     ↓                                                        │
│  3. 解析事件类型                                              │
│     ├── answer.create → 实时响应                             │
│     ├── survey.complete → 调研完成                           │
│     └── quota.reached → 配额达成                             │
│     ↓                                                        │
│  4. 调用Backend获取详细数据                                   │
│     backend.get_results(external_id)                        │
│     ↓                                                        │
│  5. 格式转换                                                  │
│     backend._convert_response(raw_data) → SurveyResponse    │
│     ↓                                                        │
│  6. PII数据加密（敏感信息）                                    │
│     PIIEncryption.encrypt_data()                            │
│     ↓                                                        │
│  7. 存储到数据库                                              │
│     SurveyResponseStore.add(response)                       │
│     ↓                                                        │
│  8. 更新任务进度                                              │
│     SurveyTaskStore.update(task_id, {collected_count: +1})  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 3.5.4 需要扩展的适配器

**新增平台适配器示例**（问卷星）：

```python
# src/survey/backends/wenjuanxing.py

class WenjuanxingBackend(SurveyBackend):
    """问卷星后端"""
    
    @property
    def backend_type(self) -> str:
        return "api_wenjuanxing"
    
    def _convert_response(
        self,
        raw_data: Dict[str, Any],
        survey_id: str
    ) -> SurveyResponse:
        """转换问卷星响应为统一格式"""
        
        # 问卷星字段映射（需根据实际API文档调整）
        answers: Dict[str, Answer] = {}
        
        for item in raw_data.get("answers", []):
            q_id = item.get("question_id")
            q_type = item.get("question_type")
            
            if q_type == "radio":
                answers[q_id] = Answer(
                    question_id=q_id,
                    answer_value=item.get("option_text", ""),
                )
            elif q_type == "checkbox":
                selected = [opt.get("text") for opt in item.get("options", [])]
                answers[q_id] = Answer(
                    question_id=q_id,
                    answer_value=",".join(selected),
                )
            # ... 其他题型
        
        return SurveyResponse(
            response_id=raw_data.get("answer_id"),
            survey_id=survey_id,
            answers=answers,
            completed_at=datetime.fromisoformat(raw_data.get("submit_time")),
            duration_seconds=raw_data.get("duration", 0),
            # ...
        )
```

#### 3.5.5 数据存储Schema兼容性

**统一存储格式**确保不同来源数据兼容：

```sql
-- survey_responses 表设计支持多来源
CREATE TABLE survey_responses (
    response_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    survey_id TEXT NOT NULL,
    
    -- 来源标识
    source TEXT,  -- 'ai_simulation' | 'api_tencent' | 'api_wenjuanxing'
    
    -- 统一回答格式（JSON）
    answers TEXT NOT NULL,
    
    -- 原始数据保留（用于审计和追溯）
    raw_data TEXT,  -- 原始平台响应JSON
    
    -- 质量指标（各平台可能不同）
    quality_score REAL DEFAULT 1.0,
    is_valid INTEGER DEFAULT 1,
    
    -- ...
);
```

### 3.6 任务恢复机制

#### 3.4.1 检查点创建时机

```python
# 在关键步骤创建检查点
async def execute_with_checkpoint(task_id: str, step_name: str, step_fn: Callable):
    """带检查点的执行"""
    
    # 1. 执行步骤
    result = await step_fn()
    
    # 2. 创建检查点
    checkpoint = SurveyCheckpoint(
        checkpoint_id=f"cp_{uuid.uuid4().hex[:8]}",
        task_id=task_id,
        step_name=step_name,
        status="completed",
        created_at=datetime.now(),
    )
    await checkpoint_store.add(checkpoint)
    
    # 3. 更新任务状态
    await task_store.update(task_id, {
        "checkpoint_id": checkpoint.checkpoint_id,
        "last_checkpoint_at": checkpoint.created_at,
    })
    
    return result
```

#### 3.4.2 恢复流程

```python
async def recover_survey_task(task_id: str) -> SurveyTask:
    """恢复中断的调研任务"""
    
    # 1. 加载任务
    task = await task_store.get(task_id)
    if not task:
        raise NotFoundError(f"Task {task_id} not found")
    
    # 2. 检查是否需要恢复
    if task.status == "completed":
        return task
    
    # 3. 加载最新检查点
    checkpoint = await checkpoint_store.get_latest(task_id)
    if not checkpoint:
        # 从头开始
        return await restart_task(task)
    
    # 4. 从检查点恢复
    logger.info(f"Recovering task {task_id} from checkpoint {checkpoint.step_name}")
    
    # 5. 恢复数据
    if checkpoint.step_name == "ai_simulation":
        # 已生成画像，继续模拟
        personas = await persona_store.list_by_task(task_id)
        responses = await response_store.list_by_task(task_id)
        # 继续执行...
    elif checkpoint.step_name == "analysis":
        # 已收集响应，继续分析
        responses = await response_store.list_by_task(task_id)
        # 继续执行...
    
    return task
```

#### 3.4.3 启动时自动恢复

```python
async def on_startup():
    """系统启动时恢复中断的任务"""
    
    # 1. 查找中断的任务
    interrupted_tasks = await task_store.find_by_status(["active", "waiting"])
    
    # 2. 逐个恢复
    for task in interrupted_tasks:
        try:
            await recover_survey_task(task.task_id)
            logger.info(f"Task {task.task_id} recovered successfully")
        except Exception as e:
            logger.error(f"Failed to recover task {task.task_id}: {e}")
            await task_store.update(task.task_id, {
                "status": "failed",
                "error_message": str(e),
            })
```

### 3.5 数据追溯机制

**元数据记录**:
```json
{
    "survey_id": "survey_abc123",
    "created_at": "2026-04-18T10:00:00",
    "parent_task_id": "research_xyz789",    // 关联的主控研究任务
    "mode": "ai_simulation",
    "config": {...},
    "status_history": [
        {"status": "created", "at": "2026-04-18T10:00:00"},
        {"status": "confirmed", "at": "2026-04-18T10:05:00"},
        {"status": "completed", "at": "2026-04-18T10:30:00"}
    ],
    "files": {
        "questionnaire": "questionnaire.docx",
        "responses": "responses/responses.json",
        "analysis": "analysis/analysis_report.json"
    }
}
```

---

## 四、问卷文档生成方案

### 4.1 文档结构

**问卷Word文档包含**:
```
1. 封面
   - 问卷标题
   - 研究主题
   - 创建日期
   - 目标样本数

2. 问卷概述
   - 调研目的
   - 适用人群
   - 预计时长

3. 问卷正文
   - 问题编号
   - 问题类型（单选/多选/开放题等）
   - 问题文本
   - 选项列表（如有）
   - 是否必答

4. 附录
   - 问题统计
   - 生成配置
```

### 4.2 实现方案

**模板文件**: `config/document_templates/questionnaire_word.html`

**生成流程**:
```
Survey对象 → ContentOrchestrator → HTML → HTMLToWordConverter → DOCX
```

**代码示例**:
```python
async def generate_questionnaire_document(survey: Survey, output_path: str) -> str:
    """生成问卷Word文档"""
    
    # 1. 准备模板变量
    template_vars = {
        "title": survey.title,
        "created_at": survey.created_at.strftime("%Y年%m月%d日"),
        "target_count": survey.metadata.get("target_count", 100),
        "questions": [
            {
                "index": i + 1,
                "id": q.question_id,
                "text": q.text,
                "type": _get_type_label(q.question_type),
                "options": q.options or [],
                "required": "必答" if q.required else "选答",
            }
            for i, q in enumerate(survey.questions)
        ],
        "total_questions": len(survey.questions),
    }
    
    # 2. 使用模板引擎渲染
    orchestrator = ContentOrchestrator()
    html = await orchestrator.transform_to_html(
        research_result=template_vars,
        output_format="docx",
        template_name="questionnaire_word"
    )
    
    # 3. 转换为Word
    converter = HTMLToWordConverter()
    docx_path = converter.convert(html, output_path)
    
    return docx_path
```

---

## 五、AI模拟数据存储方案

### 5.1 原始响应数据结构

**responses.json**:
```json
[
    {
        "response_id": "resp_001",
        "persona_id": "persona_abc",
        "completed_at": "2026-04-18T10:15:32",
        "quality_score": 0.95,
        "is_valid": true,
        "answers": [
            {
                "question_id": "q1",
                "question_text": "您的年龄范围是？",
                "answer_value": "B",
                "answer_text": "26-35岁"
            },
            {
                "question_id": "q2",
                "question_text": "您购买电动汽车时最看重哪个因素？",
                "answer_value": "A",
                "answer_text": "价格/性价比"
            }
        ],
        "persona_profile": {
            "name": "张三",
            "age": 32,
            "gender": "男",
            "city": "上海",
            "occupation": "产品经理"
        },
        "duration_seconds": 45
    }
]
```

### 5.2 数据质量报告

**quality_report.json**:
```json
{
    "total_responses": 100,
    "valid_responses": 98,
    "invalid_responses": 2,
    "avg_duration_seconds": 52,
    "avg_quality_score": 0.92,
    
    "quality_issues": [
        {
            "response_id": "resp_042",
            "issue": "答题时间过短",
            "duration": 5
        }
    ],
    
    "distribution": {
        "by_quality": {
            "high (>0.9)": 75,
            "medium (0.7-0.9)": 20,
            "low (<0.7)": 5
        }
    }
}
```

---

## 六、实施计划

### 6.1 任务分解（修订版 v2.2 - 已完成）

| 阶段 | 任务 | 状态 | 完成日期 |
|------|------|------|----------|
| **Phase 1** | 工作流架构重构 | ✅ 完成 | 2026-04-18 |
| 1.1 | 简化工作流类型（4→2） | ✅ 完成 | 2026-04-18 |
| 1.2 | 统一接口设计 | ✅ 完成 | 2026-04-18 |
| 1.3 | 移除冗余代码 | ✅ 完成 | 2026-04-18 |
| **Phase 2** | 数据库持久化存储 | ✅ 完成 | 2026-04-18 |
| 2.1 | 设计数据库表结构 | ✅ 完成 | 2026-04-18 |
| 2.2 | 实现 SurveyTaskStore (SQLiteStore) | ✅ 完成 | 2026-04-18 |
| 2.3 | 实现 SurveyResponseStore | ✅ 完成 | 2026-04-18 |
| 2.4 | 实现 SurveyPersonaStore | ✅ 完成 | 2026-04-18 |
| **Phase 3** | 任务恢复机制 | ✅ 完成 | 2026-04-18 |
| 3.1 | 实现 SurveyCheckpointStore | ✅ 完成 | 2026-04-18 |
| 3.2 | 实现检查点创建逻辑 | ✅ 完成 | 2026-04-18 |
| 3.3 | 实现任务恢复流程 | ✅ 完成 | 2026-04-18 |
| **Phase 4** | 问卷文档生成 | ✅ 完成 | 2026-04-18 |
| 4.1 | 创建问卷Word模板 | ✅ 完成 | 2026-04-18 |
| 4.2 | 实现文档生成逻辑 | ✅ 完成 | 2026-04-18 |
| 4.3 | 集成到工作流 | ✅ 完成 | 2026-04-18 |
| **Phase 5** | 调研配置交互 | ✅ 完成 | 2026-04-18 |
| 5.1 | 修改 SmartClarifier | ✅ 完成 | 2026-04-18 |
| 5.2 | 集成到 Orchestrator | ✅ 完成 | 2026-04-18 |
| **Phase 6** | 问卷设计审核 | ✅ 完成 | 2026-04-18 |
| 6.1 | 新增审核交互 | ✅ 完成 | 2026-04-18 |
| 6.2 | 处理用户修改 | ✅ 完成 | 2026-04-18 |
| **Phase 7** | 测试验证 | ✅ 完成 | 2026-04-18 |
| 7.1 | 数据库存储测试 | ✅ 完成 | 2026-04-18 |
| 7.2 | 恢复机制测试 | ✅ 完成 | 2026-04-18 |
| 7.3 | 端到端测试 | ✅ 完成 | 2026-04-18 |

### 6.2 文件修改清单（修订版 v2.1）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/agents/fixed_agents/survey_integration_agent.py` | 重构 | 简化工作流，增加检查点 |
| **`src/survey/stores.py`** | **新增** | **调研Store类（继承SQLiteStore）** |
| `src/survey/models.py` | 修改 | 添加数据追溯字段、raw_data字段 |
| `src/survey/task_manager.py` | 修改 | 迁移到SurveyTaskStore |
| **`src/core/storage/schemas.py`** | **修改** | **注册调研表Schema（含raw_data字段）** |
| `src/core/orchestrator/smart_clarifier.py` | 修改 | 添加调研配置步骤 |
| `src/core/orchestrator/orchestrator.py` | 修改 | 集成问卷审核流程 |
| `config/document_templates/questionnaire_word.html` | 新增 | 问卷Word模板 |
| `test_survey_integration.py` | 修改 | 更新测试用例 |

**平台适配器（可选扩展）**：

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/survey/backends/wenjuanxing.py` | 新增（可选） | 问卷星后端适配器 |
| `src/survey/backends/factory.py` | 修改 | 注册新平台后端 |

### 6.3 架构复用说明

**复用现有组件**：

| 组件 | 位置 | 用途 |
|------|------|------|
| `SQLiteStore` | `src/core/storage/base_store.py` | 存储基类，提供CRUD/查询/事务 |
| `ConnectionManager` | `src/core/storage/connection_manager.py` | 连接管理，共享数据库连接 |
| `SchemaRegistry` | `src/core/storage/schema_registry.py` | 表结构注册和迁移 |
| `knowledge_bank.db` | `data/knowledge_bank.db` | 共享现有数据库文件 |

**新增组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| `SurveyTaskStore` | `src/survey/stores.py` | 调研任务存储，继承SQLiteStore |
| `SurveyResponseStore` | `src/survey/stores.py` | 调研响应存储，继承SQLiteStore |
| `SurveyPersonaStore` | `src/survey/stores.py` | AI画像存储，继承SQLiteStore |
| `SurveyCheckpointStore` | `src/survey/stores.py` | 检查点存储，继承SQLiteStore |
| `SURVEY_*_SCHEMA` | `src/core/storage/schemas.py` | 调研表Schema定义 |

---

## 七、验收标准

### 7.1 功能验收

- [x] 工作流简化为两种核心模式（third_party / ai_simulation）
- [x] 用户可在交互流程中配置调研参数（SmartClarifier.configure_survey）
- [x] 用户可预览问卷设计（survey_design_review 交互步骤）
- [x] 问卷Word文档自动生成并保存（questionnaire_word.html 模板）
- [x] AI模拟原始数据保存到数据库（survey_responses 表）
- [x] 调研结果作为独立章节出现在报告中（_build_survey_section 方法）
- [x] 数据可追溯到主控研究任务（parent_task_id 字段）
- [x] 检查点机制支持任务中断恢复（survey_checkpoints 表）
- [x] 第三方平台数据格式统一转换（_convert_response 方法）

### 7.2 测试验证结果

**测试时间**: 2026-04-18 11:37

**测试结果**: ✅ 全部通过

```
Task saved to database: task_xxx ✅
Checkpoint created: cp_xxx for task xxx ✅
Saved 100 responses and 100 personas to database ✅
Task status updated: task_xxx -> completed ✅
Survey completed successfully ✅
Document generated: research_xxx_report.docx ✅
```

### 7.3 实战测试结果

**测试时间**: 2026-04-18 13:30

**测试主题**: 中国电动汽车消费者购车意愿研究

**测试配置**:
- 调研模式: ai_simulation
- 样本数量: 100
- 研究维度: 5个

**测试结果**: ✅ 全部通过

| 验证项 | 结果 | 详情 |
|--------|------|------|
| 调研触发 | ✅ | `检测到调研配置，启动调研集成` |
| 问卷文档生成 | ✅ | `questionnaire.docx` 已生成 |
| 数据库存储 | ✅ | 任务、响应、画像全部入库 |
| 检查点创建 | ✅ | 2个检查点创建成功 |
| 研究流程执行 | ✅ | 5个Agent并行执行 |
| 报告生成 | ✅ | `research_7624899f_report.docx` |

**数据库统计**:
```
调研任务: 3个已完成
调研响应: 220份
AI画像: 220个
检查点: 20个
```

### 7.4 已修复的问题

| 问题 | 解决方案 |
|------|----------|
| 问卷Word模板缺失 | 创建 `questionnaire_word.html` |
| 异步调用错误 | `transform_to_html` 是同步方法 |
| ConnectionManager初始化 | 添加 `base_path` 参数 |
| ForeignKeyDef参数顺序 | 修正为 `(columns, ref_table, ref_columns)` |
| SQL保留字冲突 | `values` → `value_preferences` |
| Store ID列名 | 添加 `_get_id_column()` 方法 |
| Persona对象处理 | 支持 `__dict__` 和 `dict` 格式 |
| Persona ID冲突 | 使用 `task_id` 前缀生成唯一ID |

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 工作流重构影响现有功能 | 高 | 保留旧接口兼容层，渐进式迁移 |
| 第三方平台对接复杂 | 中 | 先实现Mock后端验证流程，后续对接真实API |
| 文档生成性能问题 | 低 | 异步生成，大文件分页处理 |
| 数据存储空间增长 | 中 | 设置数据保留策略，支持清理旧数据 |
