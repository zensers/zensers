<div align="center">

# Zensers

**AI-Powered Market Research Platform**

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-439%20passing-brightgreen.svg)]()
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)]()

*Turn research questions into professional reports — automatically.*

</div>

---

## Why Zensers?

LLMs generate great text, but they **hallucinate numbers**. Research reports need accuracy — every data point must be traceable and consistent.

Zensers is built different: a multi-agent system that doesn't just write reports — it **audits every number** before it reaches the page.

---

## Features

- **Multi-Agent Orchestration** — Dynamic agent teams (research, analysis, synthesis, calibration) collaborate on complex reports
- **Data Consistency Pipeline** — Automatic cross-validation of every metric against authoritative sources
- **Multi-Engine Search** — DuckDuckGo, Baidu, Google, and Bing integration with intelligent result ranking
- **Smart Content Extraction** — Adaptive web scraping that handles JS sites, PDFs, and anti-bot protection
- **Professional Report Output** — DOCX, PPTX, PDF, and Markdown with publication-grade formatting
- **Bilingual Support** — Full Chinese-English mixed-language report capabilities

---

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
cp config/settings.example.yaml config/settings.yaml

# Run
uvicorn src.main:app --reload
```

---

## Tech Stack

**Backend**: Python + FastAPI + asyncio  
**LLM**: OpenAI-compatible (GPT-4, Claude, local models)  
**Search**: DuckDuckGo, Baidu, Google, Bing  
**Frontend**: Next.js 14 + Tailwind CSS  
**Testing**: pytest (439 tests)

---

## License

MIT

---

<div align="center">
<sub>Making market research smarter · 让市场研究更智能</sub>
</div>
