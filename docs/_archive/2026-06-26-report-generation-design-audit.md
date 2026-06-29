# 报告生成升级方案 — 设计审计报告

> 日期：2026-06-26
> 审计对象：`docs/2026-06-26-report-generation-agent-upgrade-design.md`
> 审计方法：逐组件数据流追踪 + 边界条件推演 + 失败模式分析

---

## 审计结论

共发现 **9个缺陷**，其中 **致命级3个、严重级4个、中等级2个**。3个致命缺陷若不修复，将直接导致报告生成失败或质量低于现有水平。

| 等级 | 数量 | 核心问题 |
|------|------|----------|
| 致命 | 3 | DataRegistry与LLM之间无法交互；patch_data破坏审查结果；全局审查token爆炸 |
| 严重 | 4 | data_points_used自报不可靠；preceding_summary过期；rewrite质量退化；框架-数据映射缺失 |
| 中等 | 2 | 来源权威性表不完整；中间状态无持久化 |

---

## 缺陷 1【致命】DataRegistry 是 Python 对象，LLM 无法查询

**位置**：3.1 ChapterWriteInput.data_registry、3.2 ChapterReviewInput.data_registry、3.3 ReviewInput.data_registry

**问题**：

设计将 `DataRegistry` 作为 Python 对象传入多个 Agent 的输入数据类。但这些 Agent 都是 LLM——LLM 无法调用 Python 方法。具体后果：

1. **ChapterWriter** 的 Prompt 写着"使用数据注册表中尚未使用的数据点"——但 LLM 看不到注册表内容，无法知道哪些数据已被使用
2. **ChapterReviewAgent** 的 Prompt 写着"数据是否与数据注册表中的已有值矛盾"——同样看不到注册表
3. **GlobalReviewAgent** 收到 DataRegistry 对象，无法做任何数据一致性检查

**这意味着 DataRegistry 的核心功能——防止数据重复引用和冲突检测——在设计层面就是失效的。**

**根因**：混淆了"系统组件的数据传递"和"LLM Prompt的上下文注入"。DataRegistry 的数据必须在调用 LLM 之前序列化为文本，注入到 Prompt 中。

**修正**：

```python
@dataclass
class ChapterWriteInput:
    framework: ResearchFramework
    chapter_spec: FrameworkDimension
    chapter_data: Dict[str, Any]
    preceding_summary: str
    used_metrics_summary: str                # 替代 data_registry: DataRegistry
```

其中 `used_metrics_summary` 由 ReportOrchestrator 在调用 Writer 之前从 DataRegistry 序列化生成：

```python
def _serialize_used_metrics(self, data_registry: DataRegistry) -> str:
    """将 DataRegistry 中已使用的数据点序列化为 Prompt 文本"""
    if not data_registry._metrics:
        return "暂无已使用的数据指标。"
    lines = []
    for key, entry in data_registry._metrics.items():
        conflict_mark = " ⚠️存在冲突" if entry.conflicts else ""
        lines.append(f"- {entry.metric}: {entry.value} {entry.unit}（来源: {entry.source}）{conflict_mark}")
    return "\n".join(lines)
```

Prompt 中替换为：

```markdown
## 已使用的数据指标（避免重复引用，如有冲突请标注）
{used_metrics_summary}
```

此修正适用于所有需要 DataRegistry 的 Agent 输入。

---

## 缺陷 2【致命】Phase 4 的 patch_data 破坏了 Phase 2 的审查结果

**位置**：3.5 ReportOrchestrator 流程、3.6.3 _apply_data_repairs

**问题**：

当前流程：

```
Phase 2: 逐章撰写 → 章节审查通过 ✅
Phase 3: 全局审查 → 发现数据问题
Phase 4: patch_data 修改章节内容 → ❌ 修改后的章节未经审查
```

patch_data 用 LLM 修改了章节中的数据段落，但：
1. 修改后的章节**没有再经过 ChapterReviewAgent 审查**——可能引入新的逻辑错误
2. 修改可能改变了章节的 key_conclusions——但后续章节的 preceding_summary 是基于旧版 key_conclusions 生成的
3. 如果多个章节都被 patch_data 修改，章节间可能产生新的数据矛盾（patch 是逐章独立进行的，不知道其他章的 patch 内容）

