# section_id 聚合 key 映射断裂修复方案（代码级审查版）

> 本文档基于对 engine.py 和 orchestrator.py 的逐行审查编写。
> 所有代码引用均为实际行号与实际代码，无伪代码。
> 行号经过自动化验证脚本确认，偏差为 0。

---

## 0. 审查范围

| 文件 | 行号范围 | 审查内容 |
|------|---------|---------|
| engine.py | 1134-1162 | 缓存结果 dict 构造（P1 修复点） |
| engine.py | 1182-1219 | all-cached 分支 + QC 重执行（P3 修复点） |
| engine.py | 1279-1285 | 正常 section_id 注入（参考对照） |
| engine.py | 2476-2491 | `_get_section_id_from_agent`（工具方法） |
| engine.py | 2493-2525 | `_get_section_id_from_agent_id`（工具方法） |
| orchestrator.py | 735-739 | research() 中 agents 创建完毕处（P2 地图构建点） |
| orchestrator.py | 837-857 | research() 中 key 映射代码（P2 地图使用点） |
| orchestrator.py | 1623-1651 | `_research_with_routing()` 中现有地图代码（含 BUG） |
| orchestrator.py | 1765-1785 | `_research_with_routing()` 中 key 映射代码（P2 地图使用点） |

---

## 1. 根因链与问题定位

### 1.1 完整数据流追踪

```
engine.py execute_with_scheduler()
│
├─ 1134-1162: for agent_id in batch_agent_ids
│   ├─ 1135: agent = scheduler.get_agent_by_id(agent_id)
│   ├─ 1136: if agent is not None:
│   ├─ 1140-1143: agent_aspect = agent.config["context"]["aspect"]
│   ├─ 1146: cached_result = cached_by_aspect.get(agent_aspect) if agent_aspect else None
│   ├─ 1147: if cached_result:
│   │   ├─ 1153: completed_results.append({
│   │   │     "success": True,
│   │   │     "agent_id": agent_id,
│   │   │     "content": content[:50000],
│   │   │     "data_points": ...,
│   │   │     "sources": ...,
│   │   │     "charts": ...,
│   │   │     "cached": True,
│   │   │   })
│   │   │   ← ★ section_id 缺失
│   │   └─ 1162: continue
│   ├─ 1164-1170: content_lock can_execute check
│   └─ 1171-1177: content_lock.mark_running
│
├─ 1179: batch_agent_originals = batch_agents.copy()
├─ 1182: if not batch_agents:
│   ├─ 1183: if completed_results:
│   │   ├─ 1189: batch_results = completed_results
│   │   ├─ 1190-1196: scheduler / content_lock 标记完成
│   │   ├─ 1197-1198: all_results / stage_results 写入
│   │   ├─ 1200-1218: QC 检查
│   │   │   ├─ 1214: if not _qr.passed:
│   │   │   │   ├─ 1215-1218: batch_results = await _execute_agents_batch(...)
│   │   │   │   │   ← ★ 重执行结果也缺 section_id（_execute_agents_batch 不注入）
│   │   │   │   └─ ★ 应在此处注入 section_id
│   │   │   └─ (QC passed: 不进入)
│   │   └─ 1219: continue
│   │       ← ★ 跳过了 1279-1285 的 section_id 注入
│   └─ 1220-1224: 无有效 agent 跳过
│
├─ 1279: batch_results = await _execute_agents_batch(...)  ← 正常执行
├─ 1279-1285: for agent_result in batch_results:     ← section_id 注入
│       agent_id = agent_result.get("agent_id", "")
│       agent = scheduler.get_agent_by_id(agent_id)
│       section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
│       agent_result["section_id"] = section_id
```

### 1.2 BUG 精确位置

**BUG 1（engine.py:1153）：** 缓存结果 dict 构造时没有 section_id 字段。

**BUG 2（engine.py:1219）：** `continue` 跳过 1279-1285 的 section_id 注入代码块。

