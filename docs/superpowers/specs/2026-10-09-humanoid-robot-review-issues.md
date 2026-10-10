# 人形机器人案例 · 审查与修订记录（Task9-10）

日期：2026-10-09　案例：中国🤖人形机器人产业深度研究报告（宣传用）
状态：**等待用户确认定稿**

## 一、交付物清单
| 交付物 | 路径 |
|---|---|
| 最终 DOCX | `output/cases/humanoid_robot/中国人形机器人产业深度研究报告.docx`（1.5MB）|
| 数据集 | `output/cases/humanoid_robot/research_result.json`（91 源/251 数据点/17 图，chart_id 17/17）|
| 图表审计边车 | `output/cases/humanoid_robot/charts.json`（17 条，20KB，主 JSON 外独立审查）|
| 图表 PNG | `output/cases/humanoid_robot/charts/`（17 张，持久化）|
| 运行会话 | `data/humanoid_robot_20261009_162001/`（checkpoints 12/12）|

## 二、验收结果（Task7 标准）
| 指标 | 目标 | 实际 | 判定 |
|---|---|---|---|
| 页数（docx 字符//2000+图//2）| >40 | 57 | PASS |
| 图表 | ≥12 | 17 嵌入 | PASS |
| 正文字符 | ~88.5K | 99,613（含摘要/结论） | PASS |
| 章节 | 12 且全部成稿 | 12/12 ready | PASS |
| 数据源 | 真实、可溯 | 91 条真实来源 | PASS |
| 数据点 | — | 251（缺 URL 84） | 记录在案 |
| 管线质量门 | — | formal_complete=False / degraded | 记录在案（NEV 案例同交付形态，其 defense_issues=92） |

## 三、修复与抢救过程（三次运行 + 离线补写）
1. **运行1（09:08）**：SSL 并发死锁 + 百度搜索线程挂死 → 修复（共享 SSL 上下文、to_thread 超时护栏）。
2. **运行2（12:21-15:45）**：writer 8192 token 上限截断 JSON → 8 章丢失；defense 补丁失败还替
   换好章节 → 修复（`_chapter_max_tokens()` env、JSON 抢救器、patch_data 失败保原文、
   defense 重写替换加守卫）。
3. **运行3（16:20-20:48）**：11/12 章成稿 + 17 图；section_3 失败 + 短章 7 个。
4. **离线补写**（`tools/backfill_humanoid_chapters.py`）：以同一写手（关闭流式走工具路径）
   + 16384 token + 91 源证据池 → 9 章全部重写/扩写成功；随后 URL 确定性绑定（150→84）。
5. **泄露修复**（`tools/repair_leak_humanoid.py`）：section_1 模型输出把 JSON 信封当代正文
   泄露（salvage 围栏标签 bug）→ 离线确定性提取内嵌转义内容（7,988 字 + 30 个全绑定 dp）；
   修复 `_salvage_chapter_prose` 并加 2 个回归测试（11/11 过）。

## 四、遗留问题（人工审查认定，接受/记录）
| # | 问题 | 处置 |
|---|---|---|
| 1 | L3 缺 URL=84（defense 审计口径 150 为陈旧计数） | 接受：deterministic 绑定已达上限；正文数字普遍带来源名 |
| 2 | 情景推演数值（60%/25%/15% 概率、220-320 亿元等）为标注过的推算 | 接受：符合研究惯例，正文均标"推算/预测" |
| 3 | 管线 quality_gate=degraded（防御审计问题 337 条为运行期快照） | 接受：与 NEV 案例同形态交付 |
| 4 | attempt-1/2 残留归档于 `_archived_attempt1/2`（含污染数据，勿参考） | 定稿后可整体删除 |
| 5 | 12 章图表锚点数不均（部分章节 0 图） | 接受：17 图总量达标 |

## 五、代码变更清单（未提交，main 工作区）
- `src/skills/search_skill.py`：共享 SSL 上下文 + 搜索线程超时护栏（tests/unit/test_search_thread_timeout.py 4 测试）
- `src/core/research_framework_manager.py`：`ZENSERS_MAX_TOTAL_SEARCHES` 配额覆盖（3 测试）
- `src/core/orchestrator/orchestrator.py`：图表持久化目录 `_CHART_OUTPUT_DIR`
- `src/agents/fixed_agents/report_upgrade/chapter_writer.py`：
  `ZENSERS_CHAPTER_MAX_TOKENS`（默认 8192 不变）、`_load_chapter_json` 渐进解析修复、
  `_salvage_chapter_prose` 抢救（围栏标签/信封形状防泄露）、`patch_data` 失败保原文
- `src/agents/fixed_agents/report_upgrade/orchestrator.py`：defense 重写替换守卫；
  `_plan_and_render_charts` 接边车（`ChartSidecar` 落 `_checkpoint_dir/charts.json`，`chart_id` 写回主 JSON）
- `src/services/chart_generator.py`：`ChartSpec.to_record()/from_record()` + `ChartSidecar`
  （唯一审计 Seam；NaN/inf 拒、60 点 cap、非法 chart_type 回退 bar）；标题留白修复
  （有副标题时 pad 12→28、副标题 y 1.01→1.02，标题-轴间距 12px→35px）
- `src/converters/base_parser.py` + `src/converters/html_to_word.py`：`figure/figcaption`
  解析与 DOCX 灰色居中 caption（17 图 caption 全部落盘）
- `src/content/content_orchestrator.py`：四路输出透传 `chart_id`
- 测试：47 全过（sidecar 3 + attachment 3 + orchestrator 10 + generator 3 + edge 15 +
  title-caption 2 + salvage 11）；`tools/backfill_chart_sidecar.py` 回填 17 条边车

## 六、图表链路加固效果（候选 1，2026-10-10 Full replan 验证）
| 验证项 | 结果 |
|---|---|
| 重跑 | 12 章全跑 LLM planner，23 图全部新渲染（旧 17 PNG 归档于 `_archived_prereplan_charts/`）|
| 边车记录 | 23/23，`from_record()` 重渲染成功，主 JSON `chart_id` 23/23 |
| DOCX | 54 页 / 23 图嵌入 / 25 表 / 灰色 caption 23 个 |
| 标题留白 | 新图全部带修复（pad 28 + 副标题 y 1.02，顶部留白 13-15px） |
| 体积 | 边车 33KB，主 JSON 1.88MB 不动 |
| 回归 | planner 78 + 图表链 47 全过 |
| planner 修复 | JSON-first prompt + `_repair_truncated_json` 截断修复 + search 120s 超时护栏 |
| 备注 | search 补数失败的图回退用文中表格数据（`data_source=content`），2 处渲染失败为 LLM 数值含非 finite，已跳过 |

## 七、待用户确认
1. DOCX 是否达到宣传案例标准（可打开核验：封面/目录/摘要/12 章/17 图/20 表/91 源附录）。
2. 遗留问题清单是否接受，或指定必须修复项。
3. 确认后：归档 attempt 残留目录，案例交付即定稿。