**更严重的是**：patch_data 本质上是一次 LLM 调用，LLM 无法保证"只修改数据段落，不改动其他内容"。实际执行中，LLM 很可能重写整个段落甚至整个章节。

**修正**：

Phase 4 修补后，必须对被修改的章节重新执行 ChapterReviewAgent 审查：

```python
async def _phase4_fix_and_optimize(self, chapters, review, framework, topic):
    # ... 数据修补 + 冲突解决 + 回写 ...
    
    # 关键：修补后的章节必须重新审查
    patched_chapter_ids = set(chapter_updates.keys())
    for i, chapter in enumerate(chapters):
        if chapter.chapter_id not in patched_chapter_ids:
            continue
        
        re_review = await self._chapter_reviewer.review(
            ChapterReviewInput(
                framework=framework,
                chapter_spec=...,  # 从 framework 中找到对应的 dimension
                chapter_content=chapter.content,
                preceding_summary=...,  # 用更新后的 preceding_summary
                used_metrics_summary=self._serialize_used_metrics(self._data_registry),
                writer_self_check_issues=[],
            )
        )
        
        if not re_review.passed:
            # 修补引入了新问题，用 Writer 再修一次
            chapter = await self._chapter_writer.rewrite(
                original_chapter=chapter,
                review_feedback=re_review,
                ...
            )
            chapters[i] = chapter
    
    # 修补后 preceding_summary 也需要更新
    preceding_summary = self._rebuild_preceding_summary(chapters)
    
    return chapters
```

同时，patch_data 的 Prompt 需要更严格的约束：

```markdown
## 修补要求
1. 只修改涉及上述数据的句子，逐句替换，不要重写段落
2. 替换格式：将"旧数值 旧单位"替换为"新数值 新单位"，其他文字不变
3. 如果原文是"市场规模约为2000亿元"，只能改为"市场规模约为2180亿元"，不能改写为其他表述
4. 不要改动与数据无关的任何内容
5. 修补后输出完整章节内容，标注哪些行做了修改
```

---

## 缺陷 3【致命】GlobalReviewAgent 接收完整报告，token 爆炸

**位置**：3.3 GlobalReviewAgent、3.5 ReportOrchestrator Phase 3

**问题**：

GlobalReviewAgent 的 Prompt 将 `{full_report_content}` 一次性传入。假设报告有 10 章，每章 2000 字，就是 20,000 字 ≈ 27,000 tokens。加上框架、审查指令等，总 Prompt 可能超过 35,000 tokens。

后果：
- 超出 GPT-4o-mini 的 128K 输入窗口时不会报错，但**注意力稀释**：LLM 在超长上下文中会遗漏关键问题
- 单次调用成本极高（输入 35K tokens × $5/M ≈ $0.175/次，若用 GPT-4o 更贵）
- 如果报告更长（15+章），可能超出小模型的有效处理范围

**修正**：

全局审查不应传入完整报告原文，而是传入**结构化摘要**——每章的标题、核心结论、关键数据点、与前文的衔接关系：

```python
def _serialize_report_for_review(self, chapters, data_registry) -> str:
    """将完整报告序列化为全局审查用的紧凑摘要"""
    sections_summary = []
    for i, ch in enumerate(chapters):
        # 提取关键数据点（而非全文）
        data_summary = []
        for dp in ch.data_points_used:
            data_summary.append(f"  {dp.metric}: {dp.value} {dp.unit}")
        
        sections_summary.append(
            f"### 第{i+1}章：{ch.title}\n"
            f"核心结论：{'; '.join(ch.key_conclusions)}\n"
            f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
        )
    
    # DataRegistry 冲突摘要
    conflicts = data_registry.get_conflicts()
    conflict_summary = ""
    if conflicts:
        conflict_summary = "\n## ⚠️ 已知数据冲突\n" + "\n".join(
            f"- {c.metric}: {c.description}" for c in conflicts
        )
    
    return "\n\n".join(sections_summary) + conflict_summary
```

这样 10 章报告的摘要约 2000-3000 字（而非 20,000 字），全局审查的 Prompt 总量控制在 5000 tokens 以内。

**但需注意**：结构化摘要会丢失细节。因此全局审查分为两步：

