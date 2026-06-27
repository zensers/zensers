# 报告质量提升全面扫描分析：78→90+路线图

> 日期: 2026-06-27
> 基准: e2e v4实测 score=78, convergence_rounds=1, converged=False
> 目标: 从78分提升到90+分
> 扫描范围: 9个Prompt模板、orchestrator.py(1304行)、generic_agent.py(5179行)、checkers.py(1085行)、quality_check_agent.py(1185行)

---

## 0. v4实测报告质量诊断

### 0.1 章节级问题

| 章节 | 字数 | 数据点 | 模糊来源 | 关键问题 |
|------|------|--------|----------|---------|
| 第1章：核心财务指标与盈利能力 | 2214 | 10 | 0 | 仍存在"反证与边界条件""决策启示"等非研报结构段落；"来源49"模糊来源 |
| 第2章：研发与创新投入 | 2192 | 9 | 0 | 仍存在"反证与边界条件""含义"等非研报结构段落；归母净利润21.11亿 vs 第1章40.85亿冲突 |
| 第3章：供应链成本效率 | 1401 | 10 | 0 | 仍存在"反证证据""影响"等非研报结构段落；字数偏少(1401 vs 其他>2000) |

### 0.2 系统级问题

- 收敛循环1轮后停滞(improvement<5)，差2分到80目标
- LLM调用只记录了orchestrator直接调用(1次exec_summary)，writer/reviewer各自直接调llm_skill不经过`_call_llm_tracked`
- 全局审查只看到章节标题+结论+数据点摘要，看不到正文

---

## 1. 五层18个提升点

### 第一层：Prompt层面（影响最大，直接决定LLM输出质量）

#### P1. chapter_write.tmpl — 段落标题无负面清单

**现状**: 结构规范段只写了4要素顺序，但LLM仍生成"反证与边界条件""含义""决策启示""影响"等非研报段落

**根因**: 没有明确禁止这些段落标题，LLM惯性生成"学术讨论式"结构

**提升方案**: 在`chapter_write.tmpl`的"章节结构规范"段增加：

```
### 禁止使用的段落标题（黑名单）
以下标题模式**严禁出现**，对应内容必须收拢到"风险提示"或删除：
- ❌ "反证与边界条件" / "反证" / "反证证据" → 收拢到风险提示
- ❌ "含义" / "启示" / "决策启示" / "影响" → 精简1-2句并入论证分析末尾
- ❌ "边界条件" / "条件假设" → 收拢到风险提示
- ❌ "正面论证" / "反面论证" → 统一为论证分析中的确定性论述

允许的段落标题模式（白名单）：
- ✅ "核心结论" / "核心判断" / "核心发现"
- ✅ "论证与分析" / "逻辑推导" / "论证" / "分析"
- ✅ "数据支撑" / "数据支持" / "数据来源"
- ✅ "风险提示" / "风险与不确定性"
```

**预期提升**: +5~8分（消除结构违规，reviewer不再因结构扣分）

#### P2. chapter_write.tmpl — 缺少"逐段精修指令"

**现状**: prompt说"精修润色"但LLM倾向于重新组织结构，导致分析Agent精炼数据被丢弃

**根因**: "精修"缺乏操作性定义——LLM不知道"精修"=逐段对照base_content保留核心论点

**提升方案**: 在`chapter_write.tmpl`增加"精修操作规程"：

```
### 精修操作规程（严格遵循）
1. 逐段对照初稿——初稿每段的核心论点和数据引用必须保留
2. 操作模式：
   - 段落A(核心结论)：保留原文，优化措辞（如"遭遇"→"面临"），补充数据来源标注
   - 段落B(论证)：保留推理链条，补充遗漏的数据支撑，删除冗余修饰
   - 段落C(数据)：保留数值和来源，优化表格格式，补充缺失单位
   - 段落D(风险提示)：如初稿有"反证与边界条件"，将其内容提炼为风险提示
3. 禁止重排段落顺序——初稿结构即最终结构，只做内容精修不做结构调整
```

