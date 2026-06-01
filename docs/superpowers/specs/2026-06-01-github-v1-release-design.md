# Zensers GitHub v1.0.0 首次发布设计文档

> 仓库地址：https://github.com/sunchaokun/zensers
> 策略：一次性完整发布（方案B），深度打磨后推送
> 目标受众：全球开发者，双语文档（英文为主，关键部分中文对照）
> 发布范围：Python 后端 + Next.js 前端（同一仓库）

---

## 1. 文件清理

### 1.1 原则

- 所有清理操作为**移动**而非删除
- 移动目标：`C:\Users\Administrator\AppData\Local\Temp\opencode\zensers-archive\`
- 按类别创建子目录，便于日后回溯

### 1.2 根目录文件清理

#### 反编译/工具脚本（移动到 `archive/decompile/`）

| 文件 | 说明 |
|------|------|
| `decompile_py313.py` | Python 3.13 反编译脚本 |
| `decompile_py313_v2.py` | 反编译脚本 v2 |
| `decompile_py313_v3.py` | 反编译脚本 v3 |
| `decompile_rebuild.py` | 反编译重建脚本 |
| `decompile_v2.py` | 反编译脚本 v2 |
| `disassemble_pyc.py` | pyc 反汇编脚本 |
| `extract_pyc.py` | pyc 提取脚本 |
| `extract_structure.py` | 结构提取脚本 |
| `zensers.py` | 根目录残留入口文件 |
| `research_api_back.py` | API 备份文件 |

#### 日志/输出文件（移动到 `archive/logs/`）

| 文件 | 说明 |
|------|------|
| `server_error.log` | 服务器错误日志 |
| `pyc_disassembly.txt` | pyc 反汇编输出 |
| `pyc_output.txt` | pyc 输出 |
| `regex_issues.txt` | 正则问题记录 |
| `test_output.txt` | 测试输出 |
| `test_v7_output.txt` | v7 测试输出 |
| `analysis.txt` | 分析输出 |

#### 审计/修复计划文档（移动到 `archive/audit-docs/`）

| 文件 | 说明 |
|------|------|
| `analysis_and_fix_plan.md` | 分析与修复计划 |
| `ANCHORED_SUMMARY.md` | 锚定摘要 |
| `AUDIT_REPORT.md` | 审计报告 |
| `AUDIT_REPORT_V2.md` | 审计报告 V2 |
| `bug-analysis-2026-05-28.md` | Bug 分析 |
| `bug-analysis-llm-config-20260531.md` | LLM 配置 Bug 分析 |
| `bugfix-record-llm-config-20260531.md` | Bug 修复记录 |
| `findings.md` | 发现记录 |
| `FIX_PLAN.md` | 修复计划 |
| `RECOVERY_STATUS.md` | 恢复状态 |
| `research_failure_analysis_20260527.md` | 研究失败分析 |
| `REVISION_LOG.md` | 修订日志 |
| `revision_plan.md` | 修订计划 |
| `task_plan.md` | 任务计划 |

#### 归档目录（移动到 `archive/_archive/`）

| 文件 | 说明 |
|------|------|
| `_archive/` | 整个归档目录 |

### 1.3 tests/ 目录清理

#### 移动到 `archive/tests-debug/`

| 文件 | 说明 |
|------|------|
| `debug_cr01*.py` (7个) | CR01 调试系列 |
| `debug_cr02.py` | CR02 调试 |
| `debug_in02*.py` (5个) | IN02 调试系列 |
| `debug_intent.py` | 意图调试 |
| `debug_llm_output.py` | LLM 输出调试 |
| `debug_locator*.py` (2个) | 定位器调试 |
| `debug_op.py` | OP 调试 |
| `debug_root.py` | 根调试 |
| `debug_tree*.py` (3个) | 树调试系列 |
| `debug_while_test.py` | While 测试调试 |
| `deep_debug_in02.py` | 深度 IN02 调试 |
| `check_api.py` | API 检查 |
| `check_fastapi.py` | FastAPI 检查 |
| `check_ids.py` | ID 检查 |
| `check_keywords.py` | 关键词检查 |
| `data_check.py` | 数据检查 |
| `diag_failure.py` | 失败诊断 |
| `list_templates.py` | 模板列表 |
| `locator_test.py` | 定位器测试 |
| `qa_verification_p0_fixes.py` | P0 修复验证 |
| `run_frontend_tests.py` | 前端测试运行 |
| `run_phase1_tests.py` | Phase1 测试运行 |
| `run_quick_test.py` | 快速测试运行 |
| `smoke_test.py` | 冒烟测试 |
| `stability_test.py` | 稳定性测试 |
| `test_frontend_results.txt` | 前端测试结果 |
| `test_results.txt` | 测试结果 |

#### 保留的测试文件

| 文件 | 说明 |
|------|------|
| `test_e2e.py` | 端到端测试 |
| `test_e2e_survey.py` | 调查端到端测试 |
| `test_chart_generator.py` | 图表生成测试 |
| `test_cn_chart_extraction.py` | 中文图表提取测试 |
| `test_contradiction_detector.py` | 矛盾检测测试 |
| `test_css_*.py` (2个) | CSS 相关测试 |
| `test_data_validation.py` | 数据验证测试 |
| `test_fixes.py` / `test_fixes_quick.py` | 修复测试 |
| `test_final_imports.py` | 最终导入测试 |
| `test_knowledge_*.py` (3个) | 知识库测试 |
| `test_md_table_conversion.py` | MD 表格转换测试 |
| `test_pause_race_condition.py` | 暂停竞态测试 |
| `test_phase*.py` (3个) | Phase 测试 |
| `test_profitability_bug_fix*.py` (2个) | 盈利 Bug 修复测试 |
| `test_quality_control.py` | 质量控制测试 |
| `test_quick_verify.py` | 快速验证测试 |
| `test_regions.py` | 区域测试 |
| `test_report_pipeline_e2e.py` | 报告管道 E2E |
| `test_revision_*.py` (4个) | 修订系统测试 |
| `test_survey_*.py` (2个) | 调查测试 |
| `test_table_extractor.py` | 表格提取测试 |
| `test_v7_fix_verification.py` | V7 修复验证 |
| `test_cancel_pause_phase1.py` | 取消暂停测试 |
| `unit/` | 单元测试目录 |
| `integration/` | 集成测试目录 |
| `e2e/` | E2E 测试目录 |
| `quality/` | 质量测试目录 |
| `mcp/` | MCP 测试目录 |
| `benchmark/` | 基准测试目录 |

### 1.4 docs/ 目录清理

#### 保留的文档

| 文件/目录 | 说明 |
|-----------|------|
| `ARCHITECTURE_DESIGN.md` | 架构设计（后续合并为 ARCHITECTURE.md） |
| `API.md` | API 文档 |
| `CHANGELOG.md` | 变更日志 |
| `ROADMAP.md` | 路线图 |
| `QUICK_START.md` | 快速开始 |
| `README.md` | 文档目录说明 |
| `AGENT_ARCHITECTURE.md` | Agent 架构（后续合并） |
| `SYSTEM_USAGE_GUIDE.md` | 系统使用指南 |
| `LEGAL_COMPLIANCE.md` | 法律合规 |
| `PROMPT_API.md` | Prompt API |
| `RESEARCH_FRAMEWORK_DRIVEN_DESIGN.md` | 研究框架设计 |
| `AGENT_SESSION_MANAGEMENT.md` | Agent 会话管理 |
| `VERSION_MANAGEMENT_AND_UPGRADE_DESIGN.md` | 版本管理设计 |
| `KNOWLEDGE_BASE/` | 知识库目录 |
| `design/` | 设计文档目录 |
| `superpowers/` | Superpowers 目录 |
| `NAVIGATION/` | 导航目录 |
| `document_templates/` → 移至 `docs/` 下 | 文档模板 |

#### 移动到 `archive/docs-temp/`（约60个）

所有 `*_PLAN.md`、`*_FIX_PLAN*.md`、`bug-analysis-*.md`、`*_AUDIT*.md`、`*_ANALYSIS*.md`、`*_REPORT*.md`、`*_REVIEW*.md`、`settings-fix-plan.md`、`html_report_analysis.md` 等临时分析/修复文档。

### 1.5 scripts/ 目录清理

#### 移动到 `archive/scripts-debug/`

| 文件 | 说明 |
|------|------|
| `debug_locator.py` | 定位器调试 |
| `fix_corruption.py` | 修复损坏 |
| `fix_indentation.py` | 修复缩进 |
| `fix_main.py` | 修复主函数 |
| `robust_fix.py` | 健壮修复 |
| `test_html_to_ppt_fix.py` | HTML-PPT 修复测试 |
| `test_html_to_word_fix.py` | HTML-Word 修复测试 |
| `test_metadata_type_fix.py` | 元数据类型修复测试 |
| `test_orchestrator.py` | 编排器测试 |
| `verify_code.py` | 代码验证 |
| `verify_orchestrator.py` | 编排器验证 |

#### 保留的脚本

| 文件 | 说明 |
|------|------|
| `cn_audit.py` | 中文审计 |
| `cn_check.py` | 中文检查 |
| `cn_to_en.py` / `cn_to_en_v2.py` | 中文转英文 |
| `translate_to_english.py` | 翻译为英文 |
| `download_sentiment_dicts.py` | 下载情感词典 |
| `find_fences.py` | 查找围栏 |
| `migrate_database.py` | 数据库迁移 |
| `migrate_registries.py` | 注册表迁移 |
| `resize_logo.py` | Logo 调整 |
| `syntax_check.py` | 语法检查 |
| `convert_wvs_to_benchmark.py` | WVS 基准转换 |
| `validate_simulation_vs_wvs.py` | 仿真验证 |
| `check_version_variants.py` | 版本检查 |

---

## 2. .gitignore 增强

在现有 `.gitignore` 基础上追加：

```gitignore
# ═══════════════════════════════════════════════════════════════════
# 知识图谱输出（本地使用，不上传）
# ═══════════════════════════════════════════════════════════════════
graphify-out/

