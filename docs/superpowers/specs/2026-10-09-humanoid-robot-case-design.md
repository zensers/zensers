# 设计文档：人形机器人行业研究宣传案例（Zensers 真实流程）

> 日期: 2026-10-09 · 状态: 已审查（会话内批准） · 参考: findings.md（NEV 参考案例解剖）

## 1. 目标与背景

用 Zensers 系统真实跑完一次端到端行业研究，产出《中国人形机器人产业深度研究报告》：
- **真实数据**：真 LLM（mimo-v2.5）+ 真 anysearch 搜索 + akshare/雪球技能 + 白名单来源，**不得使用伪数据**
- **真实流程**：ResearchOrchestrator 完整编排（分解→采集→校验→写作→L1-L5 审计→校准→图表→Word）
- **格式要求**：Word DOCX，**页数 >40 页**（按 2000 字符/页估算口径，留余量目标 ≥45）
- **方法参考**：《中国新能源汽车行业深度研究》严格研究配方（findings.md §7），补齐其三大缺口

## 2. 章节结构（12 章）

| # | 章节 | 核心内容 | 目标字数 |
|---|---|---|---|
| 0 | 行业概览与研究范围界定 | 术语界定、技术路线（全尺寸/轮式/仿生）、统计口径声明 | 7000 |
| 1 | 市场规模与增长预测 | 全球/中国装机出货量、预测分歧交叉验证 | 8000 |
| 2 | 产业链全景 | 上游零部件→中游本体→下游集成 | 8000 |
| 3 | 核心零部件与降本路径 | 丝杠/减速器/空心杯电机/传感器 BOM 拆解、国产替代 | 8500 |
| 4 | 竞争格局 | Tesla/Figure/宇树/智元/优必选/小鹏梯队与商业模式 | 8000 |
| 5 | 技术趋势 | VLA/端到端模型、灵巧手、数据采集与仿真训练 | 7500 |
| 6 | 应用场景与商业化 | 工厂/物流/教育科研/商用服务、真实订单交付 | 7500 |
| 7 | 政策环境与监管 | 工信部指导意见、地方补贴、标准与数据安全 | 6500 |
| 8 | 投融资与资本市场 | 一级融资图谱、IPO、二级估值（akshare/雪球真数据） | 7500 |
| 9 | 风险分析 | 技术/需求兑现/供应链/估值泡沫/伦理 | 6500 |
| 10 | 投资建议与策略 | 赛道受益排序、节奏、关注标的 | 6000 |
| 11 | 结论与展望 | 关键判断回顾 | 5000 |

正文目标合计 **~88,500 字符 ≈ 44 页** + 14 图 ≈ 4-5 页 → **预计 48-50 页**（>40 有余量）。

## 3. 页数与字数机制（对齐调研后的实际约束链）

章节字数的真实约束链 = 框架 YAML `min_section_length` + ChapterWriter `max_tokens=8192` + 收敛循环（TARGET_SCORE=80，最多 3 轮）：

| 机制 | 位置 | 值 | 动作 |
|---|---|---|---|
| min_section_length | config/research_frameworks.yaml:51（industry_report 已内置 5000，注释"为30-40页报告提升"） | 5000 | 不改，运行时核对生效（plan Step 7.3） |
| Writer 每次 LLM 调用上限 | src/agents/fixed_agents/report_upgrade/chapter_writer.py:195 | max_tokens=8192 | 不改（8192 tokens ≈ 4-6K 中文字/次调用，多节/多段分次生成） |
| 总搜索配额运行上限 | src/core/research_framework_manager.py:47（硬编码 30） | 30 | 新增 env 覆盖 `ZENSERS_MAX_TOTAL_SEARCHES`（默认 30 不变，案例运行设 60） |
| 图表 | 每章 1-2 张 | - | 共 14 张，输出持久化 |

## 4. 真实数据策略（NEV 三大缺口的对症修复）

1. **证据零缺口**：所有 data_points 必须带 source_url + evidence_id；运行完成后跑 L1-L5 审计核查，L3 missing_source_url 类 issue 数必须为 0，formal_complete=true
2. **图表持久化**：图表 PNG 输出到 `output/cases/humanoid_robot/charts/`（相对项目根的持久目录，禁止 Temp 目录），docx 真嵌入 ≥12 张
3. **主题锁定**：每章生成后做主题实体校验，防止内容漂移（NEV 曾漂移到手机）；漂移章重写

## 5. 运行方式

- 入口：改写 `tools/run_full_research.py` 模式（真 ResearchOrchestrator，interaction_mode=False，framework=standard，output_type=industry_report）
- 输出目录：`output/cases/humanoid_robot/`（research_result.json / report.html / 最终 docx / charts/）
- 环境：.env 已有 LLM_API_KEY（mimo-v2.5）+ ANYSEARCH_API_KEY ✅
- 预计耗时：1-2 小时（12 章 × Writer→Reviewer 循环 + 3 轮 defense_loop）

## 6. 审查与修订流程（用户指定，生成后执行）

```
zensers 真跑出报告
→ 人工审查（我）：数据真实性抽验 / 证据链完整性 / 主题一致性 / 页数与排版 / 图表质量
→ 提出修订意见（结构化 issue 清单）
→ 执行修订（走系统修订机制 + 必要的手动审查修复轮）
→ 复审确认达标
→ 通知用户定稿（用户最终确认）
```

审查维度（依据 research_industry_report_benchmark 基准方法论）：
- 口径声明完备、跨期比较正确、机制解释有据、风险边界清晰
- evidence/provenance 可溯源、来源域名可信度

## 7. 验收标准

| 项 | 标准 |
|---|---|
| 页数 | DOCX ≥ 40 页（估算 ≥ 45 留余量） |
| 章节 | 12 章全部 non-failed，无占位句 |
| 图表 | ≥ 12 张真实嵌入（有来源标注） |
| 证据 | L3 issue=0，formal_complete=true，全 data_points 可溯源 |
| 人工审查 | 修订意见全部关闭 |
| 定稿 | 用户确认 |

## 8. 明确不做

- 不使用任何伪数据/手工编造内容
- 不引用半导体/AI 伪案例（output/full_research/revised_report.docx、ai_report.docx）的任何数据
- 不改动 src/ 全局默认参数（优先脚本内覆盖）