**预期提升**: +2~3分（保留上游精炼数据，减少信息丢失）

#### P3. chapter_review.tmpl — 缺少"结构合规度"审查维度

**现状**: 5个审查维度（数据锚定35%+数据支撑20%+逻辑20%+完整15%+风格10%），**不审查结构合规性**

**根因**: reviewer不检查是否遵循四要素结构，"反证与边界条件"等违规段落不被扣分

**提升方案**: 增加"结构合规度"维度，调整权重：

```
### 6. 结构合规度（权重10%）
- 是否采用传统研报四要素结构（核心结论→论证分析→数据支撑→风险提示）？
- 是否出现禁止段落标题（反证、含义、边界条件、决策启示等）？
- 风险提示是否放在章节末尾？

### 权重调整
1. 数据锚定度（33%）
2. 数据支撑度（18%）
3. 逻辑清晰度（18%）
4. 结构合规度（10%）
5. 内容完整度（14%）
6. 内容冗余度与风格（7%）
```

**预期提升**: +3~5分（结构违规被扣分→LLM被迫修正）

#### P4. chapter_review.tmpl — 缺少"章内数据自洽性"检查

**现状**: 只检查"与前文引用的数据一致"，不检查同章内数据自洽

**提升方案**: 在"数据支撑度"维度增加：

```
- 同一章内引用的同一指标数值是否一致（如归母净利润不能出现40.85亿和21.11亿两个值）
```

**预期提升**: +1~2分

#### P5. global_review.tmpl — 审查粒度太粗

**现状**: `serialize_report_for_review`只输出标题+结论+数据点，不包含正文

**根因**: global_reviewer看不到具体内容，无法发现结构违规、逻辑跳跃、数据编造

**提升方案**: 修改`global_reviewer.py:serialize_report_for_review`，每章增加前500字正文摘要：

```python
def serialize_report_for_review(chapters, data_registry):
    sections_summary = []
    for i, ch in enumerate(chapters):
        content_preview = ch.content[:500] if len(ch.content) > 500 else ch.content
        data_summary = [f"  {dp.metric}: {dp.value} {dp.unit}" for dp in ch.data_points_used]
        sections_summary.append(
            f"### 第{i+1}章：{ch.title}\n"
            f"核心结论：{'; '.join(str(c) for c in ch.key_conclusions)}\n"
            f"正文摘要：{content_preview}\n"
            f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
        )
    return "\n\n".join(sections_summary)
```

**预期提升**: +2~4分

#### P6. exec_summary.tmpl — 缺乏结构约束

**现状**: 只说"800-1200字，面向决策层"，没有结构要求

**提升方案**: 增加执行摘要结构模板：

```
## 执行摘要结构（严格遵守）
1. **核心结论**（1-2段）— 整合各章节最重要发现，形成完整叙事线
2. **关键数据**（3-5个）— 用数据支撑核心结论，每个数据标注来源章节
3. **风险展望**（1段）— 集中说明主要不确定性、数据缺口、假设前提
4. 禁止使用"一方面...另一方面..."的模糊平衡表述
```

**预期提升**: +1~2分

---

### 第二层：执行逻辑层面

#### E1. 收敛阈值太严格 — MIN_CONVERGENCE_IMPROVEMENT=5

**现状**: v4第1轮78分，improvement<5就退出，差2分到80

**提升方案**: 采用渐进阈值：

```python
class RetryPolicy:
    MIN_CONVERGENCE_IMPROVEMENT_ROUND1 = 5
    MIN_CONVERGENCE_IMPROVEMENT_ROUND2 = 3
    MIN_CONVERGENCE_IMPROVEMENT_ROUND3 = 2
```

在`_quality_convergence_loop`中根据round_idx选择对应阈值。

**预期提升**: +2~5分（第2轮有机会继续提升）

#### E2. rewrite路径不与best_score比较

**现状**: `_phase4_fix_and_optimize` L629只比较`rewrite_review.score >= re_review.score`，不与best_score比较

