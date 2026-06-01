# Claude HTML 生成技术方案调研报告

## 一、当前系统诊断

### 1.1 核心问题定位

| 问题维度 | 现状 | 问题等级 |
|---------|------|---------|
| **CSS 设计** | 传统中文印刷风格(SimSun/SimHei)，无CSS变量，无渐变，无毛玻璃效果 | P0 |
| **图表集成** | 图表生成后存为PNG文件，但**从未被嵌入HTML** - ContentOrchestrator只处理文本，无图表注入通道 | P0 |
| **字体策略** | 仅支持中文字体，无现代Web字体(Inter/JetBrains Mono等) | P1 |
| **响应式** | 无 `@media screen` / `@media print` 分段 | P1 |
| **动画/交互** | 零动画，零微交互 | P2 |
| **模板引擎** | 自建简单替换引擎，无Jinja2继承能力 | P2 |
| **色彩体系** | 单一navy blue+g老gold传统配色 | P1 |

### 1.2 图表管线断裂（最关键问题）

```
SmartChartGenerator → 生成图表PNG → 存到 output/charts/  → ❌ 从未注入HTML
                                                                       ↓
ContentOrchestrator → 只处理 section.content (纯文本) → 模板 {{ section.content }}
                                                                       ↓
                                                            HTML最终不含任何图表
```

`smart_chart_generator.py` 生成了图表但结果没有被 `content_orchestrator.py` 消费。`ContentOrchestrator.transform_to_html()` 的入参 `research_result` 中虽然有 `sections[].content`, `sections[].data_points`, `sections[].tables`，但没有 `sections[].charts` 字段。

---

## 二、Claude 的核心技术方案

### 2.1 Anthropic 的「前端美学」技巧

Anthropic 公开了一个约 400 token 的提示词来引导 Claude 生成高质量 HTML：

```
<frontend_aesthetics>
Focus on:
- Typography: Choose fonts that are beautiful, unique, and interesting.
  Avoid generic fonts like Arial and Inter.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency.
  Dominant colors with sharp accents outperform timid, evenly-distributed palettes.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions.
  Focus on high-impact moments: one well-orchestrated page load with staggered reveals.
- Backgrounds: Create atmosphere and depth rather than defaulting to solid colors.
  Layer CSS gradients, use geometric patterns.
</frontend_aesthetics>
```

**核心原则**：以「适当的高度」提示 —— 既不要硬编码(如 `#4F46E5`)，也不要过于模糊(如"让它更好看")。

### 2.2 Claude 的 HTML 生成演进路线

```
默认HTML (AI slop美学)
  ↓ Inter字体 + 紫色渐变 + 白底 + 扁平设计
  ↓
前端美学技能 (~400 token 提示词)
  ↓ 独特字体 + 统一色彩 + 动画 + 层次感
  ↓
web-artifacts-builder 技能
  ↓ React + Tailwind CSS + shadcn/ui + Parcel 打包
  ↓
Claude Design (2026年4月)
  ↓ 读取代码库设计系统 → 导出到 Canva/PDF/PPTX/HTML
```

### 2.3 图表的三种实现路线

| 方案 | Claude方案 | 适用场景 |
|------|-----------|---------|
| **Inline HTML/CSS/JS** | Claude自主生成交互式图表(2026年3月) | 对话内的临时可视化 |
| **matplotlib SVG** | 服务端渲染，嵌入HTML | **推荐用于AI报告的静态图表** |
| **MCP Apps** | Hex, Amplitude等专业工具 | 需要交互分析的数据 |

---

## 三、技术改进方案

### 3.1 图表管线修复（最高优先级）

需要在 `research_result` 的 section 数据结构中增加 `charts` 字段，并在 ContentOrchestrator 中集成：

```python
# 新增数据流
research_result.sections[].charts = [
  {"type": "bar", "svg": "<svg>...</svg>", "caption": "..."},
  {"type": "pie", "base64": "data:image/png;base64,...", "caption": "..."}
]
```

**推荐使用 SVG 方式**（而非 PNG）：
- `matplotlib` 原生支持 `fig.savefig(buf, format='svg')`
- SVG 无限缩放，适合打印
- SVG 直接在 HTML 中嵌入，无需 base64 编码
- SVG 可通过 CSS 控制样式

### 3.2 HTML 模板现代化改造

当前模板需要以下改造：

1. **CSS 变量体系**
2. **KPI 指标卡片组件**
3. **图表容器组件**
4. **响应式布局**
5. **屏幕/打印双模支持**
6. **现代字体栈**
7. **卡片式布局**
8. **渐变/层次感背景**

### 3.3 分层优化方案

#### P0（必须立即修复）
- 修复图表管线：SmartChartGenerator → ContentOrchestrator 打通
- 将图表输出从 PNG 切换到 SVG 格式
- 在模板中增加 chart-container 组件

#### P1（短期改进）
- CSS 全面现代化：变量体系 + 卡片布局 + 渐变背景 + 现代字体
- 增加 `@media screen` / `@media print` 分段
- 增加 KPI 卡片组件
- 字体策略：Inter + 中文字体回退

#### P2（中期规划）
- 微交互动画（CSS-only）
- 交互式 Plotly 图表（可选叠加）
- 响应式布局
- 模板继承体系

---

## 四、对比总结

| 维度 | 当前系统 | Claude方案 | 目标方案 |
|------|---------|-----------|---------|
| 图表格式 | PNG文件引用 | SVG内联/HTML+CSS+JS | **SVG内联嵌入HTML** |
| 图表管线 | 生成后未消费 | N/A | **图表生成→注入HTML→模板渲染** |
| CSS设计 | 传统印刷风格 | 现代前端美学 | **CSS变量+卡片+渐变** |
| 字体 | SimSun/SimHei | Inter/独特字体 | **Inter + 独特字体组合** |
| 动画 | 无 | 交错显示/微交互 | **CSS-only交错动画** |
| 打印支持 | 部分@page | 完整@media支持 | **媒体查询双模式** |
| 模板引擎 | 自建简单替换 | Jinja2继承 | **Jinja2+组件模式** |
| 响应式 | 无 | 自适应 | **移动端+桌面+打印** |

## 五、关键参考资料

1. https://claude.com/blog/improving-frontend-design-through-skills
2. https://claude.com/blog/claude-builds-visuals
3. https://matplotlib.org/stable/api/backend_svg_api.html
4. https://www.print-css.rocks/