# ═══════════════════════════════════════════════════════════════════
# 前端构建产物
# ═══════════════════════════════════════════════════════════════════
web/.next/
web/.env.local
web/node_modules/

# ═══════════════════════════════════════════════════════════════════
# Node.js
# ═══════════════════════════════════════════════════════════════════
node_modules/
package-lock.json

# ═══════════════════════════════════════════════════════════════════
# OpenCode / 开发工具配置
# ═══════════════════════════════════════════════════════════════════
opencode.json
.pytest_cache/
```

---

## 3. 文档重构

### 3.1 docs/ 目录重组

```
docs/
├── README.md                    # 文档导航（重写）
├── ARCHITECTURE.md              # 架构设计（合并自 ARCHITECTURE_DESIGN.md）
├── API.md                       # API 文档（保留）
├── QUICK_START.md               # 快速开始（保留）
├── INSTALLATION.md              # 安装指南（新建）
├── CONFIGURATION.md             # 配置说明（新建）
├── AGENT_DESIGN.md              # Agent 设计（合并自 AGENT_ARCHITECTURE.md + AGENT_SESSION_MANAGEMENT.md）
├── SKILL_SYSTEM.md              # Skill 系统（新建，从知识库整理）
├── RECORD_SYSTEM.md             # 记录系统（新建，从知识库整理）
├── LEGAL_COMPLIANCE.md          # 法律合规（保留）
├── CHANGELOG.md                 # 变更日志（保留）
├── ROADMAP.md                   # 路线图（保留）
├── PROMPT_API.md                # Prompt API（保留）
├── KNOWLEDGE_BASE/              # 知识库（保留）
├── design/                      # 设计文档（保留）
└── document_templates/          # 文档模板（保留）
```

### 3.2 新建开源标准文档

| 文件 | 内容 |
|------|------|
| `README.md` | 双语重写：英文为主，关键部分中文对照；包含项目简介、功能特性、架构图、快速开始、贡献指南链接、许可证 |
| `CONTRIBUTING.md` | 贡献指南：如何提交 Issue、PR 流程、代码规范、Commit 规范 |
| `CODE_OF_CONDUCT.md` | 行为准则：基于 Contributor Covenant |
| `SECURITY.md` | 安全策略：如何报告安全漏洞 |
| `THIRD_PARTY_LICENSES.md` | 第三方许可证声明（确认存在并完善） |

### 3.3 README.md 双语结构

```markdown
# Zensers — Open-Source Automated Market Research System
# Zensers — 开源自动化市场研究系统