**提升方案**: 改为`rewrite_review.score >= best_score`才替换：

```python
if rewrite_review.score >= best_score:
    chapters[i] = rewritten
```

**预期提升**: 防止质量回退

#### E3. review循环缺少提前退出机制

**现状**: 如果best_score已经>=80，仍在review循环中

**提升方案**: 在rewrite_round循环中增加：

```python
if best_score >= RetryPolicy.TARGET_SCORE:
    break
```

**预期提升**: 减少不必要的LLM调用

#### E4. _diagnose_issue_source触发词不全

**现状**: 只有"缺乏/缺失/未标注/缺口"4个触发词

**提升方案**: 扩展为：

```python
L1_TRIGGER_WORDS = ["缺乏", "缺失", "未标注", "缺口", "未提供", "不足", "欠缺", "缺少", "没有", "无"]
```

**预期提升**: +1~2分（更多L1缺失被识别为需要搜索补充）

#### E5. patch指令缺乏精确数值

**现状**: L2_omitted分支的patch指令只包含raw_data_summary的一行文本，不是结构化数值

**提升方案**: 从chapter_data(dict)中提取精确数值，传入patch指令：

```python
def _build_anchor_patch_instructions(..., chapter_data=None):
    # 在L2_omitted分支：
    if chapter_data and isinstance(chapter_data, dict):
        for key, value in chapter_data.items():
            if metric_core in str(key) or metric_core in str(value):
                precise_value = f"精确数据（来源：{key}）：{json.dumps(value, ensure_ascii=False)[:300]}"
                instructions.append(f"补充已有数据：{desc[:100]}。{precise_value}")
```

**预期提升**: +1~2分（修补精度提高）

---

### 第三层：架构层面

#### A1. 分析Agent→报告Agent数据传递断裂

**现状**: 分析Agent输出正文→orchestrator提取`content`作为base_content→writer只拿到一段文本。分析Agent的`data_points`、`key_conclusions`等结构化输出**没有传递给chapter_writer**

**提升方案**: 将分析Agent的结构化数据也传入ChapterWriteInput：

```python
class ChapterWriteInput:
    # 新增字段
    upstream_data_points: List[Dict[str, Any]] = None
    upstream_key_conclusions: List[str] = None
```

在`chapter_write.tmpl`中增加：

```
## 分析研究员的结构化输出（精确引用来源）
${upstream_data_points_json}
```

**预期提升**: +2~4分（writer能精确引用而非凭文本猜测）

#### A2. 全局审查只看摘要不看正文

（已在P5中详述）

#### A3. quality_check_agent与report_upgrade质量体系是两套独立系统

**现状**: `AnalysisQualityChecker`(checkers.py)做结构检查，但orchestrator只用chapter_reviewer(LLM review)

**提升方案**: 将AnalysisQualityChecker的分数作为收敛循环的辅助信号：

```python
async def _quality_convergence_loop(self, chapters, review, ...):
    # 在收敛循环中，先做程序化结构检查
    checker = AnalysisQualityChecker()
    for ch in chapters:
        checker_result = checker.check({"content": ch.content})
        if checker_result.score < 60:
            # 结构不合规，强制加入patch_chapter_ids
            patch_chapter_ids.add(ch.chapter_id)
```

**预期提升**: +2~3分（程序化检查不遗漏结构违规）

---

### 第四层：数据质量层面

#### D1. 跨章数据冲突未自动解决

**现状**: 第1章归母净利润40.85亿 vs 第2章21.11亿

**根因**: DataRegistry检测冲突→ConflictResolver应统一，但可能两个值被标注为"不同口径"（40.85=Q1实际值，21.11=调整后值）

**提升方案**: ConflictResolver在统一时标注口径差异：

```python
# 冲突解决时输出：
"归母净利润统一为40.85亿元（Q1实际值），第2章引用的21.11亿元为剔除汇兑亏损后的调整值，
 应标注'调整后归母净利润21.11亿元（剔除约21亿元汇兑亏损）'"
```

