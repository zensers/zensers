# 人形机器人产业报告案例总结：从框架设计到交付定稿

> 案例：`output/cases/humanoid_robot/` —— 中国人形机器人产业深度研究报告
> 成果：DOCX 55页 / 23图 / 25表 / 88065字 / 91源 / 12章
> 目标读者：后续批量生成行业案例的执行者

---

## 一、框架设计：三层分离

系统采用「研究—编排—转换」三层分离，主链路 6 步：

```
框架设计 → 研究执行 → 聚合质检 → 内容编排 → 图表归档 → 转换落盘
```

| 层 | 核心模块 | 职责一句话 | 关键文件 |
|---|---|---|---|
| 研究层 | `ResearchOrchestrator` | 全链路总控：分解→建Agent→并行执行→聚合→落盘 | `src/core/orchestrator/orchestrator.py` |
| 研究层 | `ChartPlanner` | 只决策"成不成图/何种图/插哪/数据何来"，不渲染 | `src/services/chart_planner.py` |
| 研究层 | `ChartGenerator` + `ChartSidecar` | matplotlib渲染PNG；边车`charts.json`存完整规格，主JSON只留轻引用 | `src/services/chart_generator.py` |
| 编排层 | `ContentOrchestrator` → `TemplateEngine` | sections转中间HTML，套模板渲染 | `src/content/content_orchestrator.py` |
| 转换层 | `HTMLToWordConverter`（base_parser + css_extractor + python-docx） | HTML/CSS解析落盘DOCX | `src/converters/html_to_word.py` |

三类配置在链路中的作用：

| 配置 | 代表文件 | 作用 |
|---|---|---|
| `config/` | `research_frameworks.yaml`、`templates/industry_report.yaml` | 资源配额（搜索次数/分析深度/最小章节长度）+ 12种报告章节骨架 |
| `prompts/` | `tasks/`、`phases/`、`agents/`、`_shared/` | 章节Agent行为约束：排版、图表、引用、数据一致性、去重 |
| `templates/` | `professional_report.html`（德勤咨询风母版） | 终版式：`{{title/toc_items/content}}`占位 + 锚点插`<figure class="chart-block">` |

人形案例定制了两脚本（通用链路走`DocumentGenerator`，人形走直连以便调试）：

| 脚本 | 输入 | 输出 |
|---|---|---|
| `tools/run_humanoid_robot_case.py`（研究段） | 硬编码TOPIC + 12章aspects + `ZENSERS_MAX_TOTAL_SEARCHES=60` + 真LLM/真搜索 | `research_result.json`（sections/charts/sources/key_findings） |
| `tools/render_humanoid_case_docx.py`（渲染段） | research_result.json + 模板 + 图表PNG | `report.html` + `charts/*.png` + `中国人形机器人产业深度研究报告.docx` |

---

## 二、报告生成：Full Replan 全量跑通

研究执行阶段曾两次失败并归档现场，这是批量生产必须预期的成本：

| 尝试 | 现象 | 根因 | 修复（已进代码库） |
|---|---|---|---|
| 运行1（09:08） | SSL并发死锁 + 搜索线程挂死 | 共享SSL上下文竞争 | 修共享SSL上下文 + 搜索线程超时护栏 |
| 运行2（12:21） | JSON截断、8章丢失 | 章节token上限 + 粗暴补丁破坏原文 | `ZENSERS_CHAPTER_MAX_TOKENS` env + 渐进JSON解析 + `patch_data`失败保原文 + defense替换守卫 |
| 运行3（16:20） | 11/12章成稿 | 9章偏短/失败 | 同写手16384 token离线重写 + 确定性URL绑定（缺URL 150→84） |

图表采用 **Full Replan** 策略：12章全跑LLM planner重规划，而非只补缺图。决策依据是"更新图片不是内容"——重渲染不触碰正文，风险低而一致性收益高：

- `ChartSidecar`：完整`ChartSpec`存`charts.json`（23/23条），主JSON只留`{chart_id, path, title, anchor}`
- `tools/rerender_charts_from_sidecar.py`：无LLM纯重渲染，`ok=23 fail=0 copied=23`
- 旧图归档`_archived_prereplan_charts/`，可回滚

---

## 三、优化迭代：四轮精修

### 第1轮：图表标题防重叠（量化验证）

现象：图表标题/注释与坐标轴文字重叠。
修复（`chart_generator.py`）：`fig.text y 0.01→0.02` + `subplots_adjust bottom≥0.20` + `wrap=True` + `savefig pad_inches 0.25`。
验证：`tick_bottom 49.39 > footer_top 20.0 overlap False`，回归17项通过。

