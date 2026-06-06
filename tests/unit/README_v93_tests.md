# v9.3 TDD Test Documents — Overview

## File Inventory

| 文件 | Track | 测试数 | RED | 通过 | 说明 |
|------|-------|--------|-----|------|------|
| `test_v93_normalize_score.py` | A1/A2/A3 | 19 | 18 | 1 | normalize + score_scale + content_lock |
| `test_v93_methodology_token.py` | A4 | 6 | 6 | 0 | 方法论 150→800 |
| `test_v93_fusion_weights.py` | A5 | 5 | 1 | 4 | 融合权重配置化 |
| `test_v93_self_assessment.py` | A7 | 6 | 5 | 1 | 自评指令 |
| `test_v93_hibernate_cleanup.py` | A8 | 6 | 6 | 0 | 持久化清理 |
| `test_v93_s1_semantic_gap.py` | A9 | 11 | 2 | 9 | S1 语义升级 |

**合计**: 53 测试 (42 RED, 11 GREEN)

## RED 失败类型

| 失败原因 | 测试数 | 实现动作 |
|----------|--------|---------|
| `ModuleNotFoundError: normalizer` | 7 | 新建 `src/core/quality/normalizer.py` |
| `AttributeError: score_scale` | 1 | `checkers.py:QualityResult` 增加字段 |
| `TypeError: score_scale kwarg` | 3 | 同上 |
| `AttributeError: _normalize_threshold` | 6 | `content_lock.py` 新增方法 |
| `KeyError: 'content'` | 6 | `generic_agent.py:2915` 改多框架逻辑 |
| `AttributeError: FUSION_WEIGHTS` | 1 | `quality_check_agent.py` 增加常量 |
| `AttributeError: _self_evaluate` | 1 | `generic_agent.py` 增加方法 |
| `AttributeError: _call_llm` | 4 | 自评/S1 的 LLM 调用方法 |
| `AttributeError: delete_session` | 3 | `session_persistence.py` 增加方法 |
| `AgentSessionRegistry.child_sessions` | 2 | 测试依赖 `__init__` 初始化 |

## 执行顺序

```
批次1 (可并行):
  A1/A3: 新建 normalizer.py + 改 checkers.py
  A2:    content_lock.py _normalize_threshold()
  A5:    quality_check_agent.py FUSION_WEIGHTS

批次2 (依赖批次1):
  A4:  generic_agent.py 方法论多框架
  A8:  session_persistence.py + factory.py

批次3 (独立):
  A7:  generic_agent.py _self_evaluate()
  A9:  generic_agent.py _detect_knowledge_gaps() 升级
```
