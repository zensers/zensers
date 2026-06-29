# B5 修复进度

## 2026-06-19 核实与计划

### 核实完成
- [x] result_aggregator.py 数据层核实
- [x] content_orchestrator.py HTML fallback 渲染核实
- [x] word_default.html / word_research_report.html 模板核实
- [x] document_generation_agent.py DOCX 渲染核实
- [x] document_generator.py DOCX TOC 核实
- [x] html_to_word.py / base_parser.py 转换器核实
- [x] api.ts 前端类型核实

### 发现的 Bug
| Bug | 位置 | 严重度 |
|-----|------|--------|
| T1: subsection heading level 错误（`<h2>` 应为 `<h3>`） | 两个 HTML 模板 | HIGH |
| T2: 模板 TOC 完全扁平，不显示 subsection | 两个 HTML 模板 | HIGH |
| T3: 有 subsection 时 section.content 被丢弃 | 两个 HTML 模板 | HIGH |
| T4: subsection 输出不含 points，三级信息丢失 | result_aggregator.py | HIGH |
| T5: DOCX subsection 内 heading 全部跳过 | document_generation_agent.py L646-648 | MEDIUM |
| T6: DOCX TOC 无三级 | document_generator.py | MEDIUM |
| T7: HTML→DOCX 无 h4_size 样式 | html_to_word.py | LOW |

### 计划制定完成
- [x] task_plan.md 已创建（7 个 Phase）
- [x] findings.md 已创建
