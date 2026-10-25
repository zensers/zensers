<div align="center">

# Zensers

**AI 驱动的自动化行业研究平台**

*从一句需求，到一份带交付签名的专业研究报告 —— 2 小时，全程无人工*

<br>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)]()
[![Tests 6300+](https://img.shields.io/badge/tests-6300%2B-brightgreen.svg)]()

[English](README_EN.md) · 在线案例 · 快速开始

</div>

---

## 🎬 真实案例画廊

**以下 6 份报告 100% 由系统端到端自动生成**——不是营销样稿，是真实运行产物。
每份报告都附带**交付签名**、**口径与方法前置节**、**编号 Exhibit 图表**，以及可溯源至 30+ 实名机构（IDC、Stanford HAI、Gartner、Fortune Business Insights、新华网…）的数据点。

| # | 案例 | 章节 | 数据点 | Exhibit | 交付签名 | 在线阅读 |
|---|------|:---:|:---:|:---:|------|:---:|
| 1 | **人形机器人行业分析报告** | 5 | 70 | 5 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/humanoid-robot.html) |
| 2 | **人工智能行业分析报告** | 5 | 73 | 5 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/ai-industry.html) |
| 3 | **半导体行业分析报告** | 6 | 51 | 6 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/semiconductor.html) |
| 4 | **固态电池行业分析报告** | 5 | 78 | 5 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/solid-state-battery.html) |
| 5 | **新能源汽车市场研究**（快速版） | 2 | 66 | 2 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/nev-market.html) |
| 6 | **人工智能行业深度报告**（7 章深度版） | 7 | 30 | 13 | `formal / degraded` | [📖 阅读](https://zensers.github.io/zensers/samples/ai-industry-deep.html) |

> 💡 每份报告开头的「口径、假设与方法」集中声明统计边界；正文关键数字 100% 可溯源；
> 存在未完全核验的证据链时，交付签名会如实降级标注（degraded）——**宁可诚实降级，绝不掩饰不确定性**。

---

## ⚡ 系统如何工作

```
对话派生框架 → 多源并行检索 → 章节级写作/评审/重写 → 防御循环修复 → 质检收敛 → 交付签名定级 → 多格式排版
```

| 阶段 | 发生什么 |
|------|---------|
| **需求对齐** | 对话式澄清，LLM 派生研究框架，一键确认执行 |
| **数据采集** | 多搜索引擎并行 + 结构化数据技能（A股财务/股价）+ 世界银行/国家统计局 |
| **深度写作** | 章节级 Writer→Reviewer→Rewriter 循环，每个数字绑定来源与认知层级 |
| **防御审计** | L1-L5 五层确定性审计：证据归属/口径/溯源/冲突检测，自动修复轮 |
| **交付签名** | 确定性签名器定级（formal / diagnostic / dossier），垃圾内容永不进入交付物 |

---

## 🏆 为什么与众不同

| | |
|---|---|
| **交付签名，分级诚实** | 每份报告由确定性签名器定级；无法核验的内容以诊断版交付并显著标注，绝不冒充定稿 |
| **每个数字可溯源** | 数据点携带来源 URL、证据摘录、地理/期间口径与认知层级（事实/推理/推测） |
| **口径纪律** | 跨口径数据不合并比较；统计边界在报告开头集中声明，全文一致执行 |
| **面向决策的解读** | 不止罗列数据——对比、测算、情景推演与分角色决策建议 |

---

## 🧰 核心能力速览

| 能力 | 说明 |
|------|------|
| 多智能体协作 | 13+ 专业 Agent：需求解析/数据采集/跨域综合/质检校准/文档排版 |
| 专业图表 | 12 种图表类型，LLM 规划 + 数值校验后渲染 |
| 多格式交付 | DOCX / PPTX / PDF / HTML / Markdown |
| 结构化数据 | A股上市公司财务三表、关键指标、股价历史（多数据源兜底） |
| 双轨学习 | Wisdom + Knowledge 双系统，研究结果沉淀为组织记忆 |
| 生产级工程 | 6,300+ 测试用例、失败留痕审计、断点续跑、多 LLM 供应商容灾 |

---

## 🎯 适用场景

**行业分析** · **公司研究** · **竞品分析** · **政策解读** · **投资决策** · **学术综述**

---

## 🚀 快速开始

### 环境要求

- Python 3.10+ · Node.js 18+（前端）· LLM API Key（OpenAI / DeepSeek）· Tavily API Key（推荐，主力联网搜索）

### 安装

```bash
git clone https://github.com/zensers/zensers.git
cd zensers

# 后端
pip install -r requirements.txt
cp config/settings.example.yaml config/settings.yaml   # 填入你的 LLM API Key
cp .env.example .env                                   # 填入你的 Tavily API Key（见下方说明）

# 前端
cd web && npm install && cd ..
```

> 🔑 **联网搜索配置（推荐）**：主力搜索技能 `lc_tavily_search` 需要 Tavily API Key。
> 在 [app.tavily.com](https://app.tavily.com) 免费注册即可获取（每月 1,000 credits，无需信用卡），
> 然后在 `.env` 中加入 `TAVILY_API_KEY=tvly-你的密钥`。
> **未配置时该技能会被静默禁用**，系统自动降级到内置多引擎搜索，报告质量会受影响。
> 详细步骤见[使用手册 §5.3](docs/SYSTEM_USAGE_GUIDE.md)。

### 启动

```bash
python desktop_app.py        # 桌面应用（一键启动，推荐）
uvicorn src.api.main:app --reload   # 开发模式
docker compose up -d         # Docker
```

访问 `http://localhost:3000`，输入你的研究需求即可。

---

## 📄 License

[MIT](LICENSE)