### 第2轮：HTML图表居中卡片

模板CSS：`.document max-width:860px`，`figure.chart-block`居中卡片760px，标题-轴间距12px→35px后二次渲染。

### 第3轮：目录页恢复（根因最深的一轮）

现象：目录12条全丢，转换后93条全是正文。
三层根因：

1. **解析器丢文本**：`base_parser`遇到`span`建边界切碎文本，`_end_element`只取最后1个text节点 → span透传 + while全取，恢复12/12
2. **类名错配**：渲染输出`toc-item`，转换器只认`div class==toc` → 渲染改输出`toc-item-level1/level2` + `toc-num/title/dots/page`四段式
3. **CSS类名冲突**：`.toc-page`同时命中容器div和页码span → 限定为`div.toc-page`

转换器新增`_add_toc_item`：点线制表位右对齐（`WD_TAB_LEADER.DOTS` + RIGHT tab at 430pt），一级加粗藏青、二级缩进灰字。

### 第4轮：目录行距手感

`14px/8px → 6px/3px → 8px/5px`两调，最终：HTML `line-height 1.6`、DOCX段前/后2pt + 1.15倍行距。54条目录（12一级+42二级）收紧到位。

---

## 四、批量生产手册：新案例5步

```bash
# 1. 定题：复制研究脚本，改TOPIC + CHAPTERS（12章左右）
cp tools/run_humanoid_robot_case.py tools/run_<新案例>_case.py

# 2. 跑研究（真LLM+真搜索，配额60起）
venv\Scripts\python.exe tools/run_<新案例>_case.py
# 产物：output/cases/<新案例>/research_result.json

# 3. 图表边车回填 + 重渲染（如有缺图/重叠）
venv\Scripts\python.exe tools/backfill_chart_sidecar.py   # 反推ChartSpec
venv\Scripts\python.exe tools/rerender_charts_from_sidecar.py  # ok=23 fail=0 为准

# 4. 渲染终稿
venv\Scripts\python.exe tools/render_humanoid_case_docx.py  # 或复制改路径
# 产物：report.html + charts/*.png + *.docx

# 5. 验收（以自检为准，conv.pages_estimate为噪声）
# 页数>40 PASS | 图>=12 PASS | L3缺URL=0 | formal_complete
```

回归基线（改动转换器/模板/图表任一处必跑）：

```bash
venv\Scripts\python.exe -m pytest tests/unit/test_chart_sidecar.py \
  tests/unit/test_chart_title_caption_regression.py \
  tests/unit/report_upgrade/test_chart_attachment.py \
  tests/unit/services/test_chart_production_edge_cases.py \
  tests/unit/test_chapter_writer_salvage.py -q
# 期望：34 passed
```

---

## 五、已知坑位速查

| 坑 | 症状 | 对策 |
|---|---|---|
| Windows非ASCII路径 | `CommandNotFoundException` / `gbk`编码错 | 全用`venv\Scripts\python.exe` + 临时脚本文件，避免`-c`内联中文 |
| PowerShell无`head`/`\|\|` | 命令失败 | 用`; if ($?) {}`串联，或分步执行 |
| 验收页数噪声 | `conv.pages_estimate`偏小 | 以`字符//2000+图//2`自检为准 |
| L3缺URL | `formal_complete=False/degraded` | 已知接受项（达搜索绑定上限），不阻塞交付 |
| 搜索补数失败 | `Search data unavailable` | 失败图回退`data_source=content`，用正文数值成图 |
| 临时调试脚本残留 | tools/下`check_*_tmp.py`堆积 | 定稿后`Remove-Item`清理 |
| 人形改动未提交 | git log止于09-28 | 批量前先commit当前11文件修改+20余脚本/测试 |

---

## 六、交付物清单

```
output/cases/humanoid_robot/
├── research_result.json          # 主数据 1.88MB，12 sections / 23图 / 91源
├── charts.json                   # 边车 23条 33KB
├── charts/                       # 现23 PNG（归档：_archived_prereplan_charts/、_archived_overlap_fix_charts/）
├── report.html                   # 中间HTML 303KB
├── 中国人形机器人产业深度研究报告.docx  # 终稿 55页/23图/25表/88065字
└── run.log / backfill.log        # 运行日志
docs/superpowers/specs/
├── 2026-10-09-humanoid-robot-case-design.md   # 设计定稿
└── 2026-10-09-humanoid-robot-review-issues.md # 审查记录（含第六节更新）
```