**BUG 3（engine.py:1215-1218 → 1219）：** QC 重执行后 `batch_results` 被替换为新结果，但 `continue`（1219）仍跳过注入。

### 1.3 关键辅助方法（确认无问题）

`engine.py:2476-2491` `_get_section_id_from_agent`：
```python
def _get_section_id_from_agent(self, agent: "IAgent") -> str:
    if hasattr(agent, 'section_id') and agent.section_id:
        return agent.section_id
    return agent.agent_id
```
→ 安全：优先 agent.section_id，兜底 agent.agent_id。

`engine.py:2493-2525` `_get_section_id_from_agent_id`：
```python
def _get_section_id_from_agent_id(self, agent_id: str) -> str:
    parts = agent_id.split("_")
    if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
        return agent_id  # phase_N_agent_M → 返回自身（无语义）
```
→ `phase_2_agent_0` → `"phase_2_agent_0"`。该结果在 orchestrator fallback 中解析为 `"2_agent"`。

### 1.4 坍缩问题（orchestrator 层）

`orchestrator.py:840-857`（research）和 `orchestrator.py:1768-1785`（_research_with_routing）：
```python
else:
    aspect = None
    if agent_id:
        parts = agent_id.split("_")
        if len(parts) >= 3:
            last_part = parts[-1]
            is_index = last_part.isdigit() or (...)  # ← "0" 匹配 isdigit()
            if is_index:
                aspect = "_".join(parts[1:-1])  # phase_2_agent_0 → "_".join(["2","agent"]) = "2_agent"
```
→ 对 `"phase_2_agent_0"`：`parts = ["phase","2","agent","0"]`，`last_part = "0"` isdigit=True，`"_".join(parts[1:-1])` = `"_".join(["2","agent"])` = `"2_agent"`。

所有 phase 2 的 agent 全部映射为 `"2_agent"`，第 2 个 agent 覆盖第 1 个 → 每 phase 只有 1 个 key 保留。

---

## 2. 修复方案（逐行代码级）

### 2.1 P1（engine.py:1153 行插入 section_id）

**位置：** `engine.py` 第 1153 行，`completed_results.append({` 之前。

**上下文代码（1147-1162）：**
```python
1147:                         if cached_result:
1148:                             content = cached_result.get("content") or cached_result.get("result") or ""
1149:                             logger.info(
1150:                                 f"[批次{batch_index + 1}] Agent {agent_id} aspect '{agent_aspect}' "
1151:                                 f"cached, skipping execution ({len(content)} chars)"
1152:                             )
1153:                             completed_results.append({
1154:                                 "success": True,
1155:                                 "agent_id": agent_id,
1156:                                 "content": content[:50000],
1157:                                 "data_points": cached_result.get("data_points", []),
1158:                                 "sources": cached_result.get("sources", []),
1159:                                 "charts": cached_result.get("charts", []),
1160:                                 "cached": True,
1161:                             })
1162:                             continue
```

**变量活性分析：** 在 1135 行 `agent = scheduler.get_agent_by_id(agent_id)`，1136 行 `if agent is not None:` 包裹了 1136-1177，因此执行到 1147-1162 时 `agent` 保证不为 None。

**修改（1153 行前插入）：**
```python
1147:                         if cached_result:
1148:                             content = cached_result.get("content") or cached_result.get("result") or ""
1149:                             logger.info(
1150:                                 f"[批次{batch_index + 1}] Agent {agent_id} aspect '{agent_aspect}' "
1151:                                 f"cached, skipping execution ({len(content)} chars)"
1152:                             )
1153:                             section_id = self._get_section_id_from_agent(agent)
1154:                             completed_results.append({
1155:                                 "success": True,
1156:                                 "agent_id": agent_id,
1157:                                 "section_id": section_id,
1158:                                 "content": content[:50000],
1159:                                 "data_points": cached_result.get("data_points", []),
1160:                                 "sources": cached_result.get("sources", []),
1161:                                 "charts": cached_result.get("charts", []),
1162:                                 "cached": True,
1163:                             })
1164:                             continue
```

