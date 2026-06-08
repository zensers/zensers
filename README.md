<div align="center">

# Zensers

**Automated Market Research Platform**

<br>

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-439%20passing-brightgreen.svg)]()
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)]()

<br>

> Generate professional research reports through multi-agent collaboration — with automatic data consistency assurance.

</div>

---

## ✦ Overview

Zensers is an open-source platform that transforms research questions into comprehensive, professionally formatted reports. Unlike simple LLM wrappers, it orchestrates a team of specialized agents that research, analyze, cross-validate, and synthesize information — producing reports where every data point is checked for consistency.

**Use cases:** Industry analysis · Company research · Financial reporting · Market intelligence · Academic literature review

---

## ✦ Key Capabilities

| | |
|---|---|
| **Multi-Agent System** | Dynamic agent teams autonomously handle research, analysis, synthesis, and quality calibration |
| **Data Pipeline** | Automatic cross-validation ensures numerical consistency across all report sections |
| **Intelligent Search** | Integrated search across DuckDuckGo, Baidu, Google, and Bing with smart result ranking |
| **Web Scraping** | Adaptive extraction that handles JavaScript-rendered sites, PDF documents, and anti-bot protection |
| **Report Generation** | Professional output in DOCX, PPTX, PDF, and Markdown with publication-grade formatting |
| **Bilingual Support** | Full support for Chinese and English mixed-language reports |

---

## ✦ Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure your LLM API key
cp config/settings.example.yaml config/settings.yaml

# Launch the server
uvicorn src.main:app --reload
```

---

## ✦ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · asyncio |
| LLM | OpenAI / DeepSeek / Local models |
| Search | DuckDuckGo · Baidu API · Google · Bing |
| Frontend | Next.js 14 · Tailwind CSS |
| Testing | pytest · 439 tests |

---

## ✦ License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">
<sub>Making market research smarter · 让市场研究更智能</sub>
</div>