```
Step 1: 全局摘要审查（发现跨章节问题）
  输入：结构化摘要（紧凑）
  输出：问题列表（定位到具体章节和指标）

Step 2: 问题验证（对发现的问题，读原文确认）
  输入：仅问题涉及章节的原文（局部）
  输出：确认/否定 + 精确的问题描述和修正建议
```

---

## 缺陷 4【严重】data_points_used 由 LLM 自报，不可靠

**位置**：3.1 ChapterWriteOutput.data_points_used

**问题**：

ChapterWriter 输出中 `data_points_used` 是 LLM 自报的"我使用了哪些数据点"。但 LLM 在自报数据时存在严重问题：

1. **遗漏**：LLM 使用了某个数据但忘记在 data_points_used 中列出 → DataRegistry 漏注册 → 后续章节可能重复引用同一数据
2. **幻觉**：LLM 列出了一个实际没有使用的数据点 → DataRegistry 误注册 → 后续章节被错误地阻止使用该数据
3. **数值错误**：LLM 在 data_points_used 中记录的数值与正文中的数值不一致 → DataRegistry 记录了错误值 → 冲突检测误报

**修正**：

不完全依赖 LLM 自报，增加**后置提取**环节——从生成的 Markdown 内容中用正则/LLM提取数据点，与自报数据交叉验证：

```python
async def _extract_and_validate_data_points(self, chapter: ChapterWriteOutput) -> List[DataPoint]:
    """从章节内容中提取数据点，与 LLM 自报数据交叉验证"""
    
    # 方法1：正则提取（快速，但不理解语义）
    regex_extracted = self._extract_data_points_by_regex(chapter.content)
    
    # 方法2：LLM 自报（理解语义，但不可靠）
    reported = chapter.data_points_used
    
    # 交叉验证：取两者交集，补充正则遗漏
    validated = []
    reported_metrics = {dp.metric.lower(): dp for dp in reported}
    
    for dp in regex_extracted:
        key = dp.metric.lower()
        if key in reported_metrics:
            # 正则和自报都提到 → 高置信度
            reported_dp = reported_metrics[key]
            if dp.value != reported_dp.value:
                # 数值不一致 → 以正文中实际出现的为准
                logger.warning(f"Data point value mismatch for '{dp.metric}': "
                             f"content says {dp.value}, reported says {reported_dp.value}")
            validated.append(DataPoint(
                metric=dp.metric,
                value=dp.value,        # 以正文中实际出现的值为准
                unit=dp.unit,
                source=reported_dp.source or dp.source,
            ))
        else:
            # 正则找到但自报没提 → 可能是遗漏
            validated.append(dp)
    
    return validated
```

---

## 缺陷 5【严重】preceding_summary 在 patch_data/rewrite 后过期

**位置**：3.5 ReportOrchestrator preceding_summary 构建

**问题**：

`preceding_summary` 由各章的 `key_conclusions` 拼接而成。但如果后续章节被 patch_data 修改或 rewrite，key_conclusions 可能改变，preceding_summary 就过期了。

举例：
1. 第3章审查通过，key_conclusions = ["市场规模2180亿元"]
2. 第4-8章基于这个 preceding_summary 撰写，都引用了"2180亿元"
3. 全局审查发现第1章和第3章数据冲突，patch_data 将第3章改为"2000亿元"
4. 但第4-8章的 preceding_summary 仍然记录"2180亿元"——这些章节没有重写

**修正**：

Phase 4 修补后，必须重建 preceding_summary 并验证后续章节的一致性：

```python
def _rebuild_preceding_summary(self, chapters) -> str:
    """重建前文摘要（修补后必须调用）"""
    summary_parts = []
    for ch in chapters:
        summary_parts.append(f"【{ch.title}】{'; '.join(ch.key_conclusions)}")
    return "\n".join(summary_parts)

async def _verify_downstream_consistency(self, chapters, patched_chapter_ids, framework):
    """验证被修改章节的后续章节是否仍然一致"""
    for i, chapter in enumerate(chapters):
        if chapter.chapter_id in patched_chapter_ids:
            continue
        # 检查此章是否引用了被修改的数据
        for patched_id in patched_chapter_ids:
            patched_ch = next(c for c in chapters if c.chapter_id == patched_id)
            for dp in patched_ch.data_points_used:
                if dp.metric and dp.value and dp.metric in chapter.content:
                    # 此章引用了被修改的数据指标，检查数值是否一致
                    # 简化实现：用正则检查
                    import re
                    pattern = re.compile(re.escape(dp.value) + r'\s*' + re.escape(dp.unit))
                    if pattern.search(chapter.content):
                        continue  # 数值匹配，无需修改
                    else:
                        logger.warning(f"Chapter {chapter.chapter_id} references '{dp.metric}' "
                                     f"with outdated value after patch of chapter {patched_id}")
                        # 标记此章也需要 patch
                        ...
```

