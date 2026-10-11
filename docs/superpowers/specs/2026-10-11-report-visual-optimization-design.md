# 研究报告视觉优化设计：图表系统 + Word 排版

日期：2026-10-11
状态：已确认（用户逐节批准）
基准样张：`output/cases/humanoid_robot/`（23 张图 + 1 份 docx）

## 1. 背景与目标

当前系统生成的行业研究报告在视觉效果上与国际专业研究机构（麦肯锡/高盛/券商研报）存在明显差距。本设计覆盖两条优化线：

1. **数据分析图表**：渲染层 + 规划层
2. **Word 文档排版**：转换层

范围界定：视觉层 + 规划层。HTML 预览模板（`content_orchestrator` 及模板 CSS）本期不动。

## 2. 现状诊断（基于 humanoid_robot 样张）

### 2.1 图表问题

| # | 问题 | 实例 | 根因 |
|---|------|------|------|
| 1 | 文字重叠：副标题左对齐 `ax.text(0,1.02)` 与居中标题、最高柱数值标签碰撞 | bar_1、radar_13 | `_set_title` 布局 |
| 2 | 数值标签越界裁切 | bar_1"364.4"、hbar_7"1.4万"、barline_3"127.0" | `_set_numeric_limits` padding 不足 |
| 3 | 来源字段泄漏：`\| 来源：content` | 全部 23 张 | `document_generation_agent.py:1406` 把 `plan.subtitle` 误用作 source |
| 4 | 饼图大片留白 | pie_9 | 8×8 正方形画布 + 底部注释占位 |
| 5 | 配色不成体系：12 色杂烩，单系列无强调 | pie_9、hbar_7 | `PALETTE_12` |
| 6 | 数字格式混排（5800 与 1.1万 同图；无千分位） | hbar_7 | 各渲染器内联格式化 |
| 7 | 双轴图折线标签与柱标签重叠 | barline_3 | 无错位策略 |
| 8 | DPI 150 偏低；来源注居中小字斜体 | 全部 | `_add_annotations` |

### 2.2 Word 问题

| # | 问题 | 现状 |
|---|------|------|
| 1 | 假目录：手写文本+制表符+硬编码页码，非 TOC 域 | 全文档 0 个 TOC 域 |
| 2 | 章节不分页 | `pageBreakBefore`=0 |
| 3 | 图片一刀切 5.0in 宽，不区分宽高比，左对齐 | 23 张图 |
| 4 | 表格 Table Grid 黑框：无斑马纹、无跨页重复表头、列宽不自适应 | 25 张表 |
| 5 | 标题用 Word 默认蓝色；H1 后紧跟同文 H2 重复 | 全部标题 |
| 6 | 页脚无页码 | 仅版权行 |
| 7 | 纸张 US Letter 8.5×11in，左右边距 1.25in、上下 1.0in | 全文 |
| 8 | 无图表编号体系 | 全部 |

## 3. 方案选型

- **方案一（采纳）**：现有渲染器原地重构 + 共享设计令牌。风险低、改动集中、保留 ChartSidecar 审计契约。
- 方案二（否决）：替换渲染栈（plotly/ECharts 无头截图）——重依赖、Windows 服务环境不稳、sidecar 契约全部重写。
- 方案三（否决）：docxtpl 模板填充——动态章节/图表结构下模板约束过脆。

## 4. 图表设计系统

### 4.1 新增 `src/services/chart_theme.py`（设计令牌）

```python
# 色彩（麦肯锡风 + 保留品牌基因）
PRIMARY = "#1A2744"    # 藏青：单系列柱/线默认色
ACCENT  = "#C9A227"    # 金：关键数据点强调（最大值/最新期）
SERIES  = ["#1A2744", "#4A6FA5", "#A8BCD0", "#C9A227"]  # 多系列≤4，超出降灰阶
NEUTRAL = "#8C8C8C"    # 非重点系列/基线
GRID    = "#E0E0E0"    # 仅水平实线 0.8pt；废除 #FAFAFA 底色，纯白背景
TEXT_SUB = "#666666"; TEXT_NOTE = "#999999"; TEXT = "#333333"

# 字号（微软雅黑）
TITLE=13 Bold 左对齐；SUBTITLE=9 灰；AXIS=9；VALUE_LABEL=8.5；NOTE=7.5

# 规格
DPI=200（全局标准）；宽幅图 9×5.2；饼/雷达图（横版）8×4.8
```

**DPI 协调**：`src/content/format_strategy.py` 的 `DOCXStrategy.get_chart_style()` 现为 `dpi=150, figsize=(5.0,3.5)`，与全局 DPI=200 冲突——本次一并升级为消费 chart_theme 令牌（dpi=200），避免两套配置源。

### 4.2 公共布局引擎（十类渲染器共用）

