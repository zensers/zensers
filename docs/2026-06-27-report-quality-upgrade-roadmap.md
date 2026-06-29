# 报告质量提升全面扫描分析：78→90+路线图（修订版）

> 日期: 2026-06-27
> 修订日期: 2026-06-29（代码审查修正：A3 确认已实现；D2/E5 参数存在但函数体未使用，标注修正）
> 基准: e2e v4实测 score=78, convergence_rounds=1, converged=False
> 目标: 从78分提升到90+分
> 扫描范围: 9个Prompt模板、orchestrator.py(1304行)、chapter_writer.py(135行)、chapter_reviewer.py(67行)、checkers.py(1085行)、global_reviewer.py(137行)、models.py(168行)、data_registry.py(118行)、structured_data_repair.py(105行)
> 审查说明: 2026-06-29 基于真实代码环境两轮审计确认：15/17 项已实现，2 项部分实现（D2/E5 参数死代码），3 项未实现（P2/D1/P4）

---

## ⚠️ 关键认知修正

### 评分体系不一致问题

v4的78分来自**LLM reviewer**（`chapter_review.tmpl`），不是`AnalysisQualityChecker`（`checkers.py`）。两者独立运行：

| 评分体系 | 用在哪 | 参与收敛循环? | 影响78分? |
|---------|--------|-------------|----------|
| LLM reviewer (chapter_review.tmpl) | 收敛循环的score判断 | ✅ 是 | ✅ 直接影响 |
| AnalysisQualityChecker (checkers.py) | 目前仅独立检查 | ❌ 否 | ❌ 不影响 |

**S3/S1/S2只影响AnalysisQualityChecker，对收敛循环分数无效。** 它们是"改评分标准"而非"改报告质量"——报告里仍有"反证与边界条件"，只是checker不再扣分。仅当A3将AnalysisQualityChecker接入收敛循环后，S3/S1/S2才有意义。

### 评分标准变化后分数不可比

P3增加"结构合规度"审查维度后，reviewer的评分维度从5个变为6个。修改后的分数和v4的78分**不在同一标尺**上。

### LLM遵从度黑盒

`chapter_write.tmpl:67`已有禁止指令"正文中不要出现'反证''边界条件'"，但LLM仍无视生成3个违规段落。黑名单/白名单增强的效果**高度不确定**，不能作为主要依赖。**程序化后处理(N1)是确定性最高的方案**，但需注意其局限性（见N1方案详述）。

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

## 1. 五层提升点

### 第一层：Prompt层面（影响最大，直接决定LLM输出质量）

#### P1. chapter_write.tmpl — 段落标题无负面清单

**现状**: `chapter_write.tmpl:67`已有指令"正文中不要出现'反证''边界条件'等学术讨论段落，不确定性统一收拢到风险提示"，但LLM仍无视，3个章节均存在此类段落。

**根因**: 单条禁止指令被LLM惯性生成"学术讨论式"结构所覆盖。更详细的黑名单是必要补充，但**预期效果有限**——同类指令已存在且无效，LLM对"禁止"类指令的遵从度本身偏低。

**提升方案**: 在`chapter_write.tmpl`的"章节结构规范"段增加黑名单+白名单：

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

**⚠️ 修订要点**: 黑名单必须与P3(结构合规度审查)配合才能生效。单独的黑名单依赖LLM遵从度，效果有限。P3通过扣分强制LLM修正，是黑名单生效的必要保障。

**预期提升**: **+2~4分**（原文档+5~8分偏乐观。原因：L67已有同类指令且无效，黑名单增强后LLM遵从度仍有不确定性；需配合P3扣分机制才能保证效果）

#### P2. chapter_write.tmpl — 缺少"逐段精修指令"

**现状**: prompt说"提升专业性"（L37）但LLM倾向于重新组织结构，导致分析Agent精炼数据被丢弃

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
3. 如初稿存在结构违规（如"反证与边界条件"段落），允许将违规段落内容收拢到"风险提示"中——这是唯一允许的结构调整
```

**⚠️ 修订要点**: 原方案"禁止重排段落顺序"与结构合规度修正矛盾——如果初稿有"反证"段落，必须将其移到末尾的"风险提示"，这需要重排。修改为"只允许将违规段落收拢到风险提示，其余结构不变"。

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

**⚠️ 修订要点**: 这是P1(段落黑名单)生效的**必要保障**。黑名单依赖LLM遵从度，而结构合规度审查通过扣分强制LLM修正。两者必须同时实施。

**预期提升**: +2~3分（原文档+3~5分偏乐观。原因：依赖LLM reviewer执行扣分，reviewer本身是LLM，对结构合规的判断有一定不确定性）

#### P4. chapter_review.tmpl — 缺少"章内数据自洽性"检查

**现状**: 只检查"与前文引用的数据一致"（`chapter_review.tmpl:37`），不检查同章内数据自洽

**提升方案**: 在"数据支撑度"维度增加：

```
- 同一章内引用的同一指标数值是否一致（如归母净利润不能出现40.85亿和21.11亿两个值）
```

**⚠️ 修订要点**: 此检查依赖LLM reviewer判断，非程序化检查。更可靠的方案是在 `_extract_and_validate_data_points`（orchestrator.py:824）中程序化检测同一章节内同一指标的多个不同值，但这需要额外的开发工作。当前方案作为第一步是合理的。

**预期提升**: +1~2分

#### P5. global_review.tmpl — 审查粒度太粗

**现状**: `serialize_report_for_review`（`global_reviewer.py:125-137`）只输出标题+结论+数据点，不包含正文

**根因**: global_reviewer看不到具体内容，无法发现结构违规、逻辑跳跃、数据编造

**提升方案**: 修改`global_reviewer.py:serialize_report_for_review`，每章增加**首400字+末400字**正文摘要（而非简单的前500字），因为风险提示和结构违规通常出现在章节末尾：

```python
def serialize_report_for_review(chapters, data_registry):
    sections_summary = []
    for i, ch in enumerate(chapters):
        content = ch.content or ""
        content_head = content[:400]
        content_tail = content[-400:] if len(content) > 800 else content[400:]
        data_summary = [f"  {dp.metric}: {dp.value} {dp.unit}" for dp in ch.data_points_used]
        sections_summary.append(
            f"### 第{i+1}章：{ch.title}\n"
            f"核心结论：{'; '.join(str(c) for c in ch.key_conclusions)}\n"
            f"正文前段：{content_head}\n"
            f"正文后段：{content_tail}\n"
            f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
        )
    return "\n\n".join(sections_summary)
