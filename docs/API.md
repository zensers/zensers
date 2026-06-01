# Zensers API Documentation

## Overview

Zensers is an intelligent market research platform based on multi-Agent collaboration, supporting the full process automation from requirement analysis to report generation.

---

## Part 1: Core Agent API

### 1.1 DocumentGenerationAgent

Document generation Agent, supports multiple output formats and version control.

**Location**: `src/agents/fixed_agents/document_generation_agent.py`

**Initialization**:
```python
from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

agent = DocumentGenerationAgent(
    agent_id='doc_gen_001',
    storage_path='data/documents'
)
```

**Supported Operations**:

| Action | Description | Parameters |
|--------|-------------|------------|
| `produce_document` | Generate document | `task_id`, `research_result`, `output_format` |
| `regenerate_document` | Regenerate | `task_id`, `version_id` |
| `adjust_content` | Content adjustment | `task_id`, `adjustments` |
| `export_document` | Export document | `task_id`, `export_path`, `format` |
| `list_versions` | Version listing | `task_id` |
| `rollback_version` | Version rollback | `task_id`, `version_id` |

**Example**:
```python
result = await agent.execute({
    'action': 'produce_document',
    'task_id': 'research_001',
    'research_result': {
        'title': 'Market Analysis Report',
        'sections': [...]
    },
    'output_format': 'docx'
})
```

---

### 1.2 LayoutDesignAgent

Layout design Agent, responsible for formatted report output.

**Location**: `src/agents/fixed_agents/layout_design_agent.py`

**Initialization**:
```python
from src.agents.fixed_agents.layout_design_agent import LayoutDesignAgent

agent = LayoutDesignAgent('layout_agent')
```

**Execution**:
```python
result = await agent.execute({
    'content': '# Report Title\n...',
    'output_format': 'docx',
    'style_config': {...}
})
```

---

### 1.3 QualityCheckAgent

Quality check Agent, validates report quality.

**Location**: `src/agents/fixed_agents/quality_check_agent.py`

---

### 1.4 SurveyIntegrationAgent

Survey integration Agent, handles survey data.

**Location**: `src/agents/fixed_agents/survey_integration_agent.py`

---

## Part 2: Skill API

### 2.1 DocxSkill

Word document generation skill.

**Location**: `src/skills/docx_skill.py`

**Supported Operations**:

| Action | Description |
|--------|-------------|
| `create` | Create new document |
| `add_heading` | Add heading |
| `add_paragraph` | Add paragraph |
| `add_table` | Add table |
| `build_report` | Build complete report |

**Example**:
```python
from src.skills.docx_skill import DocxSkill

skill = DocxSkill()
result = await skill.execute(
    action='build_report',
    filepath='output/report.docx',
    title='Research Report',
    sections=[
        {'heading': 'Chapter 1', 'content': '...'},
        {'heading': 'Chapter 2', 'content': '...'},
    ]
)
```

---

### 2.2 SearchSkill

Search skill, supports web search.

**Location**: `src/skills/search_skill.py`

---

### 2.3 WebScraperSkill

Web scraping skill.

**Location**: `src/skills/web_scraper_skill.py`

---

### 2.4 LLMSkill

LLM invocation skill.

**Location**: `src/skills/llm_skill.py`

---

## Part 3: Core Service API

### 3.1 ResearchOrchestrator

Research scheduler, coordinates the entire research flow.

**Location**: `src/core/orchestrator/research_orchestrator.py`

**Initialization**:
```python
from src.core.orchestrator.research_orchestrator import ResearchOrchestrator

orchestrator = ResearchOrchestrator()
```

**Execute Research**:
```python
result = await orchestrator.execute_research(
    topic='New Energy Vehicle Market Analysis',
    requirements=['Market Size', 'Competitive Analysis'],
    output_format='docx'
)
```

---

### 3.2 DocumentVersionManager

Document version manager.

**Location**: `src/core/storage/document_version_manager.py`

**Main Methods**:

| Method | Description |
|--------|-------------|
| `create_version()` | Create new version |
| `get_version()` | Get version |
| `list_versions()` | List versions |
| `compare_versions()` | Compare versions |
| `rollback_version()` | Rollback version |

---

### 3.3 ExportManager

Export manager.

**Location**: `src/core/storage/export_manager.py`

**Main Methods**:

| Method | Description |
|--------|-------------|
| `export_document()` | Export document |
| `list_exports()` | List export records |
| `get_export()` | Get export record |

---

### 3.4 ContentOrchestrator

Content orchestrator, converts research results into structured format.

**Location**: `src/content/content_orchestrator.py`

**Usage**:
```python
from src.content.content_orchestrator import ContentOrchestrator

orchestrator = ContentOrchestrator()
html = orchestrator.transform_to_html(
    research_result={...},
    output_format='docx'
)
```

---

## Part 4: Converter API

### 4.1 HTMLToWordConverter

HTML to Word converter.

**Location**: `src/converters/html_to_word.py`

**Usage**:
```python
from src.converters.html_to_word import HTMLToWordConverter

converter = HTMLToWordConverter()
result = converter.convert(
    html='<article>...</article>',
    output_path='output/report.docx'
)
```

---

### 4.2 HTMLToPPTConverter

HTML to PPT converter.

**Location**: `src/converters/html_to_ppt.py`

---

## Part 5: Chart Generation API

### 5.1 ChartGenerator

Professional chart generator, supports McKinsey style.

**Location**: `src/services/chart_generator.py`

**Supported Chart Types**:

| Type | Description |
|------|-------------|
| `BAR` | Bar chart |
| `HBAR` | Horizontal bar chart |
| `BAR_LINE` | Bar + line chart combination |
| `PIE` | Pie chart |
| `LINE` | Line chart |
| `RADAR` | Radar chart |
| `SCATTER` | Scatter chart |
| `BUBBLE` | Bubble chart |
| `WATERFALL` | Waterfall chart |
| `QUADRANT` | Quadrant chart |

**Example**:
```python
from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType

generator = ChartGenerator('output/charts')

result = generator.generate(ChartConfig(
    chart_type=ChartType.BAR,
    title='Market Share Analysis',
    data={
        'categories': ['A', 'B', 'C'],
        'values': [30, 45, 25]
    },
    ylabel='Market Share (%)'
))
```

---

## Part 6: Configuration

### 6.1 Main Configuration File

**Location**: `config/settings.yaml`

### 6.2 Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DATABASE_URL` | Database connection URL |

---

## Part 7: Error Handling

All API calls return a unified format:

```python
{
    'success': True/False,
    'data': {...},          # Data returned on success
    'error': '...',         # Error message on failure
    'error_code': '...'     # Error code
}
```

**Common Error Codes**:

| Code | Description |
|------|-------------|
| `INVALID_INPUT` | Invalid input parameters |
| `NOT_FOUND` | Resource not found |
| `PERMISSION_DENIED` | Insufficient permissions |
| `INTERNAL_ERROR` | Internal error |

---

## Part 8: Version Information

- **Version**: 1.0.0
- **Python Requirement**: 3.10+
- **Last Updated**: January 2024
