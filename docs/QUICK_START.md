# Zensers Quick Start Guide

> Get started with the automated market research report generation system in 5 minutes

---

## Part 1: Installation and Configuration

### 1.1 Install Dependencies

```bash
# Enter project directory
cd E:\market_report_systerm

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies (if not already installed)
pip install -r requirements.txt
```

### 1.2 Configure API Keys

Edit the `.env` file and fill in your API keys:

```env
# OpenAI compatible interface (required)
OPENAI_API_KEY=sk-xxxxx
OPENAI_API_BASE=https://api.openai.com/v1

# Search service (optional)
TAVILY_API_KEY=tvly-xxxxx
```

---

## Part 2: Command Line Usage

### 2.1 Submit Research Task

```bash
# Basic usage
python -m src.cli.main research "Analyze China's new energy vehicle market development trends"

# Specify output format
python -m src.cli.main research "New energy vehicle market analysis" --format docx --output report.docx

# Show detailed logs
python -m src.cli.main research "Medical AI market research" --verbose
```

### 2.2 Check Task Status

```bash
# List all active tasks
python -m src.cli.main status

# Check specific task status
python -m src.cli.main status task_xxx

# Continuously monitor task
python -m src.cli.main status task_xxx --watch
```

### 2.3 Download Report

```bash
# Download Markdown format
python -m src.cli.main download task_xxx --output report.md --format markdown

# Download Word format
python -m src.cli.main download task_xxx --output report.docx --format docx
```

### 2.4 Other Commands

```bash
# View version
python -m src.cli.main version

# View configuration
python -m src.cli.main config --show
```

---

## Part 3: Python Code Usage

### 3.1 Minimal Example

```python
import asyncio
from src.core.orchestrator.orchestrator import ResearchOrchestrator

async def main():
    # Create orchestrator
    orchestrator = ResearchOrchestrator()
    
    # Execute research
    result = await orchestrator.process_request(
        "Analyze China's new energy vehicle market development trends, including market size, competitive landscape, policy impact"
    )
    
    # View results
    if result.get("success"):
        print(f"Report generated: {result.get('output_path')}")
        print(f"Quality score: {result.get('quality_score')}")
    else:
        print(f"Execution failed: {result.get('error')}")

asyncio.run(main())
```

### 3.2 Structured Requirements

```python
result = await orchestrator.process_request({
    "topic": "Medical AI Market Research",
    "aspects": ["Market Size", "Competitive Landscape", "Technology Trends", "Investment Opportunities"],
    "region": "China",
    "time_range": "2023-2025",
    "output_format": "docx"
})
```

### 3.3 Resume Interrupted Task

```python
# Resume previously interrupted task
result = await orchestrator.resume("task_xxx")
```

---

## Part 4: Output Location

All output is uniformly stored in the `output/reports/{task_id}/` directory:

```
output/reports/task_xxx/
├── report.docx          # Research report (Word format)
├── report.md            # Research report (Markdown format)
├── charts/              # Chart files
│   ├── chart_001.png    # Bar chart
│   ├── chart_002.png    # Donut chart
│   └── ...
└── survey/              # Survey related (if any)
    ├── questionnaire.json
    └── analysis.json
```

---

## Part 5: Report Templates

The system supports multiple report templates:

| Template | Purpose | Command |
|----------|---------|---------|
| industry_report | Industry research report | Default template |
| company_research | Company research report | `--template company_research` |
| competitor_analysis | Competitive analysis report | `--template competitor_analysis` |
| investment_memo | Investment memorandum | `--template investment_memo` |

---

## Part 6: Frequently Asked Questions

### Q1: API Key configuration error?

Make sure `OPENAI_API_KEY` in the `.env` file is correct and the API service is accessible.

### Q2: Report generation failed?

Check the log file `logs/Zensers.log` for specific error information.

### Q3: How to use local model?

Modify `OPENAI_API_BASE` in `.env` to point to your local model service:

```env
OPENAI_API_BASE=http://localhost:8000/v1
```

### Q4: Where is the output directory?

Default is under `output/reports/`, can be modified in `config/system.yaml`:

```yaml
system:
  paths:
    report_output_dir: "output/reports"
```

---

## Part 7: Next Steps

- View detailed documentation: [SYSTEM_USAGE_GUIDE.md](./SYSTEM_USAGE_GUIDE.md)
- Learn about system architecture: [ARCHITECTURE_DESIGN.md](./ARCHITECTURE_DESIGN.md)
- View changelog: [CHANGELOG.md](./CHANGELOG.md)

---

> Bug reports: Check logs or submit an Issue