```

**⚠️ 修订要点**:
- 原方案取前500字摘要，但风险提示通常在章节末尾（`chapter_write.tmpl:66`明确要求"风险提示放在章节最后一部分"），前500字可能遗漏末尾的结构违规
- 改为首400字+末400字，当章节长度>800字时head和tail无重叠；当400<len<=800时tail从400字开始取，避免重叠；当len<=400时head已覆盖全文
- 总增加约800字*3章=2400字额外上下文，比原方案500字*3=1500字多900字，但确保末尾内容也被审查

**预期提升**: +2~4分

#### P6. exec_summary.tmpl — 缺乏结构约束

**现状**: `exec_summary.tmpl:24-29`只说"800-1200字，面向决策层"，没有结构要求

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

#### N1. 程序化结构后处理（新增，确定性方案）

**问题**: LLM生成的章节中存在"反证与边界条件""决策启示""含义""影响"等非研报规范段落，LLM对禁止指令遵从度低（L67已有禁止指令但仍生成3个违规段落）

**方案**: 在`chapter_writer.write()`返回后、`_chapter_reviewer.review()`之前（orchestrator.py L152-153之间），增加程序化后处理函数，对`chapter.content`进行确定性修正：

```python
import re

_FORBIDDEN_SECTION_PATTERNS = [
    (r'^#{1,3}\s*反证(?:与|及|和)?边界条件', 'risk_disclosure'),
    (r'^#{1,3}\s*反证(?:证据)?', 'risk_disclosure'),
    (r'^#{1,3}\s*边界条件(?:假设)?', 'risk_disclosure'),
    (r'^#{1,3}\s*正面?论证', 'argument'),
    (r'^#{1,3}\s*反面?论证', 'argument'),
    (r'^#{1,3}\s*(?:决策)?启示', 'merge_last'),
    (r'^#{1,3}\s*含义', 'merge_last'),
    (r'^#{1,3}\s*影响$', 'merge_last'),
]

_RISK_DISCLOSURE_HEADING = "#### 风险提示"

def _enforce_structure_compliance(content: str) -> str:
    """
    程序化后处理：将违规段落标题替换/收拢为规范结构。
    在chapter_writer.write()返回后、chapter_reviewer.review()之前调用。
    """
    lines = content.split('\n')
    result_lines = []
    risk_buffer = []  # 收拢的违规段落内容
    has_risk_section = False
    
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        matched = False
        for pattern, action in _FORBIDDEN_SECTION_PATTERNS:
            if re.match(pattern, stripped):
                matched = True
                # 收集该标题下的内容（直到下一个标题或空行+标题）
                j = i + 1
                section_content = []
                while j < len(lines):
                    next_stripped = lines[j].strip()
                    if next_stripped.startswith('#') or (not next_stripped and j + 1 < len(lines) and lines[j+1].strip().startswith('#')):
                        break
                    section_content.append(lines[j])
                    j += 1
                if action == 'risk_disclosure':
                    risk_buffer.extend(section_content)
                elif action == 'argument':
                    result_lines.append(lines[i].replace(re.match(pattern, stripped).group(), '#### 论证分析'))
                    result_lines.extend(section_content)
                elif action == 'merge_last':
                    # 精简1-2句，并入最后的论证分析段落
                    if section_content:
                        summary = section_content[0].strip()
                        if len(summary) > 100:
                            summary = summary[:100] + '…'
                        result_lines.append(summary)
                i = j
                break
        if not matched:
            if stripped.startswith('#') and '风险提示' in stripped:
                has_risk_section = True
            result_lines.append(lines[i])
            i += 1
    
    # 将收拢的违规内容追加到风险提示段
    if risk_buffer:
        if has_risk_section:
            # 插入到风险提示段末尾
            insert_idx = len(result_lines)
            for idx in range(len(result_lines)):
                if result_lines[idx].strip().startswith('#') and '风险提示' in result_lines[idx]:
                    # 找到风险提示段的结束位置
                    insert_idx = idx + 1
                    while insert_idx < len(result_lines):
                        if result_lines[insert_idx].strip().startswith('#'):
                            break
                        insert_idx += 1
                    break
            for k, line in enumerate(risk_buffer):
                result_lines.insert(insert_idx + k, line)
        else:
            # 没有风险提示段，新增一个
            result_lines.append('')
            result_lines.append(_RISK_DISCLOSURE_HEADING)
            result_lines.extend(risk_buffer)
    
    return '\n'.join(result_lines)