> Multi-Agent collaborative intelligent market research platform
> 基于多Agent协作的智能市场研究平台

## Features / 核心特性
## Architecture / 系统架构
## Quick Start / 快速开始
## Documentation / 文档
## Contributing / 贡献
## License / 许可证
## Roadmap / 路线图
```

### 3.4 config/ 目录安全化

- 将 `config/settings.yaml` 移入 `.gitignore`（已有部分配置）
- 新建 `config/settings.example.yaml` 作为配置模板（去除敏感默认值）

---

## 4. 测试目录整理

### 4.1 清理后的 tests/ 结构

```
tests/
├── __init__.py
├── test_e2e.py
├── test_e2e_survey.py
├── test_chart_generator.py
├── test_cn_chart_extraction.py
├── test_contradiction_detector.py
├── test_css_extractor.py
├── test_css_integration.py
├── test_data_validation.py
├── test_knowledge_compiler.py
├── test_knowledge_importer.py
├── test_knowledge_v2.py
├── test_md_table_conversion.py
├── test_pause_race_condition.py
├── test_quality_control.py
├── test_regions.py
├── test_report_pipeline_e2e.py
├── test_table_extractor.py
├── test_cancel_pause_phase1.py
├── test_revision_behavior.py
├── test_revision_comprehensive.py
├── test_revision_pipeline_breakpoints.py
├── test_revision_e2e_real.py
├── test_profitability_bug_fix.py
├── test_profitability_bug_fix_v2.py
├── test_phase1_fixes.py
├── test_phase3.py
├── test_phase4.py
├── test_fixes.py
├── test_fixes_quick.py
├── test_final_imports.py
├── test_quick_verify.py
├── test_v7_fix_verification.py
├── test_survey_engine_p1p2.py
├── test_survey_mock.py
├── unit/
├── integration/
├── e2e/
├── quality/
├── mcp/
└── benchmark/
```

### 4.2 测试可运行性验证

- 执行 `pytest tests/ --collect-only` 确认保留的测试可被发现
- 修复因文件移动导致的 import 错误

---

## 5. 部署配置

### 5.1 Dockerfile

```dockerfile
# Stage 1: Frontend build
FROM node:18-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt

