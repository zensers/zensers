# Zensers Documentation Center

> **Streamlined Knowledge Base** - 33 Core Documents

---

## Quick Start

| Role | Recommended Document |
|------|---------------------|
| Newcomer | [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) |
| Architect | [ORCHESTRATOR_REDESIGN.md](./KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md) |
| Developer | [AGENT_SESSION_MANAGEMENT.md](./AGENT_SESSION_MANAGEMENT.md) |
| User | [SYSTEM_USAGE_GUIDE.md](./SYSTEM_USAGE_GUIDE.md) |

---

## Document Structure

```
docs/
├── Core Documents (root, 9 files)
│   ├── DEVELOPMENT_PLAN.md          # Development plan (main)
│   ├── ARCHITECTURE_DESIGN.md       # Architecture overview
│   ├── AGENT_ARCHITECTURE.md        # Agent architecture
│   ├── AGENT_SESSION_MANAGEMENT.md  # Session management
│   ├── SYSTEM_USAGE_GUIDE.md        # System usage guide
│   ├── UNIFIED_DOCUMENT_GENERATION_AGENT_DESIGN.md
│   ├── ROADMAP.md                   # Roadmap
│   ├── CHANGELOG.md                 # Changelog
│   └── README.md                    # This document
│
├── KNOWLEDGE_BASE/ (18 files)
│   ├── 02_ARCHITECTURE/ (6)         # Architecture design
│   ├── 03_QUALITY/ (4)              # Quality assurance
│   ├── 04_SECURITY/ (2)             # Security
│   ├── 05_OPERATIONS/ (5)           # Operations
│   └── 07_AUDIT/ (2)                # Audit
│
├── NAVIGATION/ (5)                  # Navigation system
├── STATUS/ (7)                      # Project status reports
│
└── _archive/                        # Archive (39 files)
```

---

## Core Design Documents

| Document | Purpose |
|----------|---------|
| [ORCHESTRATOR_REDESIGN.md](./KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md) | Master six-layer architecture design |
| [AGENT_COORDINATION_DESIGN.md](./KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_COORDINATION_DESIGN.md) | Agent coordination mechanism |
| [CORE_ARCHITECTURE.md](./KNOWLEDGE_BASE/02_ARCHITECTURE/CORE_ARCHITECTURE.md) | Seven-layer architecture overview |
| [UNIFIED_DOCUMENT_GENERATION_AGENT_DESIGN.md](./UNIFIED_DOCUMENT_GENERATION_AGENT_DESIGN.md) | Document generation Agent |

---

## Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0-4 | Complete | Constraint layer, session management, CoreMemory, production ready |
| Phase 5 | 25% | MCP support framework |
| Phase 6 | Complete | Unified document generation Agent |
| Phase 8 | Complete | Preview revision workflow |
| Master Refactoring | Complete | Six-layer architecture, streamlined to ~430 lines |
| **Integration Fixes** | Complete | Survey data flow, chart generation, quality check |
| **CLI Integration** | Complete | survey command group (8 subcommands) |
| **Statistics Engine** | Complete | t-test, ANOVA, chi-square, non-parametric tests |

---

## Recent Updates (2026-05-04)

### Systematic Integration Fixes

- **Survey data flow**: Fixed complete data flow from collection to report generation
- **Chart generation**: Integrated ChartGenerator into SurveyAnalysisAgent
- **Template engine**: Fixed nested loop and conditional statement rendering
- **Quality check**: Integrated QualityCheckAgent into main flow
- **Statistical analysis**: Added standard deviation, confidence intervals, correlation analysis
- **CLI Integration**: Added `survey` command group (8 subcommands)
- **Statistical inference**: t-test, ANOVA, chi-square, non-parametric tests (zero dependencies)
- **Multi-country population data**: US/UK/DE/JP/FR

See [CHANGELOG.md](./CHANGELOG.md)

---

## Documentation Guidelines

- **Root directory**: Only core documents (development plan, architecture design)
- **KNOWLEDGE_BASE**: Detailed designs organized by category
- **STATUS**: Project status reports and analysis documents
- **_archive**: Outdated/duplicate documents

---

> Updated: 2026-04-19 | Document count: 33 (streamlined from 72)