**预期提升**: +1~2分

#### D2. StockDataSkill数据未充分注入

**现状**: `_try_fill_data_gap`只在L1_missing时调用，且EntityResolver首次加载可能超时

**提升方案**: 在`_extract_chapter_data`阶段就尝试预取关键指标：

```python
def _extract_chapter_data(self, aggregated_result, section_id, content_dependencies):
    # ...现有逻辑...
    # 新增：尝试从StockDataSkill预取
    if self._skill_registry:
        try:
            stock_skill = self._skill_registry.get("stock_data")
            if stock_skill and topic_contains_company_name:
                key_metrics = await stock_skill.execute(symbol=stock_code, action="key_metrics")
                if key_metrics.get("success"):
                    refined["stock_key_metrics"] = key_metrics["content"]
        except Exception:
            pass
```

**预期提升**: +1~3分

#### D3. "来源49"等模糊来源

**现状**: `_ground_data_point_sources`用original_sources[0]作为fallback，但"来源49"说明grounding逻辑没覆盖到

**提升方案**: 改用href匹配而非简单fallback：

```python
@staticmethod
def _ground_data_point_sources(data_points, available_sources):
    for dp in data_points:
        dp_src = dp.get("source", "")
        if dp_src and not _is_vague_source(dp_src):
            grounded.append(dp)
            continue
        # 新增：用数字索引匹配href
        if re.match(r'来源\d+', dp_src):
            idx = int(re.search(r'\d+', dp_src).group()) - 1
            if 0 <= idx < len(available_sources):
                dp["source"] = available_sources[idx].get("title", available_sources[idx].get("href", ""))
        else:
            dp["source"] = fallback_source
    return grounded
```

**预期提升**: +0.5~1分

---

### 第五层：评分体系层面

#### S1. AnalysisQualityChecker权重不合理

**现状**: structure 40% + caliber 30% + risk_disclosure 20% + quantified 10%

**问题**: caliber(数据口径声明)占30%——研报中大量数据不需要口径声明(如"70.05万辆"不需要GAAP/IFRS标注)

**提升方案**: 调整权重：

```python
structure_score = self._check_structure(content) * 0.50   # 40→50
caliber_score = self._check_caliber_coverage(content) * 0.15  # 30→15
risk_score = self._check_risk_disclosure(content) * 0.20      # 不变
quant_score = self._check_quantified_decomposition(content) * 0.15  # 10→15
```

**预期提升**: +1~3分（caliber不再过度扣分）

#### S2. STRUCTURE_MARKERS的data_support关键词太宽泛

**现状**: `"据"`作为关键词匹配"据2026年一季报"但也匹配"据了解"

**提升方案**: 收紧关键词，增加最小上下文长度：

```python
"data_support": {
    "keywords": ["数据来源", "数据支撑", "Source", "数据显示", "据统计", "据XX数据显示", "据财报"],
    "min_context_chars": 50,  # 30→50
},
```

移除"据""来源""统计"等单字/泛化词。

**预期提升**: +0.5~1分

#### S3. "反证与边界条件"不属于risk_disclosure匹配范围

**现状**: v4各章都有"反证与边界条件"而非"风险提示"，risk_disclosure得分可能为0

**提升方案**: 将"反证""边界条件"纳入risk_disclosure的过渡期兼容匹配：

```python
"risk_disclosure": {
    "keywords": ["风险提示", "风险", "不确定性", "假设", "数据缺口",
                 "反证", "边界条件", "反面", "限制",  # 过渡期兼容
                 "需要注意的是", "但需注意", "潜在风险"],
    "min_context_chars": 30,
    "exclude_trivial": True,
    "transition_note": "反证/边界条件应收拢到风险提示，过渡期兼容评分",
},
```

同时在`_check_risk_disclosure`中为"反证"匹配降权(0.6而非1.2)。

**预期提升**: +3~5分（兼容期内不因结构违规直接0分）