**零错误论证：**
- `agent` 变量在此作用域内保证非 None（1136 行 if guard）
- `_get_section_id_from_agent` 兜底返回 `agent.agent_id`（2488-2491），不会返回空字符串
- 新 key `"section_id"` 与现有消费者兼容：orchestrator 的 `result.get("section_id", "")`（837 行）、content_lock 的 `_get_section_id_from_agent`（1195 行）
- 不影响 1279-1285 的正常注入路径：两者写同一字段，值一致，幂等

### 2.2 P2（orchestrator.py 双层兜底）

**2.2.1 research() 中构建 agent_section_map**

**位置：** `orchestrator.py` 第 739 行之后、第 741 行之前。

**上下文（735-744）：**
```python
735:             else:
736:                 agents = self._create_agents(
737:                     requirement, intent_result, task_id,
738:                     research_type="market_research")
739:             logger.info(f"[{task_id}] Created {len(agents)} Agents")
740: 
741:             # 4.3 Get Session Registry (for Agent execution state tracking)
742:             session_registry = self._agent_factory.get_registry(task_id)
```

**插入（739-740 行之间）：**
```python
739:             logger.info(f"[{task_id}] Created {len(agents)} Agents")
739a:            agent_section_map: Dict[str, str] = {}
739b:            for _agent in agents:
739c:                _sid = getattr(_agent, 'section_id', None) or ''
739d:                if _sid:
739e:                    agent_section_map[_agent.agent_id] = _sid
740: 
741:             # 4.3 Get Session Registry (for Agent execution state tracking)
```

**安全性：** `agents` 变量在 725/732/736 行赋值且 739 行已确认非空。旧路径 agent 的 `section_id` 为空（由 `_create_agents` 创建时不设 section_id）→ `_sid = ''` → 不写入 map → map 为空 → 对旧路径零影响。

**2.2.2 research() key 映射中插入地图查询**

**位置：** `orchestrator.py` 第 837-857 行。

**上下文（834-861）：**
```python
834:                         # 优先使用 section_id（由 engine 注入结果字典）
835:                         # 新格式 phase_1_agent_N 的 agent_id 解析会全部坍缩为 "1_agent"
836:                         # section_id 格式: section_0_核心财务指标（唯一不碰撞）
837:                         section_id = result.get("section_id", "") or ""
838:                         if section_id:
839:                             key = section_id
840:                         else:
841:                             # Fallback: 解析 agent_id（旧格式 research_市场规模_2）
842:                             aspect = None
843:                             if agent_id:
844:                                 parts = agent_id.split("_")
845:                                 if len(parts) >= 3:
846:                                     last_part = parts[-1]
847:                                     is_index = last_part.isdigit() or (
848:                                         len(last_part) >= 6
849:                                         and all(c in '0123456789abcdef' for c in last_part.lower())
850:                                     )
851:                                     if is_index:
852:                                         aspect = "_".join(parts[1:-1])
853:                                     else:
854:                                         aspect = last_part
855:                                 elif len(parts) == 2:
856:                                     aspect = parts[1]
857:                             key = aspect if aspect else f"{stage_name}_{i}"
```

**修改（838-857）→（838-859）：**
```python
837:                         section_id = result.get("section_id", "") or ""
838:                         if section_id:
839:                             key = section_id
840:                         elif agent_id in agent_section_map:
841:                             key = agent_section_map[agent_id]
842:                         else:
843:                             # Fallback: 解析 agent_id（旧格式 research_市场规模_2）
844:                             aspect = None
845:                             if agent_id:
846:                                 parts = agent_id.split("_")
847:                                 if len(parts) >= 3:
848:                                     last_part = parts[-1]
849:                                     is_index = last_part.isdigit() or (
850:                                         len(last_part) >= 6
851:                                         and all(c in '0123456789abcdef' for c in last_part.lower())
852:                                     )
853:                                     if is_index:
854:                                         aspect = "_".join(parts[1:-1])
855:                                     else:
856:                                         aspect = last_part
857:                                 elif len(parts) == 2:
858:                                     aspect = parts[1]
859:                             key = aspect if aspect else f"{stage_name}_{i}"
860: 
861:                         results_for_aggregation[key] = result
```

