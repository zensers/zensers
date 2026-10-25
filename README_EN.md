<div align="center">

# Zensers

**AI-Powered Automated Industry Research Platform**

*From a single prompt to a signature-verified professional research report — 2 hours, fully autonomous*

<br>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)]()
[![Tests 6300+](https://img.shields.io/badge/tests-6300%2B-brightgreen.svg)]()

[中文](README.md) · Live Cases · Quick Start

</div>

---

## 🎬 Live Case Gallery

**All 6 reports below were generated 100% end-to-end by the system** — not marketing mockups, but real production runs.
Every report ships with a **delivery signature**, a **methodology & definitions preamble**, numbered **Exhibits**, and data points traceable to 30+ named institutions (IDC, Stanford HAI, Gartner, Fortune Business Insights, Xinhua…).

| # | Case | Sections | Data Points | Exhibits | Signature | Read Online |
|---|------|:---:|:---:|:---:|------|:---:|
| 1 | **Humanoid Robot Industry Report** | 5 | 70 | 5 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/humanoid-robot.html) |
| 2 | **AI Industry Report** | 5 | 73 | 5 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/ai-industry.html) |
| 3 | **Semiconductor Industry Report** | 6 | 51 | 6 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/semiconductor.html) |
| 4 | **Solid-State Battery Industry Report** | 5 | 78 | 5 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/solid-state-battery.html) |
| 5 | **EV Market Research** (Express) | 2 | 66 | 2 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/nev-market.html) |
| 6 | **AI Industry In-Depth Report** (7 sections) | 7 | 30 | 13 | `formal / degraded` | [📖 Read](https://zensers.github.io/zensers/samples/ai-industry-deep.html) |

> 💡 Every report opens with a consolidated "Methodology, Definitions & Assumptions" section; every key figure is traceable;
> when evidence cannot be fully verified, the delivery signature is downgraded honestly (degraded) — **honest degradation over false confidence**.

---

## ⚡ How It Works

```
Conversational Framework → Multi-Source Retrieval → Section Writing/Review/Rewrite
→ Defense-Loop Repair → Quality Convergence → Delivery Signing → Multi-Format Publishing
```

| Stage | What Happens |
|-------|--------------|
| **Requirement Alignment** | Conversational clarification; LLM derives the research framework; one click to execute |
| **Data Collection** | Parallel multi-engine search + structured data skills (A-share financials/quotes) + World Bank/NBS |
| **Deep Writing** | Per-section Writer→Reviewer→Rewriter loops; every figure bound to a source and epistemic level |
| **Defense Audit** | L1-L5 deterministic audit: evidence ownership, scope, provenance, conflict detection, auto-repair rounds |
| **Delivery Signing** | A deterministic signer grades the output (formal / diagnostic / dossier); garbage never ships |

---

## 🏆 What Makes It Different

| | |
|---|---|
| **Signed, Honest Delivery** | Every report is graded by a deterministic signer; unverifiable content ships as a clearly-labeled diagnostic edition, never disguised as final |
| **Every Number Traceable** | Data points carry source URLs, evidence excerpts, geo/period scope, and epistemic levels (factual / inferential / speculative) |
| **Caliber Discipline** | Cross-caliber data is never merged; statistical boundaries are declared upfront and enforced throughout |
| **Decision-Oriented** | Beyond listing data — comparisons, projections, scenario analysis, and role-specific recommendations |

---

## 🧰 Capability Highlights

| Capability | Details |
|------|------|
| Multi-Agent Collaboration | 13+ specialized agents: parsing, collection, synthesis, QA calibration, publishing |
| Professional Charts | 12 chart types, LLM-planned and numerically validated before rendering |
| Multi-Format Delivery | DOCX / PPTX / PDF / HTML / Markdown |
| Structured Data | A-share financial statements, key metrics, price history (multi-source fallback) |
| Dual-Track Learning | Wisdom + Knowledge systems turn every research run into organizational memory |
| Production Engineering | 6,300+ tests, failure audit trail, checkpoint resume, multi-LLM failover |

---

## 🎯 Use Cases

**Industry Analysis** · **Company Research** · **Competitive Analysis** · **Policy Interpretation** · **Investment Decisions** · **Academic Reviews**

---

## 🚀 Quick Start

### Requirements

- Python 3.10+ · Node.js 18+ (frontend) · LLM API Key (OpenAI / DeepSeek) · Tavily API Key (recommended, primary web search)

### Install

```bash
git clone https://github.com/zensers/zensers.git
cd zensers

# Backend
pip install -r requirements.txt
cp config/settings.example.yaml config/settings.yaml   # add your LLM API key
cp .env.example .env                                   # add your Tavily API key (see below)

# Frontend
cd web && npm install && cd ..
```

> 🔑 **Web Search Setup (Recommended)**: The primary web-search skill `lc_tavily_search` requires a Tavily API key.
> Sign up for free at [app.tavily.com](https://app.tavily.com) (1,000 credits/month, no credit card),
> then add `TAVILY_API_KEY=tvly-your-key` to `.env`.
> **Without the key, the skill is silently disabled** and the system falls back to built-in multi-engine search, reducing report quality.
> See the [Usage Guide §5.3](docs/SYSTEM_USAGE_GUIDE.md) for detailed steps.

### Run

```bash
python desktop_app.py                # Desktop app (one-click, recommended)
uvicorn src.api.main:app --reload    # Dev mode
docker compose up -d                 # Docker
```

Open `http://localhost:3000` and type your research request.

---

## 📄 License

[MIT](LICENSE)
