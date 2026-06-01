# Zensers System Usage Guide

> Version: v1.2 | Updated: 2026-05-04

---

## 1. System Overview

Zensers is an automated market research report generation system that completes the full process from requirements analysis to professional report generation through multi-Agent collaboration.

### Core Capabilities

| Capability | Description |
|------|------|
| Intelligent Requirements Analysis | Automatically parse research requirements, generate research framework |
| Multi-source Data Collection | Supports industry research, web search, data provider integration |
| Survey Questionnaires | AI-simulated respondents, quickly collect market insights |
| Professional Report Generation | McKinsey-style reports, including charts, statistics, analysis |
| Quality Check | Automatically check content completeness, data accuracy |
| Checkpoint Recovery | Supports task pause, resume, revision |

---

## 2. Quick Start

### 2.1 Environment Requirements

- Python 3.10+
- Dependency Installation: `pip install -r requirements.txt`

### 2.2 Basic Usage

```python
from src.core.orchestrator.orchestrator import ResearchOrchestrator

# Create orchestrator
orchestrator = ResearchOrchestrator()

# Execute research task (interactive mode)
result = await orchestrator.research(
    "Analyze China's new energy vehicle market development trends",
    interaction_mode=True,
    interaction_callback=my_callback
)

# Execute research task (auto mode)
result = await orchestrator.research(
    {
        "topic": "Healthcare AI Market",
        "aspects": ["Market Size", "Competitive Landscape", "Development Trends"],
        "output_format": "docx"
    },
    interaction_mode=False
)
```

### 2.3 Command Line Interface (CLI)

The system provides a complete CLI tool `zensers`, invoked via `python -m src.cli.main`.

```bash
# View help
python -m src.cli.main --help

# Research task
python -m src.cli.main research "Analyze new energy vehicle market"

# View task status
python -m src.cli.main status <task_id>

# Session management
python -m src.cli.main session list
python -m src.cli.main session show <task_id>
python -m src.cli.main session resume <task_id>

# Knowledge bank
python -m src.cli.main knowledge summary
python -m src.cli.main knowledge search <query>
```

#### Survey CLI Commands

```bash
# Create survey (from JSON file)
python -m src.cli.main survey create "Customer Satisfaction Survey" --questions survey.json

# List surveys
python -m src.cli.main survey list

# Run AI simulation
python -m src.cli.main survey simulate <survey_id> --count 100 --template "First-tier White-collar"

# Query simulation status
python -m src.cli.main survey status <survey_id>

# Get simulation results
python -m src.cli.main survey results <survey_id> --limit 50

# Generate analysis report
python -m src.cli.main survey analyze <survey_id> --output report.md

# View available persona templates
python -m src.cli.main survey templates

# View available regional data
python -m src.cli.main survey regions
```

**Survey JSON Format**:
```json
[
  {
    "id": "q1",
    "text": "Are you satisfied with the product?",
    "type": "single_choice",
    "options": ["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied"],
    "required": true
  },
  {
    "id": "q2",
    "text": "Would you recommend it to a friend?",
    "type": "yes_no"
  }
]
```

### 2.4 Output Location

All outputs are uniformly stored in the `output/reports/{task_id}/` directory:

```
output/reports/{task_id}/
├── report.docx              # Research Report
├── survey/                  # Survey Related
│   ├── questionnaire.docx   # Questionnaire Document
│   └── analysis.json        # Analysis Results
├── charts/                  # Chart Files
└── preview/                 # Preview Files
```

---

## 3. Core Process

### 3.1 Research Process

```
Requirement Input → Requirement Clarification → Intent Analysis → Task Planning
    ↓
Agent Creation → Data Collection → Survey Analysis → Result Aggregation
    ↓
Document Generation → Quality Check → Preview Revision → Output Report
```

### 3.2 Survey Process

```
Questionnaire Design → AI Simulated Respondents → Response Collection
    ↓
Statistical Analysis → Chart Generation → Insight Extraction
    ↓
Result Integration → Report Section
```

---

## 4. Feature Details

### 4.1 Survey Analysis

The survey module supports a complete statistical indicator system (zero external dependencies):