```

**插入位置**: orchestrator.py L152后、L154前：
```python
chapter = await self._chapter_writer.write(...)
# 新增：程序化结构后处理
chapter.content = _enforce_structure_compliance(chapter.content)
```

**⚠️ 局限性**:
1. Markdown标题匹配依赖正则，边界情况下（如"反证"出现在正文而非标题中、标题格式不规范如加粗`**反证与边界条件**`）可能漏检。确定性应为"中高"而非"高"。
2. "影响"关键词匹配需排除正常用法（如"受到影响"），当前用`影响$`限制为标题行结尾。
3. 收拢后的风险提示内容可能冗余或措辞不统一——这是程序化处理的代价，后续可通过P3审查维度进一步修正。

**⚠️ 与P1+P3的关系**: N1与P1+P3目标重叠但机制互补：
- N1是确定性后处理，不管LLM是否遵从都能修正结构
- P1+P3是通过扣分机制从源头阻止LLM生成违规段落
- **两者同时实施时，N1会先修正结构→P3审查不再发现违规→P3扣分机制不起作用**。这是预期行为：N1作为保底，P1+P3作为源头预防
- **预期提升不应简单叠加**：N1(+3~6)和P1+P3(+1~3)都针对同一问题，实际效果取max而非求和。P1+P3的+1~3是在N1修正后LLM下次生成时减少违规（源头改善），而非额外消除当前违规

**预期提升**: **+3~5分**（取N1的确定性修正效果，P1+P3的源头预防效果叠加后边际递减。N1单独约+3~4分，P1+P3叠加后额外+0~1分。**注意**：N1只在初始write后调用，不覆盖patch/rewrite路径——patch_data(L550)和rewrite(L610)后不会自动N1处理，但后续reviewer会捕获新引入的违规并触发再修正。）

---

### 第二层：执行逻辑层面

#### E1. 收敛阈值太严格 — MIN_CONVERGENCE_IMPROVEMENT=5

**现状**: v4第1轮(round_idx=0)78分，improvement<5就退出，差2分到80

**⚠️ 修订要点（关键错误修正）**: 原方案设ROUND1=5, ROUND2=3, ROUND3=2，但v4卡在**第1轮(round_idx=0)**，此时阈值仍为5，与现状完全相同。渐进阈值只帮助后续轮次，对首轮停滞无任何改善。

**提升方案（修正）**: 应降低首轮阈值，而非仅降低后续轮次：

```python
class RetryPolicy:
    MIN_CONVERGENCE_IMPROVEMENT_ROUNDS = [3, 2, 1]  # 首轮3→第2轮2→第3轮1
    
    @staticmethod
    def get_min_improvement(round_idx: int) -> int:
        rounds = RetryPolicy.MIN_CONVERGENCE_IMPROVEMENT_ROUNDS
        if round_idx < len(rounds):
            return rounds[round_idx]
        return rounds[-1]  # 超出预设轮数时使用最后一个值
```

在`_quality_convergence_loop`中（L403）改为：

```python
if improvement < RetryPolicy.get_min_improvement(round_idx):
    break
```

**预期提升**: **+1~3分**（原文档+2~5分偏乐观。原因：修正后首轮阈值从5降到3，v4场景下improvement≈3已>=3，不会首轮停滞。但improvement=3意味着收敛速度慢，后续轮次提升幅度可能有限）

**⚠️ 成本风险**: 降低阈值会增加收敛轮数。v4中improvement≈3，首轮阈值改为3后不会停滞，但可能进入第2轮。每轮额外增加1次全局review+若干patch/rewrite调用，需在cost和quality之间权衡。

#### E2. _phase4_fix_and_optimize中rewrite后不保留best版本

**现状**: `_phase4_fix_and_optimize` L629比较`rewrite_review.score >= re_review.score`就替换章节，但函数内没有best_score跟踪机制

**根因**: `_phase4_fix_and_optimize`不跟踪全局best_score，rewrite后可能用更差版本替换原版本

**⚠️ 修订要点**: 外层`_quality_convergence_loop` L393-395已跟踪best_chapters/best_score，即使_phase4产生更差版本，收敛循环最终会选用best_chapters。E2的真正风险是**单轮内退化**（_phase4可能在一个收敛轮次内让某章节变差），但不会跨轮退化（外层收敛循环有保底机制）。

**提升方案（简化）**: L629处已有`re_review.score`（rewrite前的review分数），直接比较即可，无需额外LLM调用：

```python
# L629 现有：
if rewrite_review.score >= re_review.score:
    chapters[i] = rewritten

# 改为严格大于（>= → >），避免相同分数时无意义替换：
if rewrite_review.score > re_review.score:
    chapters[i] = rewritten
```

这是最小改动方案。更完善的方案是引入chapter_best_scores跟踪，但需额外LLM调用成本，暂不推荐。

**预期提升**: 防止单轮内质量回退（非加分，防退分）

**优先级调整**: 从P3降为P4——外层收敛循环已有保底机制，E2风险有限

#### E3. review循环缺少提前退出机制

**现状**: 代码在`review.score >= MIN_REVIEW_SCORE_TO_ACCEPT(60)`时退出循环（L182），在`best_score < MIN_REVIEW_SCORE_TO_ACCEPT(60)`时才触发rewrite（L232）

**⚠️ 修订要点（关键问题修正）**: 原文档说"60-79分段过早退出"——这描述正确。但**原方案有遗漏**：L232的rewrite条件`logic_issues and best_score < MIN_REVIEW_SCORE_TO_ACCEPT`意味着best_score>=60时不会rewrite logic_issues。如果将退出条件改为"60-79继续尝试"，还必须**同步修改L232的rewrite触发条件**，否则60-79分段虽不退出循环，但也不会触发rewrite，只是空转。

**提升方案（修正）**: 修改退出条件和rewrite触发条件：

```python
# L182 退出条件改为：
if review.passed or review.score >= RetryPolicy.TARGET_SCORE:
    break  # 达标退出（>=80）
if review.score >= MIN_REVIEW_SCORE_TO_ACCEPT and rewrite_round >= 2:
    break  # 60-79分段最多尝试2轮后退出

# L232 rewrite触发条件改为：
if logic_issues and best_score < RetryPolicy.TARGET_SCORE:
    chapter = await self._chapter_writer.rewrite(...)
```

**⚠️ 防无限循环**: 60-79分段最多2轮后必须退出（`rewrite_round >= 2`），否则可能无限制循环。同时需注意MAX_REVIEW_RETRIES=2（L43），2轮后循环本身也会结束。

**预期提升**: +1~3分（60-79分段有机会通过rewrite推到80+，但依赖rewrite质量）

#### E4. _diagnose_issue_source触发词不全

**现状**: L880只有"缺乏/缺失/未标注/缺口"4个触发词

**⚠️ 修订要点（危险修正）**: 原方案建议加入"没有""无"。这两个词在日常中文极常见（如"无明显风险""无重大变化""没有进一步数据"），加入后会导致正常描述被误判为数据缺失，触发不必要的搜索补充，浪费LLM调用且可能引入无关数据。

**提升方案（修正）**: 仅添加不会误判的触发词：

```python
# 在L880扩展触发词，但排除"没有""无"
if "缺乏" in desc or "缺失" in desc or "未标注" in desc or "缺口" in desc \
   or "未提供" in desc or "不足" in desc or "欠缺" in desc or "缺少" in desc:
