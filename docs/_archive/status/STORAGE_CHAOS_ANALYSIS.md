# Document Storage Chaos Analysis

## I. Problem Symptoms

### Current Storage Location Chaos

| Expected Location | Actual Location | Description |
|------------------|----------------|-------------|
| `output/reports/` | `output/passenger_vehicle_research/` | Research report saved to custom directory |
| - | `output/survey/` | Questionnaire documents saved to separate directory |
| - | `output/test_reports/` | Test reports saved to test directory |
| `docs/research_results/` | Not used | StorageManager default path |
| - | `data/knowledge_bank.db` | Survey data saved to database |

### Root Cause: Hard-coded paths, no unified management

## II. Hard-coded Path Inventory

### 1. Orchestrator Default Storage Path

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Line 209

```python
self._storage_path = storage_path or Path("docs/research_results")
```

**Problem**: Default saves to `docs/research_results`, but this directory was never used

### 2. Questionnaire Storage Path Hard-coded

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Line 1734

```python
survey_agent = SurveyIntegrationAgent(
    agent_id=f"{task_id}_survey",
    storage_path=f"output/survey/{task_id}"  # Hard-coded!
)
```

**Problem**: Questionnaire saved to `output/survey/`, not in unified report directory

### 3. StorageManager Default Path

**File**: `src/core/orchestrator/output/storage_manager.py`
**Location**: Line 51

```python
base_path: Path = Path("docs/research_results")
```

**Problem**: Another default path

### 4. Test Script Custom Path

**File**: `run_passenger_vehicle_research.py`

```python
result = await orchestrator.research(
    user_input=research_input,
    output_dir="output/passenger_vehicle_research",  # Custom!
    interaction_mode=False,
)
```

**Problem**: Each test script uses a different directory

### 5. DocumentGenerationAgent Default Path

**File**: `src/agents/fixed_agents/document_generation_agent.py`
**Location**: Line 185

```python
str(Path("output").resolve()),
```

### 6. SurveyIntegrationAgent Default Path

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Location**: Line 814

```python
output_dir = Path(self.storage_path or "output/survey") / survey["survey_id"]
```

## III. Configuration System Status

### Configuration File Already Defined

**File**: `config/system.yaml`

```yaml
paths:
  data_dir: data
  cache_dir: cache
  temp_dir: tmp
  report_output_dir: output/reports
```

### Settings Already Loaded

**File**: `src/config/settings.py`

```python
report_output_dir: str = "output/reports"
```

### Problem: Configuration Not Used!

All components use hard-coded paths instead of reading `settings.system.report_output_dir`

## IV. Unified Storage Plan

### Standard Directory Structure

```
E:\market_report_systerm\
├── output/                           # All output files
│   ├── reports/                      # Research reports (unified location)
│   │   ├── research_20260419_xxx/    # Organized by task ID
│   │   │   ├── report.docx           # Research report
│   │   │   ├── survey/               # Survey related (subdirectory)
│   │   │   │   ├── questionnaire.docx
│   │   │   │   └── survey_data.json
│   │   │   └── preview/              # Preview files
│   │   └── ...
│   ├── cache/                        # Cache files
│   └── temp/                         # Temporary files
│
├── data/                             # Persistent data
│   ├── knowledge_bank.db             # Knowledge base database
│   ├── tasks/                        # Task status
│   └── sessions/                     # Session data
│
└── docs/                             # Documentation
    └── research_results/             # Historical research results (optional)
```

### Core Principles

1. **One task, one directory**: All related files grouped together
2. **Configuration-driven**: Paths read from configuration, not hard-coded
3. **Clear hierarchy**: All files organized under `output/reports/{task_id}/`

## V. Fix Checklist

### Fix Point 1: Orchestrator Default Path

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Line 209

```python
# Before fix
self._storage_path = storage_path or Path("docs/research_results")

# After fix
from src.config import settings
self._storage_path = storage_path or Path(settings.system.report_output_dir)
```

### Fix Point 2: Questionnaire Storage Path

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Line 1734

```python
# Before fix
survey_agent = SurveyIntegrationAgent(
    agent_id=f"{task_id}_survey",
    storage_path=f"output/survey/{task_id}"
)

# After fix: Use unified report directory
survey_output_dir = Path(output_dir or settings.system.report_output_dir) / task_id / "survey"
survey_agent = SurveyIntegrationAgent(
    agent_id=f"{task_id}_survey",
    storage_path=str(survey_output_dir)
)
```

### Fix Point 3: StorageManager Default Path

**File**: `src/core/orchestrator/output/storage_manager.py`
**Location**: Line 51

```python
# Before fix
base_path: Path = Path("docs/research_results")

# After fix
from src.config import settings
base_path: Path = Path(settings.system.report_output_dir)
```

### Fix Point 4: DocumentGenerationAgent Default Path

**File**: `src/agents/fixed_agents/document_generation_agent.py`
**Location**: Line 185

```python
# Before fix
str(Path("output").resolve()),

# After fix
from src.config import settings
str(Path(settings.system.report_output_dir).resolve()),
```

### Fix Point 5: SurveyIntegrationAgent Default Path

**File**: `src/agents/fixed_agents/survey_integration_agent.py`
**Location**: Line 814

```python
# Before fix
output_dir = Path(self.storage_path or "output/survey") / survey["survey_id"]

# After fix
from src.config import settings
output_dir = Path(self.storage_path or settings.system.report_output_dir) / survey["survey_id"]
```

## VI. Post-Fix Results

### Unified Output Location

```
output/reports/research_4aec2cae/
├── report.docx                    # Research report
├── survey/                        # Survey related
│   ├── questionnaire.docx         # Questionnaire document
│   └── responses.json             # Response data
└── preview/                       # Preview files
```

### Data Location Unchanged

```
data/
├── knowledge_bank.db              # Knowledge base (includes survey data)
├── tasks/                         # Task status
└── sessions/                      # Session data
```

## VII. Cleanup Suggestions

### Delete Redundant Directories

```
Delete: output/survey/               # Merge under reports
Delete: output/test_reports/         # Merge under reports
Delete: output/passenger_vehicle_research/  # Merge under reports
Delete: output/ev_survey_research/   # Merge under reports
Delete: output/documents/generated/  # Merge under reports
Delete: docs/research_results/       # Never used
```

### Keep Directories

```
Keep: output/reports/              # Unified report directory
Keep: output/cache/                # Cache
Keep: output/temp/                 # Temporary files
Keep: data/                        # Data directory
```