# Copy backend code
COPY src/ ./src/
COPY config/ ./config/
COPY prompts/ ./prompts/
COPY VERSION ./

# Copy frontend build
COPY --from=frontend-builder /app/web/.next ./web/.next
COPY --from=frontend-builder /app/web/public ./web/public
COPY --from=frontend-builder /app/web/package*.json ./web/
COPY --from=frontend-builder /app/web/next.config.js ./web/

EXPOSE 8000 3000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.2 docker-compose.yml

```yaml
version: "3.8"
services:
  app:
    build: .
    ports:
      - "8000:8000"
      - "3000:3000"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./output:/app/output
      - ./logs:/app/logs
    depends_on:
      - redis
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD:-zensers}
    ports:
      - "6379:6379"
```

### 5.3 GitHub Actions CI

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ -x --tb=short
      - run: ruff check src/ || true  # lint（首次允许警告）

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "18"
      - run: npm ci
      - run: npm run lint
      - run: npm run build

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: trufflesecurity/trufflehog@main
        with:
          extra_args: --only-verified
```

### 5.4 Makefile 增强

在现有 Makefile 基础上追加：

```makefile
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

release:
	@echo "Creating release v$$(cat VERSION)..."
	git tag v$$(cat VERSION)
	git push origin v$$(cat VERSION)
```

---

## 6. 安全审计

### 6.1 检查清单

| 检查项 | 方法 | 处理 |
|--------|------|------|
| 硬编码 API Key / Token | `grep -rE "(sk-|api_key|token|password)\s*=" src/` | 移除或替换为环境变量引用 |
| 硬编码密码 | `grep -rE "password\s*=\s*['\"]" src/ config/` | 替换为环境变量 |
| .env 泄露 | 确认 `.env` 在 .gitignore | 已确认 |
| config/settings.yaml 泄露 | 确认在 .gitignore 并创建 example | 需创建 settings.example.yaml |
| web/.env.local 泄露 | 确认在 .gitignore | 需添加 |
| 日志文件泄露 | 确认 `*.log` 在 .gitignore | 已确认 |
| IP / 内部地址泄露 | `grep -rE "192\.168|10\.\d+\.\d+\.\d+" src/` | 移除或替换 |
| 大文件 | 检查仓库中是否有 >1MB 的非必要文件 | 排除 |
| 第三方许可证合规 | 检查所有依赖的许可证兼容性 | 完善 THIRD_PARTY_LICENSES.md |

### 6.2 start.bat 修复

将硬编码路径：
```batch
D:\conda\python.exe -m uvicorn ...
```
改为通用路径：
```batch
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

### 6.3 config/settings.example.yaml

从 `config/settings.yaml` 创建模板，移除所有敏感默认值，替换为占位符。

---

## 7. 项目结构优化

### 7.1 pyproject.toml 修正

