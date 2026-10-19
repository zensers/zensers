<div align="center">

<img src="Logo.png" alt="Zensers" width="120" />

# Zensers

**AI-Powered Automated Industry Research Platform**

<br>

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![Version](https://img.shields.io/badge/version-3.6.0-blue.svg)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)]()

<br>

> Multi-agent collaboration that transforms research questions into professional reports — where every data point is cross-validated.

[中文](README.md) · Quick Start · [Documentation](docs/) · [Roadmap](docs/ROADMAP.md)

</div>

---

## Why Zensers?

Traditional industry research relies on analysts spending weeks on manual work: gathering data, cross-validating sources, writing reports. Zensers automates this entire workflow — not as a simple LLM wrapper, but as a coordinated team of specialized agents that handles everything from requirement parsing to quality calibration, autonomously.

**Core Value:**

| | |
|---|---|
| **10x Efficiency** | Weeks of research compressed into hours — from question to polished report in one flow |
| **Trusted Data** | Multi-source cross-validation + source whitelists + fact tracing — prefer uncertainty over misinformation |
| **Professional Output** | McKinsey-style formatting, 12 chart types, DOCX/PPTX/PDF/Markdown export |
| **Continuous Evolution** | Dual-track learning system (Wisdom + Knowledge) — every research task makes the system smarter |

---

## Key Capabilities

### Multi-Agent Collaboration System

Zensers orchestrates a team of specialized agents, each responsible for a critical stage of the research pipeline:

```
Requirement Parsing → Smart Clarification → Intent Analysis → Task Decomposition → Parallel Execution → Result Aggregation → Quality Calibration → Document Generation
```

| Agent | Responsibility |
|-------|---------------|
| RequirementAnalysisAgent | Industry identification, dimensional analysis, depth assessment, skill recommendation |
| RequirementParserAgent | Requirement parsing, intent recognition, parameter extraction |
| DataCollectionAgent | Multi-source search, data cleaning, API calls, file parsing |
| CrossSynthesisAgent | Cross-domain synthesis, contradiction detection, logical integration |
| ReportGenerationAgent | Content integration, structural organization, style unification, summary generation |
| QualityCheckAgent | Data accuracy, content completeness, logical coherence, format standards |
| ResultCalibrationAgent | Result calibration, data repair, quality convergence |
| DocumentGenerationAgent | Professional multi-format output (Word/PPT/PDF/HTML) |
| LayoutDesignAgent | Report layout design and style composition |
| ChartPlannerAgent | Report content analysis, proactive data fetching, 12 chart type planning & generation |
| DataRepairAgent | Data defect detection and repair |
| GlobalReviewAgent | Global report review and consistency check |
| SurveyAnalysisAgent | Survey data analysis and visualization |

### Seven-Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 7: Application Layer — CLI / Web API / Desktop App     │
├──────────────────────────────────────────────────────────────┤
│ Layer 6: Orchestration Layer — ResearchOrchestrator / Factory │
├──────────────────────────────────────────────────────────────┤
│ Layer 5: Agent Layer — Fixed / Dynamic Agents / Sessions     │
├──────────────────────────────────────────────────────────────┤
│ Layer 4: Capability Layer — Skills / MCP Tools / Converters  │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Layer — CoreMemory / Session / KnowledgeBank │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: Communication Layer — MessageBus / SharedMemory     │
├──────────────────────────────────────────────────────────────┤
│ Layer 1: Storage Layer — TaskStorage / WAL / ResultStore     │
├──────────────────────────────────────────────────────────────┤
│ Layer 0: Constraint Layer — SourceWhitelist / CrossValidator │
└──────────────────────────────────────────────────────────────┘
```

### Self-Describing Skill System

Zensers uses a **self-describing skill architecture** where each skill declares its capabilities via a `SKILL.md` manifest file — no hard-coded registration required:

- **SKILL.md Manifest** — YAML frontmatter defines capabilities, action_rules, priority, aliases, data_types; Markdown section provides execution instructions
- **Skill Discovery Engine** — `SkillDiscovery.discover_all()` auto-scans `src/skills/` directory, parses SKILL.md, builds registries
- **Three-Dimension Registries** — `SkillRegistries` auto-builds priority_map, alias_map, structured_data_capabilities, data_source_skill_map, category_to_skills
- **Semantic Routing** — `infer_actions()` infers which actions to execute based on user intent (A-share/HK/US + quote/kline/hot)
- **Zero Hard-Code Extension** — Adding a new skill requires only: create directory + SKILL.md + skill.py; the system auto-discovers and registers it

```
src/skills/xueqiu/
├── SKILL.md          # Self-describing manifest (YAML + Markdown)
│   ├── name: xueqiu
│   ├── capabilities: [quote, kline, hot_stocks, search_and_quote, ...]
│   ├── action_rules: [{intent: "A-share+quote", actions: [quote, kline]}]
│   ├── priority: structured_db
│   └── aliases: [xueqiu_stock, stock_quote]
└── skill.py          # Skill entry point → reuses analysis/xueqiu_skill.py
```

### Data Trust Assurance

Zensers' constraint layer ensures research quality rather than blindly trusting LLM output:

- **Source Whitelist** — Government sites, statistical bureaus, and SEC filings are Tier 1 trusted sources; anonymous forums and unverified social media are flagged as untrusted
- **Multi-Source Cross-Validation** — Key conclusions require at least 2 independent sources, with 10% tolerance for numerical consistency checks
- **Fact Tracing** — Every data point is traceable to its original source, with source credibility scoring
- **Epistemic Defense** — L1-L5 five-tier contradiction detection, escalating from format checks to LLM semantic analysis
- **Quality Convergence** — Multi-round calibration loops that automatically repair data defects until quality thresholds are met

### Intelligent Routing & Dynamic Orchestration

- **Semantic Intent Analysis** — Automatically identifies research type (industry/company/competitor/policy/academic) and matches optimal framework
- **Task Structure Analysis** — Intelligently decomposes section dependencies, identifying core and supporting sections
- **Dynamic Phase Orchestration** — Generates execution plans based on task complexity, supporting mixed parallel/sequential scheduling
- **Content Lock Mechanism** — Inter-section dependency constraints ensuring downstream sections only begin after upstream completion

### Professional Multi-Format Output

| Format | Features |
|--------|----------|
| DOCX | Title styles, paragraph formatting, table styles, chart insertion, headers/footers, TOC generation |
| PPTX | Slide layouts, title styles, content layouts, chart insertion, animations |
| PDF | Page layout, font embedding, chart rendering |
| HTML | Responsive layout, stylesheets, chart embedding |
| Markdown | Structured text, chart descriptions |

Supports 12 professional chart types: Bar, Horizontal Bar, Bar+Line Combo, Pie, Line, Radar, Scatter, Bubble, Waterfall, Quadrant, Grouped Bar, Multi-entity Radar

### Research Frameworks

Built-in 6 specialized research frameworks, each with independent search strategies, analysis depth, and content requirements:

| Framework | Use Case | Search Depth | Analysis Depth |
|-----------|----------|-------------|----------------|
| Industry Research | Market size, competitive landscape, trend forecasting | 100 searches | Ultra-deep |
| Company Research | Listed company investment value analysis | 150 searches | Ultra-deep |
| Competitor Analysis | Product/strategy/strengths & weaknesses comparison | 100 searches | Ultra-deep |
| Policy Brief | Policy impact interpretation & response strategies | 80 searches | Ultra-deep |
| Market Brief | Quick market overview | 30 searches | Deep |
| Academic Research | Papers & literature reviews | 200 searches | Ultra-deep |

### Bilingual & Multilingual Support

- Full Chinese-English mixed-language report support
- Automatic language detection (Chinese/English/Japanese/Korean)
- Bilingual research framework parameter configuration
- Industry template keyword mapping in Chinese and English

---

## Use Cases

- **Industry Analysis** — Deep research on new energy, semiconductors, healthcare, etc.
- **Company Research** — Financial modeling and valuation analysis for listed companies
- **Competitor Analysis** — Product comparison, strategy differences, SWOT analysis
- **Policy Interpretation** — Policy impact assessment and response strategies
- **Academic Literature Review** — Literature reviews and empirical analysis
- **Investment Decisions** — Market intelligence and investment recommendations

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- OpenAI / DeepSeek API Key

### Installation

```bash
# Clone the repository
git clone https://github.com/zensers/zensers.git
cd zensers

# Install backend dependencies
pip install -r requirements.txt

# Configure API Key
cp config/settings.example.yaml config/settings.yaml
# Edit settings.yaml with your LLM API Key

# Install frontend dependencies
cd web && npm install && cd ..
```

### Launch

```bash
# Option 1: Desktop application (one-click start, recommended)
python desktop_app.py

# Option 2: Development mode
uvicorn src.api.main:app --reload

# Option 3: Docker
docker compose up -d

# Option 4: Production deployment
bash start.prod.sh
```

> **Desktop App Features**: Independent watchdog process guard — automatically cleans up backend/frontend child processes even when the window is force-closed, with no zombie processes left behind.

### Usage

```python
# Programmatic API
from src.core.orchestrator.orchestrator import ResearchOrchestrator

orchestrator = ResearchOrchestrator()
result = await orchestrator.research("Analyze China's NEV market", interaction_mode=True)
```

Or via the web interface: visit `http://localhost:3000`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · FastAPI · asyncio |
| LLM | OpenAI · DeepSeek · Local models |
| Search | DuckDuckGo · Baidu · Google · Bing · Tavily |
| Data Sources | AKShare · Tushare · World Bank · National Bureau of Statistics |
| Frontend | Next.js 14 · Tailwind CSS · TypeScript |
| Documents | python-docx · python-pptx · reportlab · markdown |
| Charts | matplotlib · seaborn · plotly |
| Storage | SQLite · PostgreSQL · Redis · WAL |
| Protocol | MCP (Model Context Protocol) |
| Testing | pytest · 6,300+ test cases |

---

## Project Scale

| Metric | Value |
|--------|-------|
| Source files | 430+ |
| Lines of code | ~160,000 |
| Test files | 380+ |
| Test cases | 6,300+ |
| Agents | 13+ |
| Research frameworks | 6 |
| Chart types | 12 |
| Output formats | 5 |

---

## Project Structure

```
zensers/
├── src/                        # Core source code
│   ├── agents/                 # Agent implementations
│   │   └── fixed_agents/       # Fixed agent team
│   ├── api/                    # FastAPI interface layer
│   ├── cli/                    # Command-line tools
│   ├── config/                 # Configuration management
│   ├── content/                # Content orchestration
│   ├── converters/             # Document format converters
│   ├── core/                   # Core framework
│   │   ├── adjustment/         # Report revision system
│   │   ├── agents/             # Agent core (factory/session/lifecycle)
│   │   ├── analysis/           # Analysis phase orchestration
│   │   ├── coordination/       # Task coordination
│   │   ├── decomposition/      # Task decomposition strategies
│   │   ├── dialogue/           # Dialogue state machine
│   │   ├── harness/            # Constraint layer (whitelist/cross-validation)
│   │   ├── mcp/                # MCP protocol support
│   │   ├── memory/             # Memory system (core/session/knowledge)
│   │   ├── orchestrator/       # Orchestrator (scheduling/aggregation/output)
│   │   ├── preview/            # Preview generation
│   │   ├── quality/            # Quality checks (3-stage validation)
│   │   ├── recovery/           # Fault recovery
│   │   ├── search/             # Search deduplication & domain inference
│   │   ├── storage/            # Storage engine
│   │   └── workflow/           # Workflow engine
│   ├── methodologies/          # Research methodology frameworks
│   ├── services/               # Chart planning, chart generation & data extraction
│   ├── skills/                 # Self-describing skill plugin system (SKILL.md manifest-driven)
│   │   ├── discovery.py        # Skill discovery engine (ActionRule/Manifest/Registries)
│   │   ├── registry.py         # Skill registry (capability/priority/category queries)
│   │   ├── base.py             # Skill base class (format_data/infer_actions/resolve_identifier)
│   │   ├── xueqiu/             # Xueqiu data skill (A/HK/US stock real-time quotes)
│   │   │   ├── SKILL.md        # Self-describing manifest (YAML frontmatter + instructions)
│   │   │   └── skill.py        # Skill entry point
│   │   ├── analysis/           # Data analysis skills
│   │   ├── search_skill.py     # Search skill
│   │   └── ...                 # More skills
│   └── survey/                 # Survey system
├── web/                        # Next.js frontend
├── config/                     # YAML configuration files
├── docs/                       # Project documentation
├── tests/                      # Test suite
├── scripts/                    # Utility scripts
└── docker-compose.yml          # Docker orchestration
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">
<sub>Making Market Research Smarter · 让行业研究更智能</sub>
</div>