1. **标题区重构**：废弃"居中 title + `ax.text(0,1.02)` 副标题"混排，改为 fig 级左对齐标题块（`fig.text` 标题行 + 副标题行 + 金色短下划线），配 `fig.subplots_adjust(top≈0.82)` 预留头部。**约束**：必须移除/替换 radar 渲染器内的 `plt.tight_layout()`（chart_generator.py:980），否则其会覆盖 subplots_adjust 并忽略 fig.text artist，导致标题与极坐标区重叠。
2. **防裁切 `_auto_margins()`**：纵向上界扩至 `max×1.15`；横向条形图右界扩至 `max×1.12`；数值标签永不越界。
3. **数字格式 `_format_value()`**：全图单一规则——≥1万→`x.x万`；≥1000→千分位 `1,234`；≥1→一位小数；<1→两位小数；`%`→一位小数。
4. **来源注规范化**：左下角 `资料来源：…`，右下角 `单位：…`；source 命中 `{"content", "fetched", "Public data compilation"}` 字面量时走兜底链。
5. **DPI 150→200**。

### 4.3 各图型规则

| 图型 | 升级点 |
|------|--------|
| bar | 关键柱金色强调，其余藏青；关键柱判定：类目为时间序列时取最新期，否则取最大值 |
| hbar | 长条数值标签条内右端白字，短条条外深灰 |
| pie | 改环形图 donut + 右侧图例带数值，中心放合计；8×4.8 横版画布消灭留白 |
| bar_line | 折线只标注首末两点数值；柱标签默认柱内顶部白字（柱色藏青亮度低，可读）；**矮柱降级**：柱高不足阈值（标签高度放不下）时标签外置柱顶深灰字；图例横排标题下 |
| line | 去图例框，系列名直接标注在线端 |
| radar | 副标题移出极坐标区；类目标签加大 pad |
| scatter/bubble/waterfall/quadrant | 同步套用主题令牌与公共布局 |

## 5. 规划层修复

### 5.1 source 泄漏修复

泄漏点共 3 处：
- `document_generation_agent.py:1406`（`source=plan.subtitle or ...`，subtitle 被误用作 source）
- `document_generation_agent.py:1418`（chart 字典的 `"source"` 字段同样取 `plan.subtitle`）
- `src/agents/fixed_agents/report_upgrade/orchestrator.py:1054`（`source=plan.data_source`）

修复方式（依赖 5.2 先行）：三处统一改为 `source=plan.source`（5.2 新增字段），为空则兜底 `"公开资料整理"`。**注意**：现有 `plan.data_source` 取值恒为 `"content"/"fetched"`（数据出处类型，非机构名），无显示价值，不再参与 source 兜底链。渲染入口过滤集合：`{"content", "fetched", "Public data compilation"}` 字面量一律走兜底。

### 5.2 chart_planner 字段与提示词升级

代码落点（不止提示词）：
1. **`_JSON_SCHEMA` 模板**（chart_planner.py:145，现指示 LLM `"subtitle": "数据来源说明"`——泄漏根因）：新增 `source` 输出字段（真实机构来源），subtitle 指示语改为"口径与单位说明"；`data_source` 字段保留原语义（数据出处类型 content/fetched），命名不变以兼容现有消费方。
2. **`_resolve_chart` 字段装载**（chart_planner.py:1101-1115）：同步装载新 `source` 字段（缺失时回退 `"公开资料整理"`）。
3. **`ChartPlan` dataclass**（chart_planner.py:46-59）：新增 `source: str = ""` 字段。
4. **口径一致性硬约束**：季度值与累计值禁止同图混排；确需对比时分组呈现并在 subtitle 显式标注各期口径。
5. **选型规则强化**：趋势→line/bar_line；构成→donut（≤6）/hbar；对比→bar；相关→scatter；多维权衡→radar/quadrant，附一句话理由。
6. **subtitle/caption 分工**：subtitle 只放口径与单位说明；caption 只放注释。

### 5.3 软校验

`_validate_config` 检测 categories 同时出现季度与累计口径模式时记 warning（不阻断，供质量检查 Agent 消费）。

## 6. Word 排版系统（`html_to_word.py` 重构 + 新增 `word_styles.py`）

### 6.1 页面

A4（21×29.7cm）；边距上下 2.54cm、左右 3.17cm（可用宽约 14.7cm）。

### 6.2 正文（券商研报规范）

| 元素 | 规格 |
|------|------|
| 正文 | 宋体 10.5pt（五号），行距固定 22pt，首行缩进 2 字符，两端对齐。缩进实现：`w:ind` 的 `w:firstLineChars="200"`（字符单位，随字号缩放）+ `w:firstLine="420"` twips 兜底 |
| H1 | 黑体 16pt 加粗藏青 #1A2744，段前分页，段后 18pt，底部 1pt 藏青横线 |
| H2 | 黑体 14pt 加粗藏青，段前 12pt 段后 6pt |
| H3 / H4 | 黑体 12pt / 宋体加粗 11pt |
| 重复标题 | H2 文本与前一个 H1 去编号后相同则跳过 |

### 6.3 目录与页码