---

## 2. 优先级排序（按投入产出比）

| 优先级 | 提升点 | 预期提升 | 工作量 | 涉及文件 |
|--------|--------|----------|--------|---------|
| **P0** | P1(段落黑名单) | +5~8分 | 小 | chapter_write.tmpl |
| **P0** | E1(收敛阈值渐进) | +2~5分 | 小 | orchestrator.py |
| **P0** | S3(反证兼容risk) | +3~5分 | 小 | checkers.py |
| **P1** | P3(审查+结构维度) | +3~5分 | 小 | chapter_review.tmpl |
| **P1** | A2/P5(全局审查看正文) | +2~4分 | 小 | global_reviewer.py |
| **P1** | P2(逐段精修指令) | +2~3分 | 小 | chapter_write.tmpl |
| **P2** | E4(触发词扩展) | +1~2分 | 小 | orchestrator.py |
| **P2** | S1(权重调整) | +1~3分 | 小 | checkers.py |
| **P2** | P6(摘要结构) | +1~2分 | 小 | exec_summary.tmpl |
| **P3** | A1(数据传递) | +2~4分 | 中 | models.py + chapter_writer.py + orchestrator.py |
| **P3** | D1(跨章冲突) | +1~2分 | 中 | orchestrator.py |
| **P3** | E5(patch精确数值) | +1~2分 | 中 | orchestrator.py |
| **P3** | D2(StockData预取) | +1~3分 | 中 | orchestrator.py |
| **P3** | E2/E3(best_score比较+提前退出) | 防回退 | 小 | orchestrator.py |
| **P3** | D3(来源49修复) | +0.5~1分 | 小 | orchestrator.py |
| **P3** | S2(data_support关键词收紧) | +0.5~1分 | 小 | checkers.py |
| **P4** | A3(程序化检查接入) | +2~3分 | 大 | orchestrator.py + checkers.py |
| **P4** | P4(章内自洽性) | +1~2分 | 小 | chapter_review.tmpl |

### 预期效果

- **P0三项(1天)**: 78 → 85+
- **P0+P1六项(2天)**: 78 → 90+
- **全部18项(5天)**: 78 → 92+

---

## 3. 实施顺序建议

### Phase 1: P0三项（预期78→85+）

1. 修改`chapter_write.tmpl`增加段落黑名单+白名单
2. 修改`orchestrator.py` RetryPolicy增加渐进阈值
3. 修改`checkers.py` STRUCTURE_MARKERS增加"反证""边界条件"兼容匹配

### Phase 2: P1三项（预期85→90+）

4. 修改`chapter_review.tmpl`增加"结构合规度"维度
5. 修改`global_reviewer.py` serialize_report_for_review增加正文摘要
6. 修改`chapter_write.tmpl`增加"逐段精修指令"

### Phase 3: P2四项（预期90→93+）

7. 扩展`_diagnose_issue_source`触发词
8. 调整`AnalysisQualityChecker`权重
9. 增加`exec_summary.tmpl`结构模板
10. 修改E2/E3(best_score比较+提前退出)

### Phase 4: P3+P4剩余项（预期93→95+）

11-18. 依次实施A1/D1/E5/D2/D3/S2/P4/A3

---

## 4. 风险与注意事项

1. **P1(段落黑名单)**可能过度约束LLM——如果某个主题确实需要"反面论证"，黑名单会阻止。建议在黑名单前加"除非研究框架明确要求反面论证"
2. **S3(反证兼容risk)**是过渡期方案——最终目标仍是让LLM生成"风险提示"而非"反证"，兼容匹配只防0分惩罚
3. **E1(渐进阈值)**可能增加收敛轮数和LLM调用成本——需要在cost和quality之间权衡
4. **A2/P5(正文摘要)**增加全局审查的token消耗——500字*3章=1500字额外上下文
5. **S1(权重调整)**影响的是AnalysisQualityChecker，而非chapter_reviewer的LLM评分——两者评分体系不同
