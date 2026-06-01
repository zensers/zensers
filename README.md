# Zensers

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

**Open-source automated market research system powered by multi-agent collaboration**

基于多Agent协作的开源自动化市场研究系统

---

## Key Features / 核心特性

- 🤖 **Multi-Agent Collaboration** — Master agent dynamically spawns specialized agents for complex research tasks / 主控Agent动态生成专业Agent协同完成复杂研究
- 📊 **Professional Report Generation** — McKinsey-style international publication quality reports / 支持McKinsey风格的国际出版物级别报告输出
- 📈 **Intelligent Chart Generation** — 10 professional chart types with automatic data visualization / 10种专业图表类型，自动数据可视化
- 🔌 **Open Source Ecosystem** — Integrates LangChain, LlamaIndex and other open-source skills / 集成LangChain、LlamaIndex等开源Skill生态
- 🧠 **Model Agnostic** — Universal OpenAI-compatible interface supporting GPT, Claude, local models / 通用OpenAI接口，支持GPT、Claude、本地模型等
- 💾 **Persistent State** — Task state persistence with crash recovery and resume support / 任务状态持久存储，支持崩溃恢复和断点续传
- 🔧 **Dynamic Extension** — Auto-discovery and dynamic installation of skills / Skill自动发现和动态安装，功能无限扩展
- 🌐 **Modern Frontend** — Next.js 14 with Tailwind CSS for responsive UI / 基于Next.js 14和Tailwind CSS的现代化前端界面

---

## Architecture / 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                          │
│                     用户交互层 (Next.js)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   Understanding Layer                        │
│                     需求理解层                                │
│              (Requirement Analysis & Parsing)                │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                  Orchestration Layer                         │
│                     主控调度层                                │
│         (Master Agent, Task Planning, Agent Spawning)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     Agent Layer                              │
│                    Agent执行层                               │
│    (Specialized Agents: Research, Analysis, Generation)      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     Skill Layer                              │
│                    Skill能力层                               │
│   (Search, Scraping, Charts, Document Generation, etc.)      │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start / 快速开始

### Prerequisites / 前置要求

- Python 3.10 or higher
- Node.js 18 or higher
- OpenAI-compatible API key

### Installation / 安装

```bash
# Clone the repository
git clone https://github.com/sunchaokun/zensers.git
cd zensers

# Install backend dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Configuration / 配置

```bash
# Copy the example configuration
cp config/settings.example.yaml config/settings.yaml

# Edit config/settings.yaml and add your API keys
# 编辑 config/settings.yaml 并填入你的API密钥
```

### Run / 运行

```bash
# Start backend server
uvicorn src.main:app --reload

# In a new terminal, start frontend
cd frontend
npm run dev
```

Access the application at `http://localhost:3000`

访问 `http://localhost:3000` 使用应用

---

## Documentation / 文档

- [API Reference](docs/API.md) — REST API documentation
- [Architecture](docs/ARCHITECTURE.md) — System architecture design
- [Agent Design](docs/AGENT_DESIGN.md) — Agent states and lifecycle
- [Skill System](docs/SKILL_SYSTEM.md) — Skill management and integration
- [Changelog](docs/CHANGELOG.md) — Version history
- [Roadmap](docs/ROADMAP.md) — Development roadmap

---

## Tech Stack / 技术栈

| Layer | Technology | Description |
|-------|------------|-------------|
| **Backend** | Python 3.10+ | Core development language |
| **Framework** | FastAPI | High-performance async web framework |
| **LLM** | LangChain + OpenAI API | Multi-model support with unified interface |
| **Frontend** | Next.js 14 | React framework with App Router |
| **Styling** | Tailwind CSS | Utility-first CSS framework |
| **Validation** | Pydantic | Data validation and settings management |
| **Async** | asyncio | Concurrent task processing |
| **Testing** | pytest | Unit and integration testing |

---

## Contributing / 贡献

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

欢迎贡献代码！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南。

---

## License / 许可证

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

本项目采用 MIT 许可证 — 详见 [LICENSE](LICENSE) 文件。

---

## Acknowledgments / 致谢

This project builds upon the following open-source projects:

- [LangChain](https://github.com/langchain-ai/langchain) — LLM application framework
- [LlamaIndex](https://github.com/run-llama/llama_index) — Data framework for LLMs
- [FastAPI](https://github.com/tiangolo/fastapi) — Modern web framework for Python
- [Next.js](https://github.com/vercel/next.js) — React framework for production

See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for full license details.

---

*Zensers — Making market research smarter and more efficient*  
*Zensers — 让市场研究更智能、更高效*