```

**预期提升**: +1~2分（更多L1缺失被识别，且不产生误判）

#### E5. patch指令缺乏精确数值

**现状**: L2_omitted分支的patch指令（`_build_anchor_patch_instructions` L933-979）只包含raw_data_summary的一行文本，不是结构化数值

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

**⚠️ 实施注意**: chapter_data结构不固定（依赖上游分析Agent输出格式），方案需考虑chapter_data可能不含metric_core对应字段的情况。建议加fallback：如果精确数据提取失败，仍使用raw_data_summary文本。

**预期提升**: +1~2分（修补精度提高）

---

### 第三层：架构层面

#### A1. 分析Agent→报告Agent数据传递断裂

**现状**: L134只取`chapter_data.get("content")`作为base_content→writer只拿到一段文本。分析Agent的`data_points`、`key_conclusions`等结构化输出**没有传递给chapter_writer**。`ChapterWriteInput`（models.py:26-34）无upstream_data_points/upstream_key_conclusions字段。

**根因**: 数据传递断裂是报告质量问题的**根本原因之一**——writer凭文本猜测而非精确引用结构化数据，是数据来源模糊、引用不精确的根源。

**⚠️ 修订要点（关键错误）**: `_split_chapter_data`（L767）**显式剥离了`data_points`**：`if k == "data_points": continue`。因此`chapter_data`中永远不包含`data_points`，`chapter_data.get("data_points", [])`始终返回`[]`。原方案直接从chapter_data提取data_points是**不可行的**。

此外，上游分析Agent输出中**不含`key_conclusions`字段**（grep确认result_aggregator.py中无此字段）。`key_conclusions`是`ChapterWriteOutput`的属性，由chapter_writer生成，而非上游数据。

**提升方案（修正）**:

1. 修改`_split_chapter_data`(L767)不再剥离`data_points`，而是将其保留在refined中：

```python
# L766-772 修改为：
refined = {}
for k, v in raw_data.items():
    if k == "data_points" and isinstance(v, list):
        refined["upstream_data_points"] = v  # 保留，重命名避免与ChapterWriteOutput.data_points_used混淆
    elif isinstance(v, str) and len(v) > 8000:
        refined[k] = v[:8000]
    else:
        refined[k] = v
```

2. 不提取`key_conclusions`（上游不存在此字段），只提取`upstream_data_points`：

```python
# orchestrator.py L134 处：
base_content = chapter_data.get("content", "") if isinstance(chapter_data, dict) else ""
upstream_data_points = chapter_data.get("upstream_data_points", []) if isinstance(chapter_data, dict) else None
```

3. ChapterWriteInput只增加一个新字段：

```python
class ChapterWriteInput:
    # 新增字段（去掉upstream_key_conclusions，上游不存在此字段）
    upstream_data_points: List[Dict[str, Any]] = None
```

4. chapter_write.tmpl增加：

```
## 分析研究员的结构化数据输出（精确引用来源）
${upstream_data_points_json}
```

**预期提升**: **+3~5分**（原+2~4偏保守。数据传递断裂是根本问题）

**实施成本**: 需修改4个文件（models.py+orchestrator.py+chapter_writer.py+chapter_write.tmpl），且需同步修改`_split_chapter_data`的data_points保留逻辑

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

**⚠️ 实施注意**: `_quality_convergence_loop`不接收framework_config中的patch/rewrite逻辑，只是循环调用`_phase4_fix_and_optimize`。方案需修改`_phase4_fix_and_optimize`的入口，在调用前先做程序化检查，将不合规章节加入patch_chapter_ids。这需要修改`_phase4_fix_and_optimize`的签名以接收额外的patch_chapter_ids。

**预期提升**: +2~3分（程序化检查不遗漏结构违规）

---

### 第四层：数据质量层面

#### D1. 跨章数据冲突未自动解决

**现状**: 第1章归母净利润40.85亿 vs 第2章21.11亿

**根因**: `DataRegistry`（data_registry.py:20-26）检测冲突→ConflictResolver应统一，但可能两个值被标注为"不同口径"（40.85=Q1实际值，21.11=调整后值）

**提升方案**: ConflictResolver在统一时标注口径差异：

```python
# 冲突解决时输出：
"归母净利润统一为40.85亿元（Q1实际值），第2章引用的21.11亿元为剔除汇兑亏损后的调整值，
 应标注'调整后归母净利润21.11亿元（剔除约21亿元汇兑亏损）'"
```

**预期提升**: +1~2分

#### D2. StockDataSkill数据未充分注入

**现状**: `_try_fill_data_gap`只在L1_missing时调用，且EntityResolver首次加载可能超时

**注意**: `_extract_chapter_data`是`@staticmethod`（L706），无法访问`self._skill_registry`

**提升方案**: 保持static，调用方传入skill_registry（方案B，改动较小）：

```python
# 方案B：保持static，调用方传入skill_registry
def _extract_chapter_data(aggregated_result, section_id, content_dependencies, skill_registry=None):
    # ...现有逻辑不变...
    # 新增可选：skill_registry预取（不影响现有调用点）