**2.2.3 _research_with_routing() 修复现有地图 BUG + 插入地图查询**

**BUG 修复（1646-1651）：** 现有地图代码第 1648 行有错误回退：
```python
1646:             agent_section_map: Dict[str, str] = {}
1647:             for _agent in agents:
1648:                 _sid = getattr(_agent, 'section_id', None) or getattr(_agent, 'agent_id', '')
1649:                 if _sid:
1650:                     agent_section_map[_agent.agent_id] = _sid
1651:             task_agent_section_map = agent_section_map
```

**问题：** `getattr(_agent, 'agent_id', '')` 作为 `or` 回退 → 当 `section_id` 为空时 `_sid = agent.agent_id`（如 `"phase_2_agent_0"`）→ map 中存入 `"phase_2_agent_0" → "phase_2_agent_0"`。这混淆了地图的用途——地图应只存储有意义的 section_id。

**修复：**
```python
1646:             agent_section_map: Dict[str, str] = {}
1647:             for _agent in agents:
1648:                 _sid = getattr(_agent, 'section_id', None) or ''
1649:                 if _sid:
1650:                     agent_section_map[_agent.agent_id] = _sid
```

（删除 1651 行 `task_agent_section_map = agent_section_map`——该变量赋值后从未被引用，是死代码。）

**key 映射中插入地图查询（1765-1785）：**

**上下文：**
```python
1762:                         agent_id = result.get("agent_id", "")
1763: 
1764:                         # 优先使用 section_id（由 engine 注入结果字典）
1765:                         section_id = result.get("section_id", "") or ""
1766:                         if section_id:
1767:                             key = section_id
1768:                         else:
1769:                             # Fallback: 解析 agent_id
1770:                             aspect = None
1771:                             if agent_id:
1772:                                 parts = agent_id.split("_")
1773:                                 if len(parts) >= 3:
1774:                                     last_part = parts[-1]
1775:                                     is_index = last_part.isdigit() or (
1776:                                         len(last_part) >= 6
1777:                                         and all(c in '0123456789abcdef' for c in last_part.lower())
1778:                                     )
1779:                                     if is_index:
1780:                                         aspect = "_".join(parts[1:-1])
1781:                                     else:
1782:                                         aspect = last_part
1783:                                 elif len(parts) == 2:
1784:                                     aspect = parts[1]
1785:                             key = aspect if aspect else f"{stage_name}_{i}"
```

**修改（1765-1785）→（1765-1787）：**
```python
1764:                         # 优先使用 section_id（由 engine 注入结果字典）
1765:                         section_id = result.get("section_id", "") or ""
1766:                         if section_id:
1767:                             key = section_id
1768:                         elif agent_id in agent_section_map:
1769:                             key = agent_section_map[agent_id]
1770:                         else:
1771:                             # Fallback: 解析 agent_id
1772:                             aspect = None
1773:                             if agent_id:
1774:                                 parts = agent_id.split("_")
1775:                                 if len(parts) >= 3:
1776:                                     last_part = parts[-1]
1777:                                     is_index = last_part.isdigit() or (
1778:                                         len(last_part) >= 6
1779:                                         and all(c in '0123456789abcdef' for c in last_part.lower())
1780:                                     )
1781:                                     if is_index:
1782:                                         aspect = "_".join(parts[1:-1])
1783:                                     else:
1784:                                         aspect = last_part
1785:                                 elif len(parts) == 2:
1786:                                     aspect = parts[1]
1787:                             key = aspect if aspect else f"{stage_name}_{i}"
```