- 真 TOC 域 `TOC \o "1-3" \h \z \u`；`settings.xml` 写入 `updateFields=true`，Word/WPS 打开时自动刷新页码。**告警**：Word 打开时会弹"是否更新域"确认框（需点"是"）；LibreOffice 不响应 `updateFields`。验收标准按"Word/WPS 打开并确认后页码正确"执行。
- 页眉：左 "ZENSERS" + 右报告标题，8pt，段落底边框 0.5pt 藏青横线（`w:pBdr`）。
- 页脚：居中 "第 X 页 共 Y 页"（PAGE/NUMPAGES 域，fldChar/instrText 手工构造），版权行缩小置于其下。

### 6.4 图表与表格

- 图片：宽度 = `min(14.7cm, 像素宽/200dpi)`，居中；饼/雷达图（横版 8×4.8）限宽 11cm；图片段落 keep_with_next 绑定下方注释。
- 表格：**显式移除现有 `table.style='Table Grid'`**（html_to_word.py:762，否则 Grid 边框与 tblBorders 叠加），改为三线表（`w:tblBorders`：上下 1pt 藏青粗线，左右/内线 none；表头行 `w:tcBorders/w:bottom` 0.5pt 细线）；表头浅藏青底 `#E8EDF4` 深字加粗 9.5pt；跨页重复表头（表头行 `w:trPr/w:tblHeader`）；数据行 9pt。
- 图表编号：图片上方"图表 N：{图题}"（黑体 9pt 藏青），全文连续计数；图下注释 8.5pt 灰居中。

### 6.5 封面与尾页

封面保留文字结构：金色分隔线改 2.25pt 实线段落边框，元信息区浅灰底色块。免责声明页维持独立分页。

## 7. 错误处理

- 单图渲染失败降级为占位文字并记日志，不阻断报告（保留现有行为）。
- Word 转换沿用原子保存。

## 8. 测试与验收

1. 单测：`_format_value`、`_auto_margins`、source 过滤与兜底链、TOC 域存在性、`updateFields` 设置、分页符、表格三线边框与 `tblHeader`、页脚 PAGE/NUMPAGES 域、重复标题跳过、页眉 pBdr。
2. **必挂断言同步更新**（重构会改变这些现有断言）：
   - `tests/unit/test_chart_dpi_fix.py:20,52-58`（`dpi==150` → 200）
   - `tests/unit/test_format_strategy.py:42`（DOCX 策略 `dpi==150` → 200）
   - `tests/integration/test_e2e_format_pipeline.py:268-271`（DOCX 策略 dpi 断言）
   - `tests/test_chart_generator.py:31`（`PALETTE_12==12` → 新 SERIES 结构）
   - `tests/unit/test_chart_title_caption_regression.py:8-19`（直测 `_set_title` → 改测 fig 级标题块）
   - `tests/unit/services/test_chart_planner_e2e.py:81`（`source=plan.subtitle` 复刻 bug → 改 `plan.source`）
3. 冒烟：10 类图型渲染无异常 + 输出尺寸校验（Pillow，200dpi 下 ≥320×180 仍成立）。
4. 视觉回归：用 humanoid_robot 样张数据重渲全部 23 张图 + 重建 docx，人工比对验收。

## 9. 涉及文件

| 文件 | 动作 |
|------|------|
| `src/services/chart_theme.py` | 新增 |
| `src/services/chart_generator.py` | 重构渲染器（含移除 radar 的 tight_layout） |
| `src/services/chart_planner.py` | `_JSON_SCHEMA`/`_resolve_chart`/`ChartPlan` 加 source 字段 + 提示词升级 |
| `src/agents/fixed_agents/document_generation_agent.py` | source 透传修复（1406、1418 两处） |
| `src/agents/fixed_agents/report_upgrade/orchestrator.py` | source 透传修复（1054 行） |
| `src/content/format_strategy.py` | DOCXStrategy 图表样式升级为消费 chart_theme 令牌（dpi 150→200） |
| `src/converters/word_styles.py` | 新增 |
| `src/converters/html_to_word.py` | 重构排版逻辑（真 TOC 域/分页/三线表/页码/图片自适应/重复标题去重） |

**波及确认（不改动，仅回归验证）**——ChartGenerator/ChartConfig 的其他消费者在换肤后自动受益，需冒烟确认不挂：
`src/services/smart_chart_generator.py`、`src/core/orchestrator/orchestrator.py`、`src/core/orchestrator/output/document_generator.py`、`src/core/agents/generic_agent.py`、`src/converters/html_to_ppt.py`（PPT 图一并换肤）、`src/services/stock_charting.py`、`src/survey/analysis/report_builder.py`、`src/agents/fixed_agents/survey_analysis_agent.py`、`tests/unit/test_chart_sidecar.py`、`tests/unit/services/test_chart_production_edge_cases.py`、`tests/unit/report_upgrade/test_chart_attachment.py`、`tests/unit/test_report_integrity_regressions.py`、`tests/unit/converters/test_html_to_word.py`。