```

所有调用点（L129, L439, L528）增加可选参数传入self._skill_registry。方案B改动最小，方案A（改实例方法）需要去掉3个调用点的类名前缀，风险更大。

**⚠️ 修订要点**: 
- 原文档推荐方案A，但方案B改动更小、风险更低。推荐方案B。
- **注意**: 如需在_extract_chapter_data内调用StockDataSkill（需要`await`），需将方法声明改为`@staticmethod async def _extract_chapter_data(...)`，所有调用点改为`await self._extract_chapter_data(...)`（L129, L439, L528均已在async函数内，无需额外调整）。
- 如果仅传skill_registry参数但并不立即执行skill（懒加载，留待_try_fill_data_gap内部调用），则无需async改造。

**预期提升**: +1~3分

**实施成本**: 方案B只需在_extract_chapter_data签名增加skill_registry=None参数+3个调用点传入

#### D3. "来源49"等模糊来源

**现状**: `_ground_data_point_sources`（L1163-1181）只做vague_source判断+fallback_source（取available_sources[0]的title），不处理"来源N"数字索引模式

**根因**: LLM生成的data_points中source字段可能为"来源49"（数字索引），但grounding逻辑只判断是否vague_source，不解析数字索引

**提升方案**: 在`_ground_data_point_sources`中增加数字索引匹配：

```python
@staticmethod
def _ground_data_point_sources(data_points, available_sources):
    if not available_sources:
        return data_points
    source_names = [s.get("title", s.get("url", s.get("href", ""))) 
                    for s in available_sources 
                    if s.get("title") or s.get("url") or s.get("href")]
    fallback_source = source_names[0] if source_names else ""
    grounded = []
    for dp in data_points:
        dp_src = dp.get("source", "")
        if dp_src and not _is_vague_source(dp_src):
            grounded.append(dp)
        else:
            dp = dict(dp)
            # 新增：解析"来源N"数字索引
            idx_match = re.match(r'来源(\d+)', dp_src)
            if idx_match:
                idx = int(idx_match.group(1)) - 1
                if 0 <= idx < len(available_sources):
                    dp["source"] = available_sources[idx].get("title", 
                                    available_sources[idx].get("href", ""))
                else:
                    dp["source"] = fallback_source
            else:
                dp["source"] = fallback_source
            grounded.append(dp)
    return grounded
