# 批量案例生成流水线设计（batch_case_pipeline）

日期：2026-10-11
状态：已确认（全自动闭环 / docx 定稿人工转 PDF / 串行+断点续跑 / 热门行业选题 / 无人值守）

## 1. 背景与目标

人形机器人案例验证了"视觉优化后"的单案例产出质量，但当前流程由 5+ 个手工散件拼接
（`run_*_case.py` 研究 → `backfill_chart_sidecar.py` 图表 → `render_humanoid_case_docx.py` 渲染 → 手工审查）。
本设计提供一个**无人值守的批量调度器**，串联 zensers 既有模块，完成：

```
选题 → 研究 → 图表 → 渲染 → 审查 ⇄ 修订 → 定稿 docx
```

非目标：PDF 输出（人工转）；多案例并发；HTML 模板改版。

## 2. 选题原则

- **只选热门/高景气赛道**，回避传统行业。入选标准（满足其一）：
  1. 政策强催化（列入国家规划/有专项支持）；
  2. 一级市场融资额近两年高增长；
  3. 技术拐点已现（Gartner 曲线左侧~爬升期）。
- 默认案例池写入 `config/batch_cases.yaml`（用户可增删）：人形机器人、固态电池、
  低空经济（eVTOL）、AI 大模型/Agent、具身智能、商业航天、合成生物、智算中心（AIDC）、
  端到端自动驾驶、量子计算、可控核聚变、脑机接口。
- 传统行业（钢铁/煤炭/纺织/建材等）不得进入默认池。
- 每案例配置：`case_id`（目录名，英文蛇形）、`topic`（报告全称）、`domain_keywords`
  （主题漂移检测用领域词，≥4 个）、可选 `chapters` 覆盖默认 12 章框架。

## 3. 架构

```
tools/batch_case_pipeline.py        # 调度器（唯一入口，asyncio 串行）
config/batch_cases.yaml             # 案例池 + 公共默认值
output/cases/<case_id>/             # 每案例产物目录（沿用现有约定）
  state.json                        # 阶段状态机（断点续跑依据）
  research_result.json              # 阶段1产物
  charts.json + charts/             # 阶段2产物
  report.html / report_draft.docx   # 阶段3产物
  review_report.json                # 每轮审查报告（round1..n 追加）
  manifest.json                     # 定稿元数据
  <报告标题>.docx                    # 定稿文档
logs/batch_YYYYMMDD_HHMMSS.log      # 全局日志（每案例独立 section）
batch_summary.json（output/ 下）     # 批次汇总
```

### 状态机

```
research → charts → render → review ─┬─ pass → finalize
                        ↑            └─ issues(≤max_review_rounds) → revise ┘
                        └──(revise 后重渲染受影响产物)
```

每阶段开始写 `state.json{"stage": ..., "status": "running"}`，成功后写 `done` +
产物校验值（如 sections 数、charts 数、docx 大小）。重跑时 `done` 阶段直接跳过；
`--from-stage <s>` 可强制从指定阶段重跑（其后阶段状态重置）。

## 4. 阶段实现（模块接线）

### 4.1 research
- `ResearchOrchestrator(use_intelligent_routing=True).research(...)`，参数对齐
  `tools/run_humanoid_robot_case.py`（interaction_mode=False，output_type=industry_report）。
- 校验：`result.status ∈ {completed, completed_with_warnings}` 且 sections 非空。
- **自动化**：不设任何人机交互点；domain_score 主题漂移检测（关键词密度 <1.0/千字记 issue，
  不阻断——留待 review 阶段统一处置）。

### 4.2 charts
- 复用 `DocumentGenerationAgent._generate_charts_for_html(research_result)`：
  内部走 `chart_planner`（LLM 规划，含 source 字段与口径硬约束——本次视觉优化的成果）
  + `ChartGenerator`（新主题渲染），并落 sidecar `charts.json`。
- 校验：图表覆盖率、PNG 存在性与尺寸（复用 `_validate_rendered_image` 规则）不达标时
  **不判阶段失败**，作为 `chart_coverage` issue 传入 review 阶段统一处置。

### 4.3 render
- `DocumentGenerationAgent.execute(action="produce_document", output_format="html")`
  产出 report.html（ContentOrchestrator 路径，含封面/目录/图表锚点）。
- 再以 `output_format="docx"` + `request._preview_html_path=report.html` 复用预览 HTML
  转换（`HTMLToWordConverter` 新排版：真 TOC 域/三线表/页码/图表编号）→ report_draft.docx。
- 校验：docx 存在、>500KB、内嵌图片数与 charts 数一致（python-docx 抽验）。