---

## 缺陷 6【严重】rewrite 闭环可能导致质量退化而非提升

**位置**：3.5 ReportOrchestrator 审查闭环、3.5 rewrite()

**问题**：

每次 rewrite 基于上一版的问题修改，但可能引入新问题。2轮 rewrite 后的版本可能比初版更差：

- 第1版：逻辑A有问题
- rewrite 1：修了逻辑A，但破坏了逻辑B
- rewrite 2：修了逻辑B，但引入了逻辑C的问题

而且审查Agent可能会对每次修改都发现新问题（因为每次修改都改变了内容），导致无限循环（被 MAX_CHAPTER_REWRITE_ROUNDS 硬截断）。

**修正**：

增加**版本对比保底机制**——如果重写后审查评分不如上一版，回退到上一版：

```python
best_chapter = chapter  # 保存最佳版本
best_score = 0.0

for rewrite_round in range(self.MAX_CHAPTER_REWRITE_ROUNDS):
    review = await self._chapter_reviewer.review(...)
    
    if review.passed:
        if review.score > best_score:
            best_chapter = chapter
            best_score = review.score
        break
    
    # 关键：记录当前版本为候选最佳
    if review.score > best_score:
        best_chapter = chapter
        best_score = review.score
    
    # 重写
    chapter = await self._chapter_writer.rewrite(...)

# 使用最佳版本（而非最后一次重写的版本）
chapter = best_chapter
```

---

## 缺陷 7【严重】框架 dimensions 与聚合数据的映射未定义

**位置**：3.5 ReportOrchestrator._extract_chapter_data()

**问题**：

`_extract_chapter_data(aggregated_result, dimension.section_id)` 是整个流程的数据入口，但它的实现未定义。当前 ResultAggregator 使用模糊匹配（Jaccard + 编辑距离）将聚合数据映射到章节，匹配错误率约 15-20%。

如果映射错误：
- ChapterWriter 收到错误或为空的数据 → 章节内容基于错误数据或无数据撰写
- 后续审查发现"数据缺失"→ DataRepairAgent 搜索补充 → 但原始数据其实已经存在，只是映射错误

**修正**：

在 Agent 创建阶段（而非报告生成阶段）就建立 section_id → agent_id 的确定性映射，沿数据流传递到 ReportOrchestrator：

```python
@dataclass
class ChapterWriteInput:
    framework: ResearchFramework
    chapter_spec: FrameworkDimension
    chapter_data: Dict[str, Any]
    preceding_summary: str
    used_metrics_summary: str
    section_agent_map: Dict[str, str]     # section_id → agent_id 确定性映射
```

`_extract_chapter_data` 的实现：

```python
def _extract_chapter_data(self, aggregated_result, section_id, section_agent_map):
    """从聚合结果中提取章节数据（确定性映射）"""
    agent_id = section_agent_map.get(section_id)
    if agent_id and agent_id in aggregated_result:
        return aggregated_result[agent_id]
    
    # Fallback: 模糊匹配（保留现有逻辑，但记录警告）
    logger.warning(f"No deterministic mapping for section_id={section_id}, using fuzzy match")
    return self._fuzzy_match_chapter_data(aggregated_result, section_id)
```

---

## 缺陷 8【中等】ConflictResolver 来源权威性表不完整，且仅覆盖中文

**位置**：3.6.2 ConflictResolver.source_authority

**问题**：

来源权威性表只包含约 10 个中文域名。对于：
- 国际来源（Bloomberg、Reuters、Statista、World Bank等）→ 评分 0，总是触发昂贵搜索
- 政府来源（各部委网站不限于 stats.gov.cn 和 miit.gov.cn）
- 学术来源（知网、万方、arXiv、Nature等）
- 行业协会来源（中汽协、IDC、Gartner等）

当所有来源评分都为 0 时，会退化为 LLM 裁决——但 LLM 可能根据表面措辞而非权威性做判断。