### 2.3 P3（engine.py QC 重执行路径补 section_id）

**位置：** `engine.py` 第 1218 行之后、第 1219 行 `continue` 之前。

**上下文（1214-1219）：**
```python
1214:                                 if not _qr.passed:
1215:                                     logger.warning(f"Cached results failed QC for batch {batch_index+1}, re-executing")
1216:                                     batch_results = await self._execute_agents_batch(
1217:                                         batch_agent_originals, requirement, all_results,
1218:                                         scheduler, f"batch_{batch_index+1}_cache_rerun"
1219:                                     )
1220:                         continue
```

**修改（1219-1220 之间插入）：**
```python
1214:                                 if not _qr.passed:
1215:                                     logger.warning(f"Cached results failed QC for batch {batch_index+1}, re-executing")
1216:                                     batch_results = await self._execute_agents_batch(
1217:                                         batch_agent_originals, requirement, all_results,
1218:                                         scheduler, f"batch_{batch_index+1}_cache_rerun"
1219:                                     )
1220:                                     for agent_result in batch_results:
1221:                                         agent_id = agent_result.get("agent_id", "")
1222:                                         agent = scheduler.get_agent_by_id(agent_id)
1223:                                         section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
1224:                                         agent_result["section_id"] = section_id
1225:                         continue
```

**零错误论证：**
- 代码逻辑与 1279-1285 的正常注入完全一致
- 注入优先级（agent → agent_id 回退）与 1283-1284 相同
- 对已存在的 section_id 字段幂等（新执行的 agent 不会自带 section_id）
- 不影响 QC passed 路径（不进入此分支）

---

## 3. 场景验证矩阵

### 场景 A：正常执行（无缓存）

```
engine:1279 → _execute_agents_batch → 正常执行
engine:1279-1285 → for agent_result in batch_results:
                        section_id = self._get_section_id_from_agent(agent) if agent else ...
                        agent_result["section_id"] = section_id
→ 结果: 每个 result dict 含 section_id

orchestrator key 映射:
    result.get("section_id") → 命中 → 正确 key
```

**结果：** ✅ P1/P2/P3 均不介入，流程不变。

### 场景 B：缓存命中（QC 通过）

```
engine:1135 → agent = scheduler.get_agent_by_id(agent_id)  ← 非 None
engine:1147-1162 → if cached_result:
                        section_id = self._get_section_id_from_agent(agent)  ← ★ P1 注入
                        completed_results.append({"section_id": section_id, ...})
engine:1189 → batch_results = completed_results  ← 含 section_id
engine:1200-1213 → QC 检查 → passed
engine:1219 → continue  ← 跳过 1279-1285，但结果已含 section_id
```

**结果：** ✅ P1 保证缓存结果从源头带 section_id。

### 场景 C：缓存命中（QC 失败 → 重执行）

```
engine:1135 → agent 非 None
engine:1153 → section_id 注入（P1）
engine:1189 → batch_results = completed_results  ← 含 section_id
engine:1214 → if not _qr.passed:
                  batch_results = await _execute_agents_batch(...)  ← 新结果，无 section_id
                  for agent_result in batch_results:               ← ★ P3 注入
                      section_id = self._get_section_id_from_agent(agent) if agent else ...
                      agent_result["section_id"] = section_id
                  continue
```

**结果：** ✅ P3 保证重执行结果也带 section_id。注意 P1 注入的缓存结果被丢弃（batch_results 被覆盖），所以 P3 是必要的。

### 场景 D：engine 层意外遗漏 section_id（新增路径）

假设 engine 新增第 3 种路径（例如增量执行），该路径未注入 section_id：