```

**预期提升**: +0.5~1分

---

### 第五层：评分体系层面

#### S1. AnalysisQualityChecker权重不合理

**现状**: structure 40% + caliber 30% + risk_disclosure 20% + quantified 10%（L408-411）

**问题**: caliber(数据口径声明)占30%——研报中大量数据不需要口径声明(如"70.05万辆"不需要GAAP/IFRS标注)

**⚠️ 交互冲突**: S3让"反证"匹配risk_disclosure→structure_found从3/4恢复到4/4→structure_score恢复满分。S1同时将structure从40%提到50%，两者叠加导致结构合规的章节仅靠结构就获50分(50%*100=50)，即使内容质量差也能得到不低的总分。**structure权重50%过高**。

**提升方案（修正）**: S3生效后，structure权重应保守设为45%而非50%：

```python
structure_score = self._check_structure(content) * 0.45   # 40→45（配合S3生效后保守调整）
caliber_score = self._check_caliber_coverage(content) * 0.20  # 30→20
risk_score = self._check_risk_disclosure(content) * 0.20      # 不变
quant_score = self._check_quantified_decomposition(content) * 0.15  # 10→15
```

**预期提升**: +1~2分（原+1~3偏乐观。caliber降权确实减少过度扣分，但structure升权配合S3生效后可能让结构合规但内容差的章节得分偏高，保守调整为45%）

#### S2. STRUCTURE_MARKERS的data_support关键词太宽泛

**现状**: L370 `"据"`作为关键词匹配"据2026年一季报"但也匹配"据了解"

**提升方案**: 收紧关键词，增加最小上下文长度：

```python
"data_support": {
    "keywords": ["数据来源", "数据支撑", "Source", "数据显示", "据统计", "据财报"],
    "min_context_chars": 50,  # 30→50
},
```

移除"据""来源""统计""调研"等单字/泛化词。

**⚠️ 修订要点**: 原方案包含"据XX数据显示""据财报"——但这些是动态模式而非固定关键词，无法直接放入keywords列表。简化为只保留固定关键词："数据来源""数据支撑""Source""数据显示""据统计""据财报"。移除"据""来源""统计""调研"。

**预期提升**: +0.5~1分

#### S3. "反证与边界条件"不属于risk_disclosure匹配范围

**现状**: v4各章都有"反证与边界条件"而非"风险提示"。`_check_structure`的STRUCTURE_MARKERS（L373-378）中risk_disclosure关键词不包含"反证""边界条件"

**影响分析**: `_check_structure`检测到4个结构标记中的3个（core_conclusion/argument_analysis/data_support），但miss了risk_disclosure，structure_found=3/4=75%，structure_score = 75% * 0.40 = 30分（而非满分40分）。仅此一项就丢失10分。

`_check_risk_disclosure`本身用梯度评分（L453-467），如果正文有"然而""如果...则"等转折词能获部分分（最高0.7*100*0.20=14分而非满分20分），但"反证与边界条件"段落中的风险内容不被识别。

**⚠️ 交互冲突（关键）**: S3让"反证"匹配risk_disclosure（过渡期兼容评分），等于告诉checker"反证是可接受的风险提示"。P1要消灭"反证"段落。两者同时生效时，LLM生成"反证"不会被AnalysisQualityChecker判违规（S3兼容了），也就没有动力改为"风险提示"（P1目标落空）。

**提升方案（修正）**: S3应仅在`_check_structure`中兼容（让structure_found=4/4恢复满分），但在`_check_risk_disclosure`中**降权**（0.6而非1.2），同时在P3的"结构合规度"维度明确：出现"反证"标题时合规度扣分。形成"程序化评分兼容但LLM审查评分扣分"的双重机制：

```python
"risk_disclosure": {
    "keywords": ["风险提示", "风险", "不确定性", "假设", "数据缺口",
                 "反证", "边界条件", "反面",  # 仅在_check_structure中兼容
                 "需要注意的是", "但需注意", "潜在风险"],
    "min_context_chars": 30,
    "exclude_trivial": True,
    "compatibility_note": "反证/边界条件仅在_check_structure中兼容（4/4结构完整），在_check_risk_disclosure中降权(0.6)",
},
```

在`_check_risk_disclosure`中为"反证""边界条件""反面"匹配降权：

```python
risk_indicators = [
    (r'(?:风险提示)[^。？！；…\n]{5,}', 1.2),
    (r'(?:风险|不确定性|数据缺口|假设前提)[^。？！；…\n]{10,}', 0.9),
    (r'(?:反证|边界条件|反面证据|反面)[^。？！；…\n]{10,}', 0.6),  # 新增：降权兼容
    (r'(?:然而|不过|但是|但需注意|需要注意的是)[^。？！；…\n]{10,}', 0.7),
    (r'(?:如果|若|当)[^。？！；…\n]{15,}(?:则|那么|可能|将|会)', 0.5),
]
```

同时P3的"结构合规度"维度应明确：
```
- 出现"反证""边界条件"等标题时，结构合规度扣分（即使内容是合理的风险讨论，标题不符合研报规范）
```

这样形成三层机制：
1. `_check_structure`：兼容"反证"→structure_found=4/4→不丢10分
2. `_check_risk_disclosure`：降权0.6→仍获部分分但低于"风险提示"的1.2权重
3. LLM reviewer结构合规度：明确扣分→强制LLM修正

**预期提升**: +3~5分（兼容期内structure_found从3/4恢复到4/4，structure_score恢复满分；降权+LLM扣分确保最终趋向"风险提示"）

---

## 2. 最终优先级排序

| 优先级 | 提升点 | 预期提升 | 确定性 | 涉及文件 | 说明 | 状态 |
|--------|--------|----------|--------|---------|------|------|
| **P0** | N1(程序化后处理) | +3~5分 | 中高 | orchestrator.py(新增) | 确定性最高但仍非100%，标题格式不规范等边界情况可能漏检 | ✅ |
| **P0** | A1(数据传递) | +2~4分 | 中 | models.py+orchestrator.py+chapter_writer.py+chapter_write.tmpl | 根因修复：修改L767保留data_points | ✅ |
| **P0** | P1+P3(黑名单+合规审查) | +1~3分 | 低 | chapter_write.tmpl+chapter_review.tmpl | 辅助手段，LLM遵从度不确定 | ✅ |
| **P1** | A3(程序化检查接入收敛) | +2~4分 | 高 | orchestrator.py+checkers.py | AnalysisQualityChecker作为硬约束参与收敛 | ✅ **已实现** — `_phase4_fix_and_optimize` 入口（L547-553）对每章运行 `AnalysisQualityChecker.check()`，<60分的强制加入 patch_chapter_ids |
| **P1** | E1(收敛阈值3) | +1~2分 | 高 | orchestrator.py | 首轮阈值从5改为3 | ✅ |
| **P1** | D2(StockData预注入) | +1~3分 | 中 | orchestrator.py | 方案B：保持static+加参数 | ⚠️ **skill_registry 参数是死代码**——`_extract_chapter_data` 签名含 `skill_registry=None`（L831）但函数体从未使用。StockData 注入仅通过 `StructuredDataRepairAgent` 在修复阶段触发（structured_data_repair.py:23-53），非预注入 |
| **P2** | S3(反证兼容risk)+S1(权重45%)+S2(关键词收紧) | +3~5分 | 高 | checkers.py | **A3实施后立即生效，不独立** | ✅ |
| **P2** | P5(全局审查看正文) | +1~2分 | 中 | global_reviewer.py | 首400+末400字摘要 | ✅ |
| **P2** | P2(逐段精修指令) | +1~2分 | 低 | chapter_write.tmpl | 依赖LLM遵从度 | 🔲 未实现 |
| **P2** | E3(退出条件+rewrite触发) | +1~2分 | 高 | orchestrator.py | 同步修改L182+L232 | ✅ |
| **P3** | E4(触发词) | +0~1分 | 中 | orchestrator.py | 排除"没有""无" | ✅ |
| **P3** | D1(跨章冲突) | +1~2分 | 中 | orchestrator.py | 口径差异标注 | 🔲 未实现 — ConflictResolver（data_repair.py:121-248）无 caliber 标注逻辑；DataRegistry._normalize_metric() 会混同不同口径的同一指标（如归母 vs 扣非） |
| **P3** | E5(patch精确数值) | +1~2分 | 中 | orchestrator.py | | ⚠️ **`chapter_data` 参数是死代码**——签名存在（L1058-1062）且调用点传入（L306-308, L669-670），但函数体从未引用 `chapter_data`，仅依赖 `raw_data_summary` 字符串匹配 |
| **P3** | D3(来源49修复) | +0.5~1分 | 高 | orchestrator.py | | ✅ |
| **P3** | P4(章内自洽性) | +0~1分 | 低 | chapter_review.tmpl | 依赖LLM reviewer | 🔲 未实现 — review template 无自洽性维度。代码级检查仅存在于 `_extract_and_validate_data_points` 的 DataRegistry 冲突检测，非 LLM 审查维度 |
| **P3** | P6(摘要结构) | +0~1分 | 低 | exec_summary.tmpl | 不影响章节分数 | ✅ |
| **P4** | E2(best_score防退) | 防回退 | 高 | orchestrator.py | L629改为严格大于比较 | ✅ |

### 预期效果（代码审查验证版）

- **已实现项（12/17）**: N1 + A1 + P1+P3 + A3 + E1 + S3/S1/S2 + P5 + E3 + E4 + D3 + P6 + E2
- **部分实现项（2/17）**: D2（skill_registry 参数存在但函数体未使用）+ E5（chapter_data 参数存在但函数体未使用）
- **未实现项（3/17）**: P2（逐段精修指令）+ D1（口径差异标注）+ P4（章内自洽性维度）

基于实际实施状态的预期分数：
- 已实现 12 项 + 2 项部分实现：78 → **83~90**
- 修复 D2/E5 + 实现 P2/D1/P4 后可到：**88~94**

---

## 3. 实施顺序

### Phase 1: P0三项（预期78→81~85）— ✅ 代码审查确认全部已实现

1. **新增**`_enforce_structure_compliance`程序化后处理（N1）——在`_chapter_writer.write()`返回后、`_chapter_reviewer.review()`之前调用
2. 修改`_split_chapter_data`(L767)保留data_points为upstream_data_points + `models.py`增加upstream_data_points字段 + `chapter_writer.py`传入 + `orchestrator.py`提取 + `chapter_write.tmpl`增加结构化数据引用段（A1）
3. 修改`chapter_write.tmpl`增加段落黑名单+白名单 **同时**修改`chapter_review.tmpl`增加"结构合规度"维度（P1+P3，辅助手段）

### Phase 2: P1三项（预期81~85→85~90）— ✅ A3/E1 已实现，⚠️ D2 需修复

4. 在`_phase4_fix_and_optimize`入口增加AnalysisQualityChecker硬约束检查（A3）**同时**修改checkers.py的S3(反证兼容risk+降权)+S1(权重45%)+S2(关键词收紧)——A3接入后S3/S1/S2立即生效。**代码审查确认 A3 已实现**（_phase4_fix_and_optimize L547-553）
5. 修改`orchestrator.py` RetryPolicy，首轮阈值从5改为3（E1）
6. **`_extract_chapter_data` 的 `skill_registry` 参数是死代码**——参数已在签名中（L831）但函数体从未使用。需实现实际的数据预注入逻辑使此参数生效（D2）

### Phase 3: P2四项（预期85~90→87~92）— ✅ P5/E3 已实现，🔲 P2 待实现

7. 修改`global_reviewer.py` serialize_report_for_review增加首400+末400字正文摘要（P5）
8. 修改`chapter_write.tmpl`增加"逐段精修指令"（P2）
9. 修改章节级review退出条件+L232 rewrite触发条件（E3）

### Phase 4: P3+P4剩余项（预期87~92→88~94）— ✅ E4/D3/P6/E2 已实现，🔲 D1/P4 待实现，⚠️ E5 需修复

10-15. 依次实施E4/D1(**需重构 ConflictResolver 增加 caliber 标注和 DataRegistry 口径区分**)/E5(**修复 chapter_data 死代码参数**)/D3/P4(**需在 chapter_review.tmpl 增加自洽性维度**)/P6/E2

---

## 4. 风险与注意事项

1. **N1与P1+P3目标重叠**：N1程序化后处理先修正结构→P3审查不再发现违规→P3扣分机制不起作用。这是预期行为：N1保底+P1+P3源头预防。预期提升取max而非求和。
2. **S3/S1/S2与A3捆绑**：S3/S1/S2只影响AnalysisQualityChecker，仅当A3接入收敛循环后有效。**A3已接入收敛循环**（_phase4_fix_and_optimize L547-553），S3/S1/S2已生效。
3. **A1实施需修改L767**：`_split_chapter_data`显式剥离data_points，必须先修改此处。上游不存在`key_conclusions`字段。注意：当raw_data不是dict时（走L752-763分支），refined只有{"content":...}，没有data_points，此时upstream_data_points为空。
4. **E3防无限循环**：60-79分段最多2轮后必须退出，且需同步修改L232的rewrite触发条件。**代码审查确认已实现**。
5. **E4误判风险**：排除"没有""无"，避免正常描述被误判为数据缺失。**代码审查确认正确实现**。
6. **E1成本风险**：降低首轮阈值可能增加收敛轮数和LLM调用成本。但v4实际只跑了1轮就停滞，E1让第2轮有机会执行，而非无限制循环。
7. **P5增加token消耗**：首400+末400字*3章≈2400字额外上下文。
8. **D2 `skill_registry` 死代码**：`_extract_chapter_data` 签名含 `skill_registry=None` 参数（L831），调用点传入（L234/563/653），但函数体从未使用。需修复实现实际的数据预注入逻辑。
9. **分数不可比**：P3改变了reviewer评分维度，修改后分数与v4的78分不在同一标尺。
10. **E2简化方案**：L629改为严格大于比较(>而非>=)，避免相同分数时无意义替换。无需额外LLM调用。**代码审查确认已正确实现**。
11. **E5 `chapter_data` 死代码**：`_build_anchor_patch_instructions` 的 `chapter_data` 参数签名存在（L1060），调用点传入（L306-308, L669-670），但函数体从未使用。需修复实现实际的数据点精确查找逻辑。

## 5. 自审记录

| 条目 | 文档断言 | 代码实际 | 结论 |
|------|---------|---------|------|
| E2 | "L629只比较rewrite_review.score >= re_review.score，不与best_score比较" | `_phase4_fix_and_optimize`内无best_score变量 | **修正**: 改为"函数内没有best_score跟踪机制"，方案改为引入chapter_best_scores |
| E3 | "如果best_score已经>=80，仍在review循环中" | review.score>=60就会break退出循环 | **修正**: 实际问题是60-79分段过早退出，而非>=80不退出。方案改为区分"可接受"与"达标" |
| D2 | 代码示例用`self._skill_registry` | `_extract_chapter_data`是`@staticmethod` | **修正**: 增加注意事项，提供方案A(改实例方法)和方案B(加参数) |
| S3 | "risk_disclosure得分可能为0" | `_check_risk_disclosure`用梯度评分，"然而""如果...则"等能获部分分 | **修正**: 改为"structure_found=3/4=75%，丢失10%structure权重"，补充影响分析 |
| P1 | "LLM仍生成反证与边界条件" | v4报告3个章节均有此类段落 | ✅ 确认正确 |
| P3 | "5个审查维度，不审查结构合规性" | chapter_review.tmpl L27-50确认5维度 | ✅ 确认正确 |
| P5 | "serialize_report_for_review只输出标题+结论+数据点" | global_reviewer.py L125-137确认 | ✅ 确认正确 |
| E1 | "MIN_CONVERGENCE_IMPROVEMENT=5" | orchestrator.py L48确认 | ✅ 确认正确 |
| E4 | "只有4个触发词" | L880确认"缺乏/缺失/未标注/缺口" | ✅ 确认正确 |
| D3 | "来源49模糊来源" | e2e_v4_report.json确认 | ✅ 确认正确 |
| S1 | "structure 40% + caliber 30%" | checkers.py L408-411确认 | ✅ 确认正确 |
| S2 | "据作为关键词匹配据了解" | checkers.py L370确认"据"在keywords中 | ✅ 确认正确 |
| A1 | "分析Agent的data_points没有传递给chapter_writer" | L134只取chapter_data.get("content") | ✅ 确认正确 |

### 审计2 (2026-06-27): 第二轮深度审查修订

| 条目 | 原文档问题 | 修订内容 | 代码依据 |
|------|-----------|---------|---------|
| P1 | 预期+5~8分偏乐观；未注意L67已有同类指令 | 降为+2~4分；标注必须配合P3 | chapter_write.tmpl:67已有"正文中不要出现反证边界条件" |
| P2 | "禁止重排段落顺序"与结构合规修正矛盾 | 改为"允许违规段落收拢到风险提示" | 结构违规需将"反证"段落移到末尾"风险提示" |
| P3 | 预期+3~5分偏乐观 | 降为+2~3分；标注是P1生效的必要保障 | 依赖LLM reviewer执行扣分 |
| E1 | 首轮阈值不变(ROUND1=5)，无法解决v4问题 | 首轮阈值改为3 | v4卡在round_idx=0，原方案首轮仍用5 |
| E3 | 方案遗漏L232 rewrite触发条件 | 同步修改L232为`best_score < TARGET_SCORE` | L232只在`best_score < 60`时rewrite，60-79分段空转 |
| E4 | "没有""无"会大量误判 | 排除"没有""无" | 日常中文极常见（"无明显风险"） |
| S1 | structure提到50%与S3叠加过高 | 降为45% | S3让structure满分恢复+50%权重=内容差也能高分 |
| S3 | 与P1目标矛盾（兼容"反证"→LLM无动力改） | 三层机制：check_structure兼容+check_risk降权0.6+LLM审查扣分 | 需要同时满足评分恢复和强制修正 |
| P5 | 前500字可能遗漏末尾风险提示 | 改为首400+末400字 | chapter_write.tmpl:66要求风险提示在末尾 |
| E2 | 优先级偏高 | 从P3降为P4 | 外层收敛循环已有best_chapters保底 |
| A1 | 预期+2~4偏保守；优先级偏低 | 改为+3~5分；从P3提前到P1 | 数据传递断裂是根本问题 |
| D2 | 推荐方案A | 推荐方案B（改动更小） | 方案A需改3个调用点，方案B只加参数 |

### 审计3 (2026-06-27): 第三轮代码深度验证

| 条目 | 验证内容 | 代码实际 | 结论 |
|------|---------|---------|------|
| A1 | `chapter_data.get("data_points")`是否可行 | `_split_chapter_data` L767: `if k == "data_points": continue` **显式剥离** | **严重错误**: chapter_data永远不含data_points，原方案不可行。修正：修改L767保留data_points为upstream_data_points |
| A1 | 上游是否存在`key_conclusions`字段 | grep result_aggregator.py确认无此字段 | **错误**: `key_conclusions`是ChapterWriteOutput属性，非上游数据。修正：ChapterWriteInput只增加upstream_data_points，去掉upstream_key_conclusions |
| E3 | L182退出后L232 rewrite是否可达 | L182: `score>=60→break`，L232: `best_score<60→rewrite` | ✅ 修订正确：60-79分段退出循环且不触发rewrite，形成"空转" |
| E2 | 外层收敛循环是否保底 | L393: `if current_score > best_score: best_chapters=list(chapters)` | ✅ 修订正确：外层用`>`（严格大于）比较，相同分数不替换，退化版本被保底 |
| P1 | L67已有禁止指令 | `chapter_write.tmpl:67`: "正文中不要出现'反证''边界条件'" | ✅ 修订正确：已有指令被LLM无视，黑名单增强需配合P3 |
| S3 | S3与P1冲突分析 | AnalysisQualityChecker(program化) ≠ chapter_reviewer(LLM) | ✅ 三层机制合理：程序化兼容+降权+LLM扣分，三者独立 |
| P5 | 风险提示是否在章节末尾 | v4第1章结构：核心判断→逻辑推导→数据支撑→**反证与边界条件**→**决策启示** | ✅ 修订正确：末尾400字能捕获"反证""决策启示" |
| E1 | v4卡在round_idx=0 | L403: `improvement < MIN_CONVERGENCE_IMPROVEMENT(5)` | ✅ 修订正确：首轮阈值5导致停滞，改为3可解决 |

### 审计4 (2026-06-27): 评分体系不一致+优先级重建

| 发现 | 影响 | 处理 |
|------|------|------|
| 78分来自LLM reviewer，不是AnalysisQualityChecker | S3/S1/S2对78分无效 | S3/S1/S2与A3捆绑在Phase 2 |
| L67已有禁止指令被LLM无视 | P1黑名单预期从+5~8降为+1~3 | 新增N1程序化后处理为P0 |
| P3改变reviewer评分维度 | 修改后分数与78不可比 | 在§4风险中标注 |
| E1阈值5导致首轮停滞 | 第二轮未有机会尝试 | A1数据传递提升为P0（根因修复）+E1阈值降为3 |

### 审计5 (2026-06-27): 前后矛盾消除

| 矛盾 | 位置 | 处理 |
|------|------|------|
| §2旧优先级表(S3为P0)与§7新表(S3降级)共存 | §2 vs §7 | 删除旧§2表，统一为§2最终版 |
| §3旧Phase 1-4与§8新Phase 1-4冲突 | §3 vs §8 | 删除旧§3，统一为§3最终版 |
| §4旧风险10条与新风险9条冲突 | §4 | 统一为§4最终版 |
| §6/7/8与§2/3/4内容重复 | §6-8 | 删除§6-8，结论已回写§2-4 |