**修正**：

1. 扩展权威性表为可配置文件（而非硬编码）
2. 增加"类型权威性"规则（不基于域名，基于来源描述中的关键词）

```python
# 配置文件：config/source_authority.yaml
domain_authority:
  # 政府
  "gov.cn": 10
  "gov": 8           # 国际政府网站
  # 国际研究
  "worldbank.org": 9
  "imf.org": 9
  "oecd.org": 9
  # 行业研究
  "idc.com": 8
  "gartner.com": 8
  "statista.com": 7
  # 财经媒体
  "bloomberg.com": 6
  "reuters.com": 6
  # 学术
  "arxiv.org": 7
  "nature.com": 8
  "sciencedirect.com": 7

# 基于来源描述的规则（当域名匹配不到时）
description_rules:
  - pattern: "国家统计局|官方统计|政府公告"
    score: 10
  - pattern: "年报|季报|财报|IPO招股书"
    score: 8
  - pattern: "研究报告|白皮书|行业报告"
    score: 7
  - pattern: "新闻报道|媒体报道"
    score: 4
```

---

## 缺陷 9【中等】Phase 2-3 的中间结果无持久化，崩溃即丢失

**位置**：3.5 ReportOrchestrator 全流程

**问题**：

逐章生成过程中，已完成的章节只存储在内存中的 `chapters` 列表。如果：
- LLM 服务在 Phase 2 中途不可用
- 进程被 kill
- 服务器重启

所有已生成的章节、已通过的审查、已注册的数据点全部丢失，必须从头开始。

对于一份耗时 5-8 分钟的报告，中途崩溃意味着 5 分钟的工作白费。

**修正**：

在 Phase 2 每章完成后，将中间结果持久化到文件：

```python
async def _checkpoint_chapter(self, task_id, chapter, data_registry_snapshot):
    """章节完成后保存检查点"""
    checkpoint_dir = Path("data") / task_id / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    chapter_data = {
        "chapter_id": chapter.chapter_id,
        "title": chapter.title,
        "content": chapter.content,
        "data_points_used": [dp.__dict__ for dp in chapter.data_points_used],
        "key_conclusions": chapter.key_conclusions,
        "self_check_passed": chapter.self_check_passed,
        "self_check_issues": chapter.self_check_issues,
        "data_registry_snapshot": data_registry_snapshot,
        "timestamp": datetime.now().isoformat(),
    }
    
    checkpoint_path = checkpoint_dir / f"chapter_{chapter.chapter_id}.json"
    checkpoint_path.write_text(json.dumps(chapter_data, ensure_ascii=False, indent=2), encoding="utf-8")

async def _restore_from_checkpoint(self, task_id):
    """从检查点恢复"""
    checkpoint_dir = Path("data") / task_id / "checkpoints"
    if not checkpoint_dir.exists():
        return None
    
    chapters = []
    data_registry_snapshot = {}
    for path in sorted(checkpoint_dir.glob("chapter_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        chapter = ChapterWriteOutput(**{k: v for k, v in data.items() if k != "data_registry_snapshot"})
        chapters.append(chapter)
        data_registry_snapshot = data.get("data_registry_snapshot", {})
    
    return chapters, data_registry_snapshot if chapters else None
```

---

## 缺陷汇总与修正优先级

| # | 等级 | 缺陷 | 修正工作量 | 必须在Phase几完成 |
|---|------|------|-----------|-----------------|
| 1 | 致命 | DataRegistry 无法被 LLM 查询 | 中 | Phase 1 |
| 2 | 致命 | patch_data 破坏审查结果 | 中 | Phase 3-4 |
| 3 | 致命 | 全局审查 token 爆炸 | 中 | Phase 3 |
| 4 | 严重 | data_points_used 自报不可靠 | 中 | Phase 2 |
| 5 | 严重 | preceding_summary 过期 | 小 | Phase 4 |
| 6 | 严重 | rewrite 质量退化 | 小 | Phase 2 |
| 7 | 严重 | 框架-数据映射未定义 | 大 | Phase 1 |
| 8 | 中等 | 来源权威性表不完整 | 小 | Phase 3 |
| 9 | 中等 | 中间结果无持久化 | 中 | Phase 4 |

**建议**：将以上 9 个修正作为原设计文档的勘误附录，在实施时严格按优先级逐项验证。