| Indicator Type | Indicator Items | Purpose |
|----------|--------|------|
| Descriptive Statistics | Response count, distribution, mean, median, std deviation | Basic data overview |
| Inferential Statistics | **t-test** (Welch's) + Cohen's d | Significance of difference between two group means |
| Inferential Statistics | **One-way ANOVA** (F-test) | Multi-group mean comparison |
| Inferential Statistics | **Chi-square test** | Categorical variable independence test |
| Correlation Analysis | **Pearson correlation coefficient** + significance test | Continuous variable linear correlation |
| Non-parametric Tests | **Mann-Whitney U** | Two-group comparison (no normality assumption) |
| Non-parametric Tests | **Kruskal-Wallis H** | Multi-group comparison (no normality assumption) |
| Effect Size | Cohen's d | Practical significance of differences |
| Sentiment Analysis | Bilingual sentiment scoring (28,000+ word dictionary) | Open-ended text analysis |
| Calibration Validation | JS divergence, variance ratio, overlap coefficient | Simulation quality assessment |

All statistical tests return p-value + `significant` boolean flag, directly used for report annotation.

### 4.2 Chart Generation

The system automatically generates the following chart types:

| Chart Type | Purpose |
|----------|------|
| Bar Chart | Categorical data comparison |
| Horizontal Bar Chart | Ranking display |
| Donut Chart | Proportion distribution |
| Line Chart | Trend changes |
| Radar Chart | Multi-dimensional assessment |
| Scatter Plot | Two-variable relationship |
| Bubble Chart | Three-dimensional data display |
| Waterfall Chart | Cumulative changes |
| Quadrant Chart | Strategic positioning |

### 4.3 Quality Check

Quality Check Agent automatically checks:

- Content completeness (whether required sections exist)
- Data accuracy (whether values are reasonable)
- Format compliance (whether template requirements are met)

### 4.4 Preview and Revision

Supports interactive report revision:

- Preview generated reports
- Provide revision feedback
- Automatically revise specified sections
- Multiple rounds of revision until satisfied

---

## 5. Configuration Guide

### 5.1 System Configuration

Configuration file location: `config/system.yaml`

```yaml
paths:
  data_dir: "data"
  cache_dir: "cache"
  report_output_dir: "output/reports"
  template_dir: "config/templates"
```

### 5.2 Agent Configuration

Configuration file location: `config/agents.yaml`

```yaml
survey:
  default_target_count: 100
  simulation_mode: "ai"
  analysis_depth: "full"

quality_check:
  min_word_count: 1000
  min_sections: 3
  required_sections:
    - "Executive Summary"
```

---

## 6. API Interface

### 6.1 Main Methods

```python
# Research task
result = await orchestrator.research(query, **options)

# Resume task
result = await orchestrator.resume(task_id)

# Preview report
preview = await orchestrator.preview(task_id)

# Revise report
result = await orchestrator.revise(task_id, revision_request)
```

### 6.2 Survey API (REST)

The survey module exposes 10 REST endpoints via FastAPI (mounted at `src/api/main.py`):

| Method | Path | Purpose |
|------|------|------|
| POST | `/api/v1/surveys` | Create survey |
| GET | `/api/v1/surveys` | List |
| GET | `/api/v1/surveys/{id}` | Details |
| POST | `/api/v1/surveys/{id}/distribute` | Distribute |
| POST | `/api/v1/surveys/{id}/simulate` | AI Simulation |
| GET | `/api/v1/surveys/{id}/status` | Status |
| GET | `/api/v1/surveys/{id}/results` | Results |
| GET | `/api/v1/surveys/{id}/analysis` | Analysis Report |
| GET | `/api/v1/surveys/regions` | Regional Data |
| GET | `/api/v1/surveys/templates` | Persona Templates |

### 6.3 Return Structure

```python
{
    "success": True,
    "task_id": "task_xxx",
    "output_path": "output/reports/task_xxx/report.docx",
    "statistics": {
        "word_count": 5000,
        "sections": 8,
        "charts": 5
    },
    "quality_score": 85.5
}
```

---

## 7. Frequently Asked Questions

### Q1: Charts not showing after report generation?

Ensure `matplotlib` is properly installed, and check the `output/reports/{task_id}/charts/` directory for image files.

### Q2: How to modify report templates?

Template files are located in the `config/document_templates/` directory:
- `word_default.html` - Word report template
- `ppt_default.html` - PPT report template

### Q3: How to add custom data sources?

Implement the `DataProvider` interface and register with `DataProviderRegistry`.

### Q4: How to resume an interrupted task?

```python
result = await orchestrator.resume(task_id)
```

---

## 8. Changelog

### v1.2 (2026-05-04)

- Survey module CLI integration (8 survey subcommands)
- Statistical inference engine (t-test, ANOVA, Chi-square, Pearson, Mann-Whitney, Kruskal-Wallis)
- Chi-square auto-integrated into cross-tabulation analysis
- Skip logic / conditional branching support
- Charts auto-integrated into report generation
- Bilingual sentiment dictionary extended to 28,000+ words
- Multi-country demographic data support (US/UK/DE/JP/FR)
- WVS calibration data integration (66 countries)
- Configurable bias detection threshold
- Random seed support (reproducible results)
- Token counting switched to tiktoken
- DeepSeek API compatibility fix

### v1.1 (2026-04-19)

- Fixed survey data complete return
- Integrated chart generation functionality
- Fixed template nested loop rendering
- Integrated Quality Check Agent
- Added advanced statistical indicators

### v1.0 (2026-04-17)

- McKinsey-style report generation
- Document Generation Agent enhancements
- Project structure optimization

---

> Technical support: See [API.md](./API.md) or [CHANGELOG.md](./CHANGELOG.md)
