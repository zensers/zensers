# Market Research Report Generation System - Complete Feature Report

## I. System Architecture Overview

### 1. Core Components

| Component | File Path | Function |
|-----------|----------|----------|
| CLI Entry | `src/cli/main.py` | Command-line interface providing research/status/download commands |
| Main Orchestrator | `src/core/orchestrator/orchestrator.py` | Six-layer architecture workflow orchestration |
| Execution Engine | `src/core/orchestrator/execution/engine.py` | Agent classification, phased execution, concurrency control |
| Task Persistence | `src/core/task_persistence.py` | Task state saving, checkpoint, recovery |
| Auto Recovery | `src/core/auto_recovery.py` | Crash detection, automatic recovery |
| Content Orchestrator | `src/content/content_orchestrator.py` | HTML generation, template rendering |
| Document Conversion | `src/converters/html_to_word.py` | HTML to Word/PPT/PDF |

### 2. Configuration Files

| Config | Path | Description |
|--------|------|-------------|
| System Config | `config/system.yaml` | Database, concurrency, timeout settings |
| Agent Config | `config/agents.yaml` | LLM model, capability configuration |
| MCP Config | `config/mcp.yaml` | MCP server configuration |
| Report Templates | `config/templates/*.yaml` | 13 professional report templates |
| Document Templates | `config/document_templates/*.html` | 3 document format templates |

## II. Complete Research Report Generation Flow

```
User Input Research Request
       ↓
[1] Requirement Clarification (SmartClarifier)
    - Select output type (industry_report/investment_memo, etc.)
    - Select template
    - Adjust chapter structure
    - Configure parameters (region, time range, etc.)
       ↓
[2] User Confirms Research Plan
       ↓
[3] Intent Analysis (IntentGate)
    - Identify research intent
    - Assess complexity
       ↓
[4] Create Professional Agents (AgentFactory)
    - CategoryRouter routing
    - Skills intelligent matching
    - One Agent per research dimension
       ↓
[5] Execute Tasks (ExecutionEngine)
    ┌─────────────────────────────────────┐
    │ Phase 1: DATA_COLLECTION           │
    │   - Execute data collection Agents  │
    │   - Web search, API calls, scraping │
    ├─────────────────────────────────────┤
    │ Phase 2: ANALYSIS                  │
    │   - Execute analysis Agents in parallel│
    │   - Market analysis, competitive analysis, trend forecasting│
    ├─────────────────────────────────────┤
    │ Phase 3: REPORT_GENERATION         │
    │   - Generate research report       │
    │   - Aggregate Agent results        │
    └─────────────────────────────────────┘
       ↓
[6] Aggregate Results (ResultAggregator)
    - Merge Agent results
    - KnowledgeCompiler compiles knowledge
    - WisdomRecorder records experience
       ↓
[7] Generate Report
    - ReportGenerator → Markdown/HTML
    - DocumentGenerationAgent → DOCX/PPTX/PDF
       ↓
[8] Preview and Revision Loop
    - PreviewGenerator generates preview
    - User feedback → RevisionService revision
    - Infinite loop until satisfied
       ↓
[9] Store Results (StorageManager)
    - Save task results
    - Update knowledge bank
```

## III. Checkpoint Recovery Function

### 1. Task State Flow

```
CREATED → INITIALIZING → RUNNING → PAUSED → COMPLETED/FAILED
```

### 2. Checkpoint Mechanism

- **Create Checkpoint**: Periodically save current state during task execution
- **Checkpoint Content**: step_name, step_index, total_steps, data
- **Recovery Flow**: Recover from latest checkpoint, continue execution

### 3. Auto Recovery

```
System Startup
    ↓
Detect shutdown marker
    ↓
[If not exists] → System crashed, needs recovery
    ↓
Find RUNNING/INITIALIZING state tasks
    ↓
Execute recovery:
  - QUICK mode: Recover from latest checkpoint
  - FULL mode: Full recovery from WAL
    ↓
Continue task execution
```

### 4. Interactive Recovery

```
User enters .resume command
    ↓
Scan and list recoverable tasks
    ↓
User selects task
    ↓
Select action: [c]continue / [v]details / [d]discard
```

## IV. Task Restart Function

### 1. Task Persistence Storage

| Storage Type | Path | Format |
|--------------|------|--------|
| Task State | `data/tasks/{task_id}.json` | JSON |
| Agent Session | `data/sessions/agents/{session_id}.json` | JSON |
| Survey Tasks | `data/survey_tasks/{task_id}.json` | JSON |
| WAL Log | `data/wal/` | JSON Lines |
| Checkpoint | `data/checkpoints/` | JSON |

### 2. Restart Trigger Conditions

- Auto recovery after system crash
- User manually enters `.resume` command
- Retry after task timeout
- Degradation after Agent failure

### 3. Recovery Guarantees

- **Atomic Write**: Temporary file + atomic rename
- **Checksum Verification**: MD5 checksum prevents data corruption
- **WAL Mechanism**: Write-Ahead Log guarantees data integrity

## V. Detail Optimization Features

### 1. Report Quality Optimization

- **CSS Cleaning**: Automatically remove CSS code from templates
- **Template Tag Cleaning**: Remove unrendered template syntax
- **Content Validation**: Check report content completeness

### 2. Template Rendering Optimization

- **Nested Loop Support**: Handle multi-level nested loops correctly
- **Conditional Judgment**: Correct handling of empty lists/None
- **Variable Resolution**: Support nested attribute access

### 3. Concurrency Control Optimization

- **Max Concurrency**: Configurable (default 10)
- **Phased Execution**: Data collection → analysis → report generation
- **Timeout Control**: Configurable (default 1800 seconds)

### 4. Error Handling Optimization

- **Retry Mechanism**: Auto retry on failure (up to 3 times)
- **Degradation Chain**: Attempt degradation plan after Agent failure
- **Error Tracking**: Record error history

## VI. Usage Guide

### CLI Commands

```bash
# Start a complete research task
python -m src.cli.main research "New Energy Vehicle Market Analysis" -o report.docx

# Query task status
python -m src.cli.main status <task_id>

# Continuously monitor task
python -m src.cli.main status <task_id> --watch

# Download report
python -m src.cli.main download <task_id> -o output.docx -f docx

# Start interactive conversation
python -m src.cli.main chat start

# View knowledge bank
python -m src.cli.main knowledge summary
```

### Python API

```python
from core.orchestrator.orchestrator import ResearchOrchestrator

# Create orchestrator
orchestrator = ResearchOrchestrator()

# Execute research
result = await orchestrator.research("New Energy Vehicle Market Analysis")

# Get report
report = result["report"]
```

## VII. Test Results

| Test Item | Status |
|-----------|--------|
| System Component Import | ✅ Passed |
| Task Persistence | ✅ Passed |
| Report Generation Flow | ✅ Passed |
| Checkpoint Recovery | ✅ Passed |
| Checkpoint Mechanism | ✅ Passed |
| Configuration System | ✅ Passed |
| Storage Structure | ✅ Passed |

## VIII. Generated Test Reports

- **Location**: `output/test_reports/`
- **Files**: 
  - `test_report.docx` (37,091 bytes)
  - `final_test_report.docx` (37,601 bytes)
  - `complete_test_report.docx` (37,234 bytes)
- **Content**: Includes complete chapters, key findings, conclusions
- **Quality**: No CSS residue, no template tag residue