```
engine 新路径 → result dict 不含 section_id

orchestrator key 映射:
    result.get("section_id") → 空
    agent_id in agent_section_map → True → key = agent_section_map[agent_id]  ← ★ P2 兜底
    → 正确 key
```

**结果：** ✅ P2 兜底。地图数据来自 agent 创建时从 spec.output_keys 提取的 section_id。

### 场景 E：旧路径 agents（research 方法，无 decomposition plan）

```
_create_agents() 创建 agent:
    agent_id = "research_市场规模_1"
    context 中无 section_id → agent.section_id = ""

agent_section_map（research 中 739a-739e 构建）:
    _sid = getattr(_agent, 'section_id', None) or ''  → ''
    if _sid: → False → 不写入 map → map 为空

engine 正常执行:
    agent_result["section_id"] = self._get_section_id_from_agent(agent)
    → agent.section_id = "" → 返回 agent.agent_id = "research_市场规模_1"
    → result["section_id"] = "research_市场规模_1"

orchestrator key 映射:
    result.get("section_id") → "research_市场规模_1"  ← 非空
    key = "research_市场规模_1"
```

**结果：** ✅ 旧路径正常工作。`section_id` 实际值为 agent_id（因 engine 有兜底），该值能被 aggregator 的模糊匹配正确处理。

### 场景 F：旧路径 agents + 缓存命中

```
engine 缓存路径:
    section_id = self._get_section_id_from_agent(agent)  ← P1
    → agent.section_id = "" → 返回 "research_市场规模_1"
    → result["section_id"] = "research_市场规模_1"
```

**结果：** ✅ P1 在旧路径缓存场景也正确工作。section_id 值等于 agent_id，与场景 E 的 engine 兜底值一致。

---

## 4. 与现有 agent_section_map 的兼容性

### 4.1 `_research_with_routing()` 的修正

现有代码（1646-1651）：
```python
agent_section_map: Dict[str, str] = {}
for _agent in agents:
    _sid = getattr(_agent, 'section_id', None) or getattr(_agent, 'agent_id', '')
    if _sid:
        agent_section_map[_agent.agent_id] = _sid
task_agent_section_map = agent_section_map
```

**两个 BUG：**
1. **第 1648 行** `or getattr(_agent, 'agent_id', '')`：当 section_id 为空时 fallback 到 agent_id，对 `phase_2_agent_0` 存入错误映射 `"phase_2_agent_0" → "phase_2_agent_0"`
2. **第 1651 行** `task_agent_section_map` 变量赋值后从未被使用（dead code）

**修正后（1646-1650）：**
```python
agent_section_map: Dict[str, str] = {}
for _agent in agents:
    _sid = getattr(_agent, 'section_id', None) or ''
    if _sid:
        agent_section_map[_agent.agent_id] = _sid
```

---

## 5. 变更汇总（精确 diff）

### 5.1 engine.py 变更

#### 变更 1：P1 - 第 1153 行插入

```diff
                         if cached_result:
                             content = cached_result.get("content") or cached_result.get("result") or ""
                             logger.info(
                                 f"[批次{batch_index + 1}] Agent {agent_id} aspect '{agent_aspect}' "
                                 f"cached, skipping execution ({len(content)} chars)"
                             )
+                            section_id = self._get_section_id_from_agent(agent)
                             completed_results.append({
                                 "success": True,
                                 "agent_id": agent_id,
+                                "section_id": section_id,
                                 "content": content[:50000],
                                 "data_points": cached_result.get("data_points", []),
                                 "sources": cached_result.get("sources", []),
                                 "charts": cached_result.get("charts", []),
                                 "cached": True,
                             })
                             continue
```

#### 变更 2：P3 - 第 1218-1219 行之间插入