- 确认 `[project.scripts]` 入口 `src.cli:main` 可用
- 版本号从 `VERSION` 文件同步

### 7.2 start.sh 优化

- 确保 uvicorn 在虚拟环境中执行
- 添加环境检查提示

### 7.3 清理后的根目录

```
zensers/
├── .gitignore
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml
├── LICENSE
├── Makefile
├── README.md
├── SECURITY.md
├── THIRD_PARTY_LICENSES.md
├── VERSION
├── config/
│   ├── settings.example.yaml    # 新增：配置模板
│   ├── agents.yaml
│   ├── content_quality.yaml
│   ├── i18n.yaml
│   ├── keyword_mappings.yaml
│   ├── mcp.yaml
│   ├── research_frameworks.yaml
│   ├── system.yaml
│   ├── document_templates/
│   └── templates/
├── data/                         # .gitignore 中已排除
├── docs/
├── output/                       # .gitignore 中已排除
├── prompts/
├── pyproject.toml
├── pytest.ini
├── pyrightconfig.json
├── requirements.txt
├── requirements-dev.txt
├── requirements-lock.txt
├── scripts/
├── src/
├── start.bat
├── start.prod.sh
├── start.sh
├── tests/
└── web/
```

---

## 8. Git 初始化与发布

### 8.1 初始化步骤

```bash
# 1. 初始化仓库
git init

# 2. 添加所有文件（.gitignore 会自动排除）
git add .

# 3. 首次提交
git commit -m "feat: initial release v1.0.0

- Multi-agent collaborative market research system
- Python backend with FastAPI + Next.js frontend
- Professional report generation with McKinsey-style charts
- Support for any OpenAI-compatible LLM
- Persistent state with crash recovery"

# 4. 添加远程仓库
git remote add origin git@github.com:sunchaokun/zensers.git

# 5. 设置主分支
git branch -M main

# 6. 推送
git push -u origin main

# 7. 打标签
git tag -a v1.0.0 -m "Release v1.0.0: Initial public release"

# 8. 推送标签
git push origin v1.0.0
```

### 8.2 GitHub Release Notes

```markdown
# Zensers v1.0.0 — Initial Public Release / 首次公开发布

## 🎉 About / 关于

Zensers is an open-source automated market research system powered by multi-agent collaboration.
Zensers 是一个基于多Agent协作的开源自动化市场研究系统。

## ✨ Key Features / 核心特性

- **Multi-Agent Collaboration**: Dynamic agent generation for complex research tasks
- **Professional Reports**: McKinsey-style charts and publication-quality output
- **Model Agnostic**: Works with any OpenAI-compatible LLM (GPT, Claude, local models)
- **Persistent State**: Crash recovery and resume from checkpoints
- **Extensible Skills**: Plugin system with auto-discovery

## 🚀 Quick Start / 快速开始

```bash
git clone https://github.com/sunchaokun/zensers.git
cd zensers
pip install -r requirements.txt
cp config/settings.example.yaml config/settings.yaml
# Configure your LLM API key in settings.yaml
python -m uvicorn src.api.main:app --port 8000
```

## 📦 What's Included / 包含内容

- Python 3.10+ backend with FastAPI
- Next.js 14 frontend
- Docker support
- 10+ built-in chart types
- Web search and scraping skills
- DOCX/PPT export
```

---

## 9. 执行顺序

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 文件清理（移动到临时目录） | 30 min |
| 2 | .gitignore 增强 | 10 min |
| 3 | 安全审计（扫描+修复） | 30 min |
| 4 | 项目结构优化（start.bat、pyproject.toml等） | 20 min |
| 5 | 文档重构（docs/整理 + 新建开源文档） | 60 min |
| 6 | 部署配置（Dockerfile、docker-compose、CI） | 40 min |
| 7 | 测试目录清理 + 可运行性验证 | 20 min |
| 8 | 最终检查 + Git初始化 + 推送 | 20 min |
| **总计** | | **~3.5 hours** |

---

## 10. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 清理后测试无法运行 | 移动前先 `pytest --collect-only` 记录基线，清理后对比验证 |
| 移除文件导致 import 断裂 | 全局搜索被移除文件的引用，逐一修复 |
| Docker 构建失败 | 本地测试 Docker 构建后再推送 |
| 敏感信息遗漏 | 使用 trufflehog 扫描 + 人工复查 |
| 前端构建依赖问题 | 确保 `web/.env.local` 有示例文件 |
