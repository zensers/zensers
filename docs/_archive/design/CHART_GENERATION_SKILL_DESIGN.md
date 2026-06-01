# Chart Generation Skill Design Document

> Version: v1.0  
> Date: 2026-04-30  
> Status: Design Proposal

---

## Table of Contents

1. [Problem Diagnosis](#1-problem-diagnosis)
2. [Root Cause Analysis](#2-root-cause-analysis)
3. [Design Proposal](#3-design-proposal)
4. [Data Storage Strategy](#4-data-storage-strategy)
5. [Implementation Details](#5-implementation-details)
6. [Modification List](#6-modification-list)
7. [Test Plan](#7-test-plan)

---

## 1. Problem Diagnosis

### 1.1 Symptom Description

- Charts have been generated (93 PNG files in `output/charts/` directory)
- But charts are not embedded in the report
- Generated chart data quality is poor (e.g., "factual data" placeholders appear)

### 1.2 Problem Location

Through code analysis, the problem chain is identified:

```
Task decomposition phase (strategies.py)
    ↓
No chart_skill assigned to any Agent
    ↓
Data analysis Agent only produces text, not structured data
    ↓
Report generation Agent receives pure text
    ↓
Post-processing phase attempts to extract data from text using regex
    ↓
Data extraction fails or quality is poor
    ↓
Chart generation is invalid or data is irrelevant
```

### 1.3 Key Code Locations

| File | Line | Problem |
|------|------|---------|
| `strategies.py` | 37-60 | `ASPECT_SKILL_MAP` has no chart-related Skill |
| `strategies.py` | 374-390 | Report generation Agent's skills don't include chart capability |
| `result_aggregator.py` | 505-511 | Section creation has no `data_points` field |
| `document_generation_agent.py` | 520 | `section.get("data_points", [])` returns empty list |
| `smart_chart_generator.py` | 283-284 | Regex data format matching is inflexible |

---

## 2. Root Cause Analysis

### 2.1 Dilemma

| Dimension | Problem | Cause |
|-----------|---------|-------|
| **Task decomposition phase allocation** | Data may be insufficient, task fails | Intelligent routing **does not know** what specific data will be available at decomposition time |
| **Post-processing phase** | Data extraction fails, charts invalid | Text already generated, structured data lost, can only "guess" using regex |

### 2.2 Information Flow Break

```
At task decomposition: don't know what data will be available -> cannot decide whether to generate charts
    ↓
After data collection: know what data is available -> but Agents have already executed, no chart capability
    ↓
After report generation: text already fixed -> can only "reverse extract" data from text, poor quality
```

### 2.3 Data Flow Break Point

```
Agent executes -> produces data_points -> 
ExecutionEngine collects aggregated_data_points -> 
ResultAggregator converts to sections -> data_points lost
DocumentGenerationAgent gets section["data_points"] -> [] empty list
SmartChartGenerator has no structured data -> can only use regex extraction
```

**Key Problem**: `data_points` exists in the top-level `research_result`, but is not mapped to each `section`!

---

## 3. Design Proposal

### 3.1 Core Idea

**Introduce `ChartGenerationSkill`, called during the data analysis phase, not during the post-processing phase after report generation.**

### 3.2 Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│ Task Decomposition Phase (strategies.py)                                     │
│                                                                 │
│ ASPECT_SKILL_MAP = {                                            │
│     "market_size": ["llm_skill", "search_skill", "chart_generation"],│
│     "market_share": ["llm_skill", "search_skill", "chart_generation"],│
│     "sales_analysis": ["llm_skill", "search_skill", "chart_generation"],│
│     "competitive_landscape": ["llm_skill", "search_skill", "chart_generation"],│
│     "growth_analysis": ["llm_skill", "search_skill", "chart_generation"],│
│     ...                                                         │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Agent Execution Phase (GenericAgent)                                    │
│                                                                 │
│ 1. search_skill -> collect data                                       │
│ 2. llm_skill -> analyze data, produce data_points                        │
│ 3. chart_generation -> generate charts based on data_points                  │
│                                                                 │
│ Return Structure:                                                       │
│ {                                                               │
│     "content": "Analysis text...",                                    │
│     "data_points": [...],      <- structured data                      │
│     "charts": [                <- chart information                        │
│         {                                                       │
│             "id": "chart_1",                                    │
│             "type": "bar",                                      │
│             "title": "Market Size Trend",                             │
│             "path": "charts/market_size_bar.png",                │
│             "data": {"categories": [...], "values": [...]},      │
│             "caption": "Figure 1: 2020-2025 Market Size"                 │
│         }                                                       │
│     ]                                                           │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Result Aggregation Phase (ResultAggregator)                                   │
│                                                                 │
│ section = {                                                      │
│     "id": "market_size",                                         │
│     "title": "Market Size",                                          │
│     "content": "Analysis text...",                                      │
│     "data_points": [...],  <- structured data (new)                   │
│     "charts": [...]       <- chart information (existing, needs improvement)               │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Report Generation Phase (DocumentGenerationAgent)                            │
│                                                                 │
│ - section["charts"] already contains chart paths                                │
│ - Insert charts directly into document                                              │
│ - No post-processing data extraction needed                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Advantage Comparison

| Aspect | Current Approach (Post-processing) | New Approach (Skill Integration) |
|--------|-----------------------------------|----------------------------------|
| **Data source** | Regex extraction from text (poor quality) | Direct use of `data_points` (structured) |
| **Decision timing** | After report generation (information lost) | During data analysis (information complete) |
| **Chart quality** | Irrelevant data, placeholders | Generated based on real data |
| **Traceability** | Cannot trace data source | Charts linked to data points |
| **Flexibility** | Fixed regex patterns | Extensible Skill logic |

---

## 4. Data Storage Strategy

### 4.1 Directory Structure

```
output/
└── reports/
    └── research_1c517df6/              <- Isolated by task ID
        ├── research_1c517df6_report.docx
        ├── research_1c517df6_report.preview.html
        └── charts/                     <- Charts in same directory as report
            ├── market_size_bar.png     <- Named by section
            └── market_share_pie.png
```

### 4.2 Naming Convention

| Chart Type | Naming Format | Example |
|------------|---------------|---------|
| Bar chart | `{section_id}_bar.png` | `market_size_bar.png` |
| Pie chart | `{section_id}_pie.png` | `market_share_pie.png` |
| Line chart | `{section_id}_line.png` | `growth_trend_line.png` |
| Radar chart | `{section_id}_radar.png` | `competitor_radar.png` |

### 4.3 Path Strategy

```python
# Relative path (for HTML preview)
relative_path = f"charts/{section_id}_{chart_type}.png"

# Absolute path (for Word embedding)
absolute_path = str(report_dir / "charts" / f"{section_id}_{chart_type}.png")
```

### 4.4 Chart Data Structure

```python
chart = {
    "id": "chart_1",                    # Chart unique identifier
    "type": "bar",                       # Chart type
    "title": "Market Size Trend",              # Chart title
    "path": "charts/market_size_bar.png", # Relative path
    "absolute_path": "E:\...\charts\...", # Absolute path
    "data": {                            # Raw data (for regeneration)
        "categories": ["2020", "2021", "2022"],
        "values": [100, 150, 200],
        "unit": "100 million yuan"
    },
    "caption": "Figure 1: 2020-2025 Market Size", # Chart caption
    "source": "Public data compilation",              # Data source
    "generated_at": "2026-04-30T10:00:00", # Generation time
    "data_point_ids": ["dp_1", "dp_2"],   # Associated data point IDs
}
```

---

## 5. Implementation Details

### 5.1 ChartGenerationSkill Implementation

```python
# src/skills/chart_generation.py

class ChartGenerationSkill(Skill):
    """
    Chart Generation Skill
    
    Generates professional charts based on structured data.
    """
    
    @property
    def name(self) -> str:
        return "chart_generation"
    
    @property
    def description(self) -> str:
        return "Generate professional charts (bar/pie/line, etc.) based on structured data"
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute chart generation
        
        Args:
            data_points: List of structured data points
            section_id: Section ID (for naming)
            section_title: Section title (for chart type recommendation)
            output_dir: Chart output directory
            
        Returns:
            {
                "success": True,
                "charts": [chart_info, ...],
                "chart_paths": [path1, path2, ...]
            }
        """
        data_points = kwargs.get("data_points", [])
        section_id = kwargs.get("section_id", "unknown")
        section_title = kwargs.get("section_title", "")
        output_dir = kwargs.get("output_dir", "output/charts")
        
        # 1. Analyze data, recommend chart type
        suggestions = self._analyze_data(data_points, section_title)
        
        # 2. Generate charts
        charts = []
        for suggestion in suggestions:
            chart = await self._generate_chart(
                suggestion=suggestion,
                output_dir=output_dir,
                section_id=section_id
            )
            if chart:
                charts.append(chart)
        
        return {
            "success": True,
            "charts": charts,
            "chart_paths": [c["absolute_path"] for c in charts]
        }
    
    def _analyze_data(self, data_points: List[Dict], section_title: str) -> List[Dict]:
        """
        Analyze data, recommend chart type
        
        Rules:
        - Market share data -> Pie chart
        - Time series data -> Line/bar chart
        - Ranking comparison data -> Horizontal bar chart
        - Multi-dimensional evaluation -> Radar chart
        """
        suggestions = []
        
        # Detect market share data
        share_data = self._extract_share_data(data_points)
        if share_data:
            suggestions.append({
                "type": "pie",
                "title": f"{section_title} - Market Share Distribution",
                "data": share_data
            })
        
        # Detect time series data
        time_series = self._extract_time_series(data_points)
        if time_series:
            suggestions.append({
                "type": "line",
                "title": f"{section_title} - Trend Changes",
                "data": time_series
            })
        
        return suggestions
    
    async def _generate_chart(self, suggestion: Dict, output_dir: str, section_id: str) -> Optional[Dict]:
        """Generate a single chart"""
        from src.services.chart_generator import ChartGenerator, ChartType, ChartConfig
        
        generator = ChartGenerator(output_dir=output_dir)
        
        # Map chart types
        type_map = {
            "bar": ChartType.BAR,
            "pie": ChartType.PIE,
            "line": ChartType.LINE,
            "hbar": ChartType.HBAR,
            "radar": ChartType.RADAR,
        }
        
        chart_type = type_map.get(suggestion["type"], ChartType.BAR)
        
        config = ChartConfig(
            chart_type=chart_type,
            title=suggestion["title"],
            data=suggestion["data"],
        )
        
        result = generator.generate(config)
        
        if result.success and result.image_path:
            return {
                "id": f"chart_{section_id}_{suggestion['type']}",
                "type": suggestion["type"],
                "title": suggestion["title"],
                "path": os.path.basename(result.image_path),
                "absolute_path": result.image_path,
                "data": suggestion["data"],
            }
        
        return None
```

### 5.2 Task Decomposition Strategy Modification

```python
# src/core/decomposition/strategies.py

# Modify ASPECT_SKILL_MAP
ASPECT_SKILL_MAP = {
    "market_size": ["llm_skill", "search_skill", "data_analysis", "chart_generation"],
    "market_share": ["llm_skill", "search_skill", "data_analysis", "chart_generation"],
    "competitive_landscape": ["llm_skill", "search_skill", "market_analysis", "chart_generation"],
    "industry_trends": ["llm_skill", "search_skill", "data_analysis", "chart_generation"],
    "sales_analysis": ["llm_skill", "search_skill", "data_analysis", "chart_generation"],
    "growth_analysis": ["llm_skill", "search_skill", "data_analysis", "chart_generation"],
    # ... other dimensions
}
```

### 5.3 ResultAggregator Modification

```python
# src/core/orchestrator/aggregation/result_aggregator.py

# Add data_points mapping in _convert_to_sections() method

def _convert_to_sections(self) -> List[Dict[str, Any]]:
    # ... existing logic ...
    
    for section in self.section_details:
        section_id = section.get("id", "")
        section_name = section.get("name", section_id)
        
        # Extract content
        content = self._extract_content_for_section(section_id, section_name)
        
        # New: Extract data_points for this section
        section_data_points = self._extract_data_points_for_section(section_id, section_name)
        
        # New: Extract charts for this section
        section_charts = self._extract_charts_for_section(section_id, section_name)
        
        sections.append({
            "id": section_id,
            "title": section_name,
            "content": content,
            "subsections": subsections,
            "data_points": section_data_points,  # New
            "charts": section_charts,            # Improved
        })
    
    return sections

def _extract_data_points_for_section(self, section_id: str, section_name: str) -> List[Dict]:
    """Extract data points belonging to this section"""
    data_points = []
    
    if not isinstance(self.data, dict):
        return data_points
    
    # Find matching data_points from aggregated data
    for key, value in self.data.items():
        if key.startswith("_"):
            continue
        
        # Check if it matches current section
        key_lower = key.lower()
        if section_id.lower() in key_lower or section_name.lower() in key_lower:
            if isinstance(value, dict) and "data_points" in value:
                data_points.extend(value["data_points"])
    
    return data_points

def _extract_charts_for_section(self, section_id: str, section_name: str) -> List[Dict]:
    """Extract charts belonging to this section"""
    charts = []
    
    if not isinstance(self.data, dict):
        return charts
    
    for key, value in self.data.items():
        if key.startswith("_"):
            continue
        
        key_lower = key.lower()
        if section_id.lower() in key_lower or section_name.lower() in key_lower:
            if isinstance(value, dict) and "charts" in value:
                charts.extend(value["charts"])
    
    return charts
```

### 5.4 DocumentGenerationAgent Modification

```python
# src/agents/fixed_agents/document_generation_agent.py

def _populate_document_content(self, generator, research_result):
    # ... existing logic ...
    
    for section in sections:
        section_title = section.get("title", "")
        section_content = section.get("content", "")
        section_data_points = section.get("data_points", [])  # Now accessible
        section_charts = section.get("charts", [])           # Now accessible
        
        # Add title
        if section_title:
            generator.add_heading(section_title, level=1)
        
        # Add content
        if section_content:
            # ... process content ...
        
        # New: Directly use already generated charts (no post-processing needed)
        for chart in section_charts:
            chart_path = chart.get("absolute_path") or chart.get("path")
            if chart_path and Path(chart_path).exists():
                generator.add_image(Path(chart_path))
                logger.info(f"Added chart: {chart.get('title', '')} -> {chart_path}")
        
        # Alternative: If no pre-generated charts, try smart generation
        if not section_charts and self._should_generate_charts(section_title):
            chart_paths = generator.add_smart_chart(
                section_title=section_title,
                content=section_content,
                data_points=section_data_points,  # Pass structured data
                max_charts=2
            )
```

---

## 6. Modification List

### 6.1 New Files

| File Path | Description |
|-----------|-------------|
| `src/skills/chart_generation.py` | Chart generation Skill implementation |

### 6.2 Modified Files

| File Path | Modification |
|-----------|--------------|
| `src/core/decomposition/strategies.py` | Add `chart_generation` to `ASPECT_SKILL_MAP` |
| `src/core/orchestrator/aggregation/result_aggregator.py` | Add `data_points` and `charts` mapping logic |
| `src/agents/fixed_agents/document_generation_agent.py` | Use pre-generated charts, improve fallback logic |
| `src/skills/__init__.py` | Register `ChartGenerationSkill` |
| `src/skills/registry.py` | Add `chart_generation` factory function |

### 6.3 Configuration Changes

| Configuration File | Changes |
|--------------------|---------|
| `config/agents.yaml` | Add `chart_generation` capability configuration |

---

## 7. Test Plan

### 7.1 Unit Tests

```python
# tests/unit/skills/test_chart_generation_skill.py

class TestChartGenerationSkill:
    def test_analyze_share_data(self):
        """Test market share data recognition"""
        pass
    
    def test_analyze_time_series(self):
        """Test time series data recognition"""
        pass
    
    def test_generate_pie_chart(self):
        """Test pie chart generation"""
        pass
    
    def test_generate_line_chart(self):
        """Test line chart generation"""
        pass
```

### 7.2 Integration Tests

```python
# tests/integration/test_chart_generation_flow.py

class TestChartGenerationFlow:
    def test_data_points_to_charts(self):
        """Test the complete flow from data_points to charts"""
        pass
    
    def test_charts_in_report(self):
        """Test chart embedding in report"""
        pass
```

### 7.3 Acceptance Criteria

| Test Scenario | Expected Result |
|---------------|-----------------|
| Market size section | Generate bar/line chart, data accurate |
| Market share section | Generate pie chart, percentages correct |
| Competitive landscape section | Generate horizontal bar chart, rankings correct |
| No data section | No chart generated, no errors |
| Chart paths | Both relative and absolute paths correct |

---

## Appendix

### A. Existing Code References

- Chart generator: `src/services/chart_generator.py`
- Smart chart generator: `src/services/smart_chart_generator.py`
- Data analysis Skill: `src/skills/analysis/data_analysis.py`
- Skill base class: `src/skills/base.py`

### B. Related Documents

- System architecture: `docs/KNOWLEDGE_BASE/02_ARCHITECTURE/CORE_ARCHITECTURE.md`
- Agent design: `docs/AGENT_ARCHITECTURE.md`
- Skill system: `docs/SKILL_SYSTEM.md`

### C. Revision History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-04-30 | Initial design proposal |