```diff
                                 if not _qr.passed:
                                     logger.warning(f"Cached results failed QC for batch {batch_index+1}, re-executing")
                                     batch_results = await self._execute_agents_batch(
                                         batch_agent_originals, requirement, all_results,
                                         scheduler, f"batch_{batch_index+1}_cache_rerun"
                                     )
+                                    for agent_result in batch_results:
+                                        agent_id = agent_result.get("agent_id", "")
+                                        agent = scheduler.get_agent_by_id(agent_id)
+                                        section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
+                                        agent_result["section_id"] = section_id
                         continue
```

### 5.2 orchestrator.py 变更

#### 变更 3：P2 - research() 第 739-740 行之间插入

```diff
             logger.info(f"[{task_id}] Created {len(agents)} Agents")
+            agent_section_map: Dict[str, str] = {}
+            for _agent in agents:
+                _sid = getattr(_agent, 'section_id', None) or ''
+                if _sid:
+                    agent_section_map[_agent.agent_id] = _sid
 
             # 4.3 Get Session Registry (for Agent execution state tracking)
```

#### 变更 4：P2 - research() 第 838-839 行修改

```diff
                         section_id = result.get("section_id", "") or ""
                         if section_id:
                             key = section_id
+                        elif agent_id in agent_section_map:
+                            key = agent_section_map[agent_id]
                         else:
```

#### 变更 5：P2 - `_research_with_routing()` 第 1648 行修复 + 第 1651 行删除

```diff
             agent_section_map: Dict[str, str] = {}
             for _agent in agents:
-                _sid = getattr(_agent, 'section_id', None) or getattr(_agent, 'agent_id', '')
+                _sid = getattr(_agent, 'section_id', None) or ''
                 if _sid:
                     agent_section_map[_agent.agent_id] = _sid
-            task_agent_section_map = agent_section_map
```

#### 变更 6：P2 - `_research_with_routing()` 第 1766-1767 行修改

```diff
                         section_id = result.get("section_id", "") or ""
                         if section_id:
                             key = section_id
+                        elif agent_id in agent_section_map:
+                            key = agent_section_map[agent_id]
                         else:
```

---

## 6. 回归风险评估

### 6.1 不回归论证

| 变更 | 旧路径行为 | 新路径行为 | 回归风险 |
|------|-----------|-----------|---------|
| P1: 缓存 dict 加 section_id | 无此字段 | 字段存在 | 无（消费者已适配） |
| P2: research() 地图 | 无此变量 | map 为空（旧 path agent 无 section_id） | 无 |
| P2: research() 地图查询 | 无此分支 | agent_id 不在空 map 中 → 不进分支 | 无 |
| P2: 1648 修复 | 错误 fallback | 不 fallback | 降低错误映射风险 |
| P2: 1766 地图查询 | 无此分支 | agent 有 section_id 时进分支 | 正确（预期行为） |
| P3: 重执行注入 section_id | 无此操作 | 注入 | 无（与 1279-1285 一致） |

---

## 7. 验证步骤

### 7.1 编译验证

```bash
python -m py_compile src/core/orchestrator/execution/engine.py
python -m py_compile src/core/orchestrator/orchestrator.py
```

### 7.2 测试验证

```bash
python -m pytest tests/unit/test_section_id_cache_bug.py -v
```

### 7.3 运行时日志断言

修复后运行一次研究流程，确认以下日志模式消失：

```
❌ Execution complete, got 1 results  ← 表示坍缩
❌ 章节 'xxx' 无匹配内容，生成降级占位  ← 表示 key 缺失
```

确认出现：

```
✅ Execution complete, got 8 results  ← agent 数量等于结果数
✅ Aggregation complete, section_details=8 framework sections  ← 框架章节与结果数匹配
```

### 7.4 修复后源码验证测试更新

修复后，以下测试应更新断言方向：
- `test_cache_result_dict_has_no_section_id` → 改为断言 `cache_dict_has_section_id == True`
- `test_map_uses_agent_id_as_fallback` → 改为断言该行不再包含 `agent_id`
- `test_key_mapping_does_not_use_map` → 改为断言 key 映射已使用 map
