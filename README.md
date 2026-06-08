# Zensers

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-439%20passed-brightgreen.svg)]()

**Automated Industry Research System — 自动化产业研究系统**

> Multi-agent collaboration platform that generates professional-grade industry research reports with guaranteed data consistency.  
> 多智能体协同平台，生成具有数据一致性保障的专业级行业研究报告。

---

## Overview / 概述

Zensers is an open-source automated market research system that goes beyond simple LLM-based report generation. It features a **multi-agent orchestration engine** with a **6-stage data consistency pipeline (M0–M5)** that ensures every number in the final report is cross-validated against authoritative canonical data.

Unlike naive report generators that suffer from hallucinated numbers, Zensers treats data integrity as a first-class concern — catching and fixing inconsistencies across agents, stages, and currencies before the final report is assembled.

---

## Architecture / 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface                            │
│               Next.js 14 + Tailwind CSS / REST API               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    Orchestration Layer                            │
│     ResearchOrchestrator · Task Planner · Agent Scheduling       │
│     Intelligent Routing · Content Lock Manager · Session Mgmt    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    Multi-Agent Execution                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  Data     │  │ Analysis │  │Synthesis │  │  Calibration   │  │
│  │Collection │  │  Agents  │  │  Agents  │  │    Agent       │  │
│  │  Agents   │  │          │  │          │  │  (M5-b LLM)    │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│              M0–M5 Data Consistency Pipeline                      │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌──────┐ ┌────┐                   │
│  │ M0 │→│ M1 │→│ M2 │→│ M3 │→│ M5-a │→│ M5-b│                   │
│  │Agg.│ │Dual│ │Filt│ │Can.│ │ Gate │ │Cal. │                   │
│  │    │ │Phse│ │er  │ │Enf.│ │ Fix  │ │ LLM │                   │
│  └────┘ └────┘ └────┘ └────┘ └──────┘ └────┘                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      Skill Layer                                 │
│  Search(Baidu/DDGS/Google) · Scraper(Scrapling/PW) · Charts     │
│  PDF Generation(DOCX/PPTX) · Quality Checkers                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features / 核心特性

### 🎯 M0–M5 Data Consistency Pipeline
The core innovation — a 6-stage pipeline guaranteeing numerical accuracy:

| Stage | Function | What it does |
|-------|----------|-------------|
| **M0** | Aggregation | Maps agent_id→aggregation keys, preserves cross-phase content (DC vs Analysis) |
| **M1** | Dual-Phase | Generates DC + Analysis phases per section, manages interdependencies |
| **M2** | Aspect Filtering | Routes data to correct sections based on aspect/topic matching |
| **M3** | Canonical Enforcement | Replaces agent values with authoritative canonical data (>5% diff threshold) |
| **M5-a** | Consistency Gate | Fixes content + data_points via MetricExtractor; cross-currency conversion |
| **M5-b** | Calibration Phase | LLM-based cross-agent consistency check; generates calibration report |

### 🤖 Multi-Agent Orchestration
- **Dynamic Agent Spawning**: Master agent spawns specialized agents (DC, Analysis, Synthesis, Calibration) based on task complexity
- **Content Lock Manager**: Section-level dependency tracking prevents parallel conflicts
- **Session Persistence**: Crash recovery with checkpoint-based resume
- **Parallel Execution**: Topological scheduler for optimal batch execution

### 🔍 Search Infrastructure
- **Multi-Engine**: DuckDuckGo (DDGS), Baidu (baidu-serp-api), Google, Bing (CN/Intl)
- **Adaptive Scraping** (v3.0): Scrapling `AsyncFetcher` with anti-bot detection, Playwright for JS sites, pdfplumber for PDF reports
- **Two-Stage Enrichment**: Search → snippet → full content crawl → LLM
- **Quality Scoring**: Multi-dimensional scoring (credibility × 35% + relevance × 30% + depth × 25% + freshness × 10%)

### 📊 Professional Report Generation
- **Multi-Format Output**: DOCX, PPTX, PDF, Markdown, HTML
- **Intelligent Charts**: 10 chart types (matplotlib, plotly, seaborn)
- **McKinsey-Style Templates**: Professional publication-grade formatting
- **Bilingual Support**: Chinese + English mixed-language reports

### 🧠 Model Agnostic
- Universal OpenAI-compatible interface
- Supports GPT-4, Claude, Gemini, local models
- Automatic fallback across providers

---

## M0–M5 Pipeline in Action / 数据一致性管线工作流

```
Agent outputs → M5-a Gate (canonical fix)
     ↓
M0 Aggregation (phase-aware key mapping)
     ↓
M4 Conflict Detection (cross-agent metric comparison)
     ↓
M5-b Calibration (LLM reconciliation → Report injection)
     ↓
Final report with guaranteed data consistency
```

**Example**: Two analysis agents produce conflicting revenue figures (7200 vs 6770). The pipeline detects the discrepancy at M4, applies the authoritative canonical value (6770) at M5-a, and the calibration agent documents the fix at M5-b — the final report uses the correct value with full traceability.

---

## Quick Start / 快速开始

### Prerequisites

```bash
# Python 3.10+ and Node.js 18+
pip install -r requirements.txt
pip install "scrapling[fetchers]"   # web scraping engine
scrapling install                   # install browser dependencies
```

### Configuration

```bash
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml to add LLM API keys
```

### Run

```bash
# Backend
uvicorn src.main:app --reload

# Frontend (separate terminal)
cd frontend && npm run dev
```

Open `http://localhost:3000`

---

## Project Statistics / 项目统计

| Metric | Value |
|--------|-------|
| Commits | 28+ |
| Automated Tests | 439 |
| Test Pass Rate | 100% (core pipeline) |
| Search Engines | 5 (DuckDuckGo, Baidu, Google, Bing CN/Intl) |
| Scraping Strategies | 4 (static, JS, PDF, redirect resolution) |
| Output Formats | 6 (DOCX, PPTX, PDF, MD, HTML, JSON) |
| License | MIT |

---

## Tech Stack / 技术栈

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.10+ · asyncio |
| **API** | FastAPI · WebSocket (SSE streaming) |
| **LLM** | OpenAI API · Anthropic · LangChain |
| **Search** | DuckDuckGo · baidu-serp-api · Scrapling · Playwright · pdfplumber |
| **Documents** | python-docx · python-pptx · reportlab · markdown |
| **Charts** | matplotlib · plotly · seaborn |
| **Frontend** | Next.js 14 · Tailwind CSS |
| **Testing** | pytest · 439 tests |

---

## Documentation / 文档

- [API Reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Agent Design](docs/AGENT_DESIGN.md)
- [Skill System](docs/SKILL_SYSTEM.md)
- [Changelog](docs/CHANGELOG.md)

---

## License

MIT License — see [LICENSE](LICENSE)

---

*Zensers — Making market research smarter and more efficient · 让市场研究更智能、更高效*