### 4.4 review（全自动，无人门禁）
结构化检查，产出 `review_report.json`：
```json
{
  "round": 1,
  "pass": false,
  "score": 78,
  "issues": [
    {"code": "missing_source_url", "section": "竞争格局", "severity": "high", "detail": "..."},
    {"code": "topic_drift", "section": "政策环境", "severity": "medium"},
    {"code": "chart_leak", "section": "-", "severity": "high", "detail": "source=content"},
    {"code": "docx_format", "severity": "low", "detail": "..."}
  ]
}
```
检查项（全部沿用既有能力，不新造轮子）：
1. `QualityCheckAgent.check_by_sections`：数据一致性、指标-数值语义、L3 证据链缺 URL；
2. research 元数据：`formal_complete`、`quality_gate_status`、`defense_audit.issues`；
3. 主题漂移：domain_keywords 密度（4.1 遗留的 issue 并入）；
4. 图表：sidecar 中 source 命中 `content/fetched` 字面量、caption 缺失、PNG 缺失；
5. docx：TOC 域存在、无 `Table Grid` 残留、图片居中、页脚含 PAGE 域（复用
   `tests/unit/converters/test_word_layout.py` 的断言逻辑抽验）。

### 4.5 revise
- severity=high 的 issue 才触发修订；low/medium 记录不阻塞。
- 内容类（数据/证据/漂移）：`QualityCheckAgent.execute_and_fix` 对受影响章节 LLM 修订
  `research_result.json` 对应 section；
- 图表类：删除问题 chart 记录后重跑 charts 阶段（仅该章节重新规划）；
- 格式类：直接重跑 render。
- 修订后重渲染受影响产物 → 回到 review。`max_review_rounds`（默认 3）轮仍不 pass →
  状态 `needs_human`（问题清单已落盘），**不阻塞批次**。

### 4.6 finalize
- 复检 pass（或达到轮次上限且无 high issue）→ `report_draft.docx` 复制为
  `<报告标题>.docx` 定稿；
- 写 `manifest.json`：case_id/topic/轮次/final score/各阶段耗时/产物清单/状态
  （`done` | `needs_human` | `failed`）。

## 5. 调度器行为

- **串行**：同时只跑 1 个案例；案例内阶段串行；单案例失败自动重试 1 次（从失败阶段续），
  再失败标记 `failed` 并继续下一案例。
- **无人值守保证**：全程无 `input()`/确认点；LLM/搜索瞬时异常指数退避重试 3 次；
  Ctrl+C 安全中断（当前阶段标记 `interrupted`，重跑续接）。
- 批次结束打印并落盘 `batch_summary.json`（每案例状态/耗时/轮次/score/定稿文件名）。
- 退出码：全成功 0；部分失败 1；配置错误 2。

## 6. CLI

```bash
python tools/batch_case_pipeline.py                           # 跑全池
  --cases a,b                 # 指定案例
  --from-stage charts         # 从指定阶段强制重跑（其后重置）
  --max-review-rounds 3
  --list                      # 仅列出案例池与状态
  --config path/to/yaml       # 默认 config/batch_cases.yaml
```

## 7. 测试与验收

1. 单测（`tests/unit/tools/` 或 `tests/tools/`）：
   - YAML 解析与校验（缺 case_id/topic 报配置错误；传统行业关键词出现在默认池时告警）；
   - 状态机推进/跳过/`--from-stage` 重置；
   - review issue → revise 分派映射（内容/图表/格式三类各一）；
   - 失败隔离与重试 1 次；needs_human 不阻塞；
   - mock LLM/搜索的 review→revise→pass 闭环演练。
2. E2E 验收（真实 LLM）：
   - humanoid_robot：已有 research_result.json → 验证阶段跳过与 charts 起步续跑；
   - 新案例（案例池任选，建议固态电池已有半成品脚本可直接对照）：全 6 阶段真实跑通，
     产出定稿 docx + manifest；
   - 批次含 1 个注入失败案例（无效 topic），验证 failed 隔离与 summary 正确。

## 8. 涉及文件

| 文件 | 动作 |
|------|------|
| `tools/batch_case_pipeline.py` | 新增（调度器+状态机+CLI） |
| `config/batch_cases.yaml` | 新增（热门行业默认池 12 案例） |
| `tests/tools/test_batch_case_pipeline.py` | 新增单测 |
| `docs/superpowers/specs/` | 本文档 |

复用（不改动）：`ResearchOrchestrator`、`DocumentGenerationAgent`、`QualityCheckAgent`、
`chart_planner`、`ChartGenerator`、`HTMLToWordConverter`、`ContentOrchestrator`。
