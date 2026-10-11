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
| 7 | 纸张 US Letter，边距 1.25in | 全文 |
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
DPI=200；宽幅图 9×5.2；方形图（饼/雷达）8×4.8
```

### 4.2 公共布局引擎（十类渲染器共用）

1. **标题区重构**：废弃"居中 title + `ax.text(0,1.02)` 副标题"混排，改为 fig 级左对齐标题块：标题行 + 副标题行 + 金色短下划线，预留固定头部空间。
2. **防裁切 `_auto_margins()`**：纵向上界扩至 `max×1.15`；横向条形图右界扩至 `max×1.12`；数值标签永不越界。
3. **数字格式 `_format_value()`**：全图单一规则——≥1万→`x.x万`；≥1000→千分位 `1,234`；≥1→一位小数；<1→两位小数；`%`→一位小数。
4. **来源注规范化**：左下角 `资料来源：…`，右下角 `单位：…`；source 命中 `{"content", "Public data compilation"}` 字面量时走兜底链。
5. **DPI 150→200**。

### 4.3 各图型规则

| 图型 | 升级点 |
|------|--------|
| bar | 关键柱金色强调，其余藏青；关键柱判定：类目为时间序列时取最新期，否则取最大值 |
| hbar | 长条数值标签条内右端白字，短条条外深灰 |
| pie | 改环形图 donut + 右侧图例带数值，中心放合计；8×4.8 画布消灭留白 |
| bar_line | 折线只标注首末两点数值；柱标签移柱内顶部白字；图例横排标题下 |
| line | 去图例框，系列名直接标注在线端 |
| radar | 副标题移出极坐标区；类目标签加大 pad |
| scatter/bubble/waterfall/quadrant | 同步套用主题令牌与公共布局 |

## 5. 规划层修复

### 5.1 source 泄漏修复

`document_generation_agent.py:1406`：`source=plan.subtitle or ...` 改为 `source=plan.data_source or ...`；渲染入口过滤字面量，兜底链：`plan.data_source` → 数据请求机构来源 → `"公开资料整理"`。

### 5.2 chart_planner 提示词升级

1. **口径一致性硬约束**：季度值与累计值禁止同图混排；确需对比时分组呈现并在 subtitle 显式标注各期口径。
2. **新增输出字段 `source`**：规划器为每张图输出真实机构来源。
3. **选型规则强化**：趋势→line/bar_line；构成→donut（≤6）/hbar；对比→bar；相关→scatter；多维权衡→radar/quadrant，附一句话理由。
4. **subtitle/caption 分工**：subtitle 只放口径与单位说明；caption 只放注释。

### 5.3 软校验

`_validate_config` 检测 categories 同时出现季度与累计口径模式时记 warning（不阻断，供质量检查 Agent 消费）。

## 6. Word 排版系统（`html_to_word.py` 重构 + 新增 `word_styles.py`）

### 6.1 页面

A4（21×29.7cm）；边距上下 2.54cm、左右 3.17cm（可用宽约 14.7cm）。

### 6.2 正文（券商研报规范）

| 元素 | 规格 |
|------|------|
| 正文 | 宋体 10.5pt（五号），行距固定 22pt，首行缩进 2 字符，两端对齐 |
| H1 | 黑体 16pt 加粗藏青 #1A2744，段前分页，段后 18pt，底部 1pt 藏青横线 |
| H2 | 黑体 14pt 加粗藏青，段前 12pt 段后 6pt |
| H3 / H4 | 黑体 12pt / 宋体加粗 11pt |
| 重复标题 | H2 文本与前一个 H1 去编号后相同则跳过 |

### 6.3 目录与页码

- 真 TOC 域 `TOC \o "1-3" \h \z \u`；`settings.xml` 写入 `updateFields=true`，打开时自动刷新页码。
- 页眉：左 "ZENSERS" + 右报告标题，8pt，段落底边框 0.5pt 藏青横线。
- 页脚：居中 "第 X 页 共 Y 页"（PAGE/NUMPAGES 域），版权行缩小置于其下。

### 6.4 图表与表格

- 图片：宽度 = `min(14.7cm, 像素宽/200dpi)`，居中；方形图限宽 11cm；图片段落 keep_with_next 绑定下方注释。
- 表格：三线表（上下 1pt 藏青粗线 + 表头下 0.5pt 细线，去竖线）；表头浅藏青底 `#E8EDF4` 深字加粗 9.5pt；跨页重复表头（`tblHeader`）；数据行 9pt。
- 图表编号：图片上方"图表 N：{图题}"（黑体 9pt 藏青），全文连续计数；图下注释 8.5pt 灰居中。

### 6.5 封面与尾页

封面保留文字结构：金色分隔线改 2.25pt 实线段落边框，元信息区浅灰底色块。免责声明页维持独立分页。

## 7. 错误处理

- 单图渲染失败降级为占位文字并记日志，不阻断报告（保留现有行为）。
- Word 转换沿用原子保存。

## 8. 测试与验收

1. 单测：`_format_value`、`_auto_margins`、source 过滤、TOC 域存在性、分页符、表格三线样式与 `tblHeader`、页脚页码域、重复标题跳过。
2. 冒烟：10 类图型渲染无异常 + 输出尺寸校验（Pillow）。
3. 视觉回归：用 humanoid_robot 样张数据重渲全部 23 张图 + 重建 docx，人工比对验收。

## 9. 涉及文件

| 文件 | 动作 |
|------|------|
| `src/services/chart_theme.py` | 新增 |
| `src/services/chart_generator.py` | 重构渲染器 |
| `src/services/chart_planner.py` | 提示词升级 + source 字段 |
| `src/agents/fixed_agents/document_generation_agent.py` | source 透传修复 |
| `src/converters/word_styles.py` | 新增 |
| `src/converters/html_to_word.py` | 重构排版逻辑 |
| `tests/` | 新增/更新对应测试 |
