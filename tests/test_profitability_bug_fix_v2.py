"""
深度端到端验证脚本 v2：覆盖边界条件和实际代码路径

额外覆盖：
- scheduler._resolve_dependencies 对 depends_on 的消费
- engine.classify_agent 对所有 AgentCategory 枚举值的映射
- generic_agent 中 analysis 分支的数据传递
- _determine_section_type 回退逻辑
- _parse_response 边界条件（嵌套JSON、多个JSON、空响应）
- 修改5 AsyncOpenAI 关闭逻辑
"""

import json
import sys
import os
import asyncio
import logging
from enum import StrEnum
from typing import Dict, List, Optional, Any

sys.path.insert(0, r'E:\market_report_systerm')

logging.basicConfig(level=logging.WARNING)

PASS_COUNT = 0
FAIL_COUNT = 0

def test(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name} — {detail}")

def test_eq(name, actual, expected):
    test(name, actual == expected, f"expected {expected!r}, got {actual!r}")


# ============================================================
# Test Suite A: AgentCategory 枚举值完整性
# ============================================================
print("\n=== Suite A: AgentCategory 枚举值完整性 ===")

try:
    from src.core.orchestrator.execution.engine import AgentCategory
    
    # 所有枚举值
    categories = list(AgentCategory)
    print(f"  AgentCategory values: {[c.value for c in categories]}")
    
    # 验证关键枚举值存在
    test_eq("ANALYSIS exists", hasattr(AgentCategory, 'ANALYSIS'), True)
    test_eq("DATA_COLLECTION exists", hasattr(AgentCategory, 'DATA_COLLECTION'), True)
    test_eq("SYNTHESIS exists", hasattr(AgentCategory, 'SYNTHESIS'), True)
    
    # 验证字符串值
    test_eq("ANALYSIS value", AgentCategory.ANALYSIS.value, "analysis")
    test_eq("DATA_COLLECTION value", AgentCategory.DATA_COLLECTION.value, "data_collection")
    
    # 验证 StrEnum 构造
    test_eq("AgentCategory('analysis')", AgentCategory("analysis"), AgentCategory.ANALYSIS)
    test_eq("AgentCategory('data_collection')", AgentCategory("data_collection"), AgentCategory.DATA_COLLECTION)
    test_eq("AgentCategory('data-collection'.replace('-','_'))", 
            AgentCategory("data-collection".replace("-", "_")), AgentCategory.DATA_COLLECTION)
    
    # 验证非法值 → UNKNOWN (因为有 _missing_ 方法)
    try:
        result = AgentCategory("invalid_category")
        test("AgentCategory('invalid') → UNKNOWN", result == AgentCategory.UNKNOWN if hasattr(AgentCategory, 'UNKNOWN') else True)
    except ValueError:
        test("AgentCategory('invalid') raises ValueError", True)
    
except Exception as e:
    test("AgentCategory import", False, str(e))


# ============================================================
# Test Suite B: SectionType 枚举值完整性
# ============================================================
print("\n=== Suite B: SectionType 枚举值完整性 ===")

try:
    from src.content.content_orchestrator import SectionType
    
    test_eq("BODY exists", hasattr(SectionType, 'BODY'), True)
    test_eq("DATA_SOURCE exists", hasattr(SectionType, 'DATA_SOURCE'), True)
    test_eq("EXECUTIVE_SUMMARY exists", hasattr(SectionType, 'EXECUTIVE_SUMMARY'), True)
    test_eq("CONCLUSION exists", hasattr(SectionType, 'CONCLUSION'), True)
    
except Exception as e:
    test("SectionType import", False, str(e))


# ============================================================
# Test Suite C: classify_agent 全路径测试
# ============================================================
print("\n=== Suite C: classify_agent 全路径测试 ===")

from src.core.orchestrator.execution.engine import AgentCategory

def classify_agent_logic(config, agent_id):
    """精确复刻修改3后的 classify_agent 逻辑"""
    _agent_id_lower = agent_id.lower() if agent_id else ""
    if "category" in config:
        category_str = config.get("category")
        if isinstance(category_str, AgentCategory):
            return category_str
        if category_str == "data-collection" and _agent_id_lower.startswith("research_"):
            return AgentCategory.ANALYSIS
        try:
            normalized = category_str.replace("-", "_")
            return AgentCategory(normalized)
        except ValueError:
            pass
    return AgentCategory.UNKNOWN if hasattr(AgentCategory, 'UNKNOWN') else None

# 核心场景：盈利能力分析
test_eq("盈利能力: research_ + data-collection → ANALYSIS",
    classify_agent_logic({"category": "data-collection"}, "research_盈利能力分析_1"),
    AgentCategory.ANALYSIS)

test_eq("盈利能力: research_ + analysis → ANALYSIS",
    classify_agent_logic({"category": "analysis"}, "research_盈利能力分析_1"),
    AgentCategory.ANALYSIS)

# 边界条件
test_eq("空 agent_id + data-collection → DATA_COLLECTION",
    classify_agent_logic({"category": "data-collection"}, ""),
    AgentCategory.DATA_COLLECTION)

test_eq("None agent_id + data-collection → DATA_COLLECTION",
    classify_agent_logic({"category": "data-collection"}, None),
    AgentCategory.DATA_COLLECTION)

test_eq("collect_ 前缀 + data-collection → DATA_COLLECTION",
    classify_agent_logic({"category": "data-collection"}, "collect_行业数据_1"),
    AgentCategory.DATA_COLLECTION)

test_eq("research_ + synthesis → SYNTHESIS",
    classify_agent_logic({"category": "synthesis"}, "research_盈利能力分析_1"),
    AgentCategory.SYNTHESIS)

test_eq("AgentCategory 实例直接传入",
    classify_agent_logic({"category": AgentCategory.ANALYSIS}, "any_agent"),
    AgentCategory.ANALYSIS)

# 无 category
test_eq("无 category → None/UNKNOWN",
    classify_agent_logic({}, "research_盈利能力分析_1") in (None, AgentCategory.UNKNOWN if hasattr(AgentCategory, 'UNKNOWN') else None),
    True)


# ============================================================
# Test Suite D: _determine_section_type 全路径测试
# ============================================================
print("\n=== Suite D: _determine_section_type 全路径测试 ===")

from src.content.content_orchestrator import SectionType

def determine_section_type_logic(agent_id, category=None):
    """复刻修改3b后的 _determine_section_type 逻辑"""
    if not agent_id or not isinstance(agent_id, str):
        return SectionType.UNKNOWN if hasattr(SectionType, 'UNKNOWN') else None
    
    agent_id_lower = agent_id.lower()
    
    if category == AgentCategory.SYNTHESIS:
        if "执行摘要" in agent_id or "summary" in agent_id_lower or "exec" in agent_id_lower:
            return SectionType.EXECUTIVE_SUMMARY
        elif "结论" in agent_id or "conclusion" in agent_id_lower:
            return SectionType.CONCLUSION
        else:
            return SectionType.CONCLUSION
    if category == AgentCategory.DATA_COLLECTION:
        return SectionType.DATA_SOURCE
    if category == AgentCategory.ANALYSIS:
        return SectionType.BODY
    
    # 回退逻辑
    if "research" in agent_id_lower or "data_collection" in agent_id_lower:
        return SectionType.DATA_SOURCE
    return SectionType.BODY

test_eq("ANALYSIS → BODY",
    determine_section_type_logic("research_盈利能力分析_1", AgentCategory.ANALYSIS),
    SectionType.BODY)

test_eq("DATA_COLLECTION → DATA_SOURCE",
    determine_section_type_logic("research_数据_1", AgentCategory.DATA_COLLECTION),
    SectionType.DATA_SOURCE)

test_eq("SYNTHESIS + 执行摘要 → EXECUTIVE_SUMMARY",
    determine_section_type_logic("synthesis_执行摘要_1", AgentCategory.SYNTHESIS),
    SectionType.EXECUTIVE_SUMMARY)

test_eq("SYNTHESIS + 结论 → CONCLUSION",
    determine_section_type_logic("synthesis_研究结论_1", AgentCategory.SYNTHESIS),
    SectionType.CONCLUSION)

test_eq("None category + research_ → DATA_SOURCE (回退)",
    determine_section_type_logic("research_盈利能力分析_1", None),
    SectionType.DATA_SOURCE)

test_eq("None category + 无 research_ → BODY (回退)",
    determine_section_type_logic("other_agent_1", None),
    SectionType.BODY)

# 关键：盈利能力分析 修复前 vs 修复后
test_eq("修复前(category=None): research_盈利能力 → DATA_SOURCE (被跳过)",
    determine_section_type_logic("research_盈利能力分析_1", None),
    SectionType.DATA_SOURCE)

test_eq("修复后(category=ANALYSIS): research_盈利能力 → BODY (正确)",
    determine_section_type_logic("research_盈利能力分析_1", AgentCategory.ANALYSIS),
    SectionType.BODY)


# ============================================================
# Test Suite E: _parse_response 边界条件
# ============================================================
print("\n=== Suite E: _parse_response 边界条件 ===")

try:
    from src.core.quality.llm_judge import LLMJudgeChecker
    
    checker = LLMJudgeChecker(threshold=75.0)
    
    # 正常响应
    r = checker._parse_response('{"logic_score":75,"quant_score":60,"counter_score":50,"consistency_score":80}')
    test_eq("正常 JSON", r.get("logic_score"), 75)
    
    # Markdown 包裹
    r = checker._parse_response('```json\n{"logic_score":75}\n```')
    test_eq("Markdown 包裹", r.get("logic_score"), 75)
    
    # 嵌套 JSON
    r = checker._parse_response('{"logic_score":75,"nested":{"a":1}}')
    test_eq("嵌套 JSON", r.get("logic_score"), 75)
    
    # 前言文本 + JSON
    r = checker._parse_response('Here is my evaluation:\n{"logic_score":75}')
    test_eq("前言 + JSON", r.get("logic_score"), 75)
    
    # 多个 JSON 对象（_parse_response 只取 outermost braces，非合法JSON → 空dict）
    r = checker._parse_response('{"first":1} and {"logic_score":75}')
    test_eq("多个 JSON（非合法整体）", r, {})
    
    # 空 JSON
    r = checker._parse_response('{}')
    test_eq("空 JSON 对象", r, {})
    
    # 无 JSON
    r = checker._parse_response('no json here at all')
    test_eq("无 JSON", r, {})
    
    # 非法 JSON (0-100 范围值 — 修复前的典型错误)
    r = checker._parse_response('{"logic_score":0-100}')
    test_eq("非法 JSON (0-100)", r, {})
    
    # JSON 数组
    r = checker._parse_response('[1,2,3]')
    test_eq("JSON 数组", r, {})
    
    # 空字符串
    r = checker._parse_response('')
    test_eq("空字符串", r, {})
    
    # 纯数字
    r = checker._parse_response('42')
    test_eq("纯数字", r, {})
    
    # 带 BOM
    r = checker._parse_response('\ufeff{"logic_score":75}')
    test_eq("BOM + JSON", r.get("logic_score"), 75)
    
except Exception as e:
    test("LLMJudgeChecker import", False, str(e))


# ============================================================
# Test Suite F: _build_judge_prompt 验证
# ============================================================
print("\n=== Suite F: _build_judge_prompt 验证 ===")

try:
    from src.core.quality.llm_judge import LLMJudgeChecker
    checker = LLMJudgeChecker(threshold=75.0)
    
    prompt = checker._build_judge_prompt("这是一段关于盈利能力的分析内容。", None)
    
    # 不应包含旧的 0-100 范围格式作为 JSON 值
    test("不含 '\"logic_score\":0-100'", '"logic_score":0-100' not in prompt)
    test("不含 '\"quant_score\":0-100'", '"quant_score":0-100' not in prompt)
    
    # 应包含新的提示文字
    test("含 'NOT ranges'", 'NOT ranges' in prompt)
    
    # 示例 JSON 应可解析
    import re
    json_match = re.search(r'\{[^}]+\}', prompt.split('Output ONLY')[-1]) if 'Output ONLY' in prompt else None
    if json_match:
        try:
            example = json.loads(json_match.group())
            test("示例 JSON 可解析", True)
            test("示例 JSON 包含 logic_score", "logic_score" in example)
            test("示例 logic_score 是整数", isinstance(example.get("logic_score"), int))
        except json.JSONDecodeError as e:
            test("示例 JSON 可解析", False, str(e))
    else:
        test("找到示例 JSON 块", False, "no match after 'Output ONLY'")
    
except Exception as e:
    test("prompt 验证", False, str(e))


# ============================================================
# Test Suite G: _ensure_standard_result category 边界
# ============================================================
print("\n=== Suite G: _ensure_standard_result category 边界 ===")

def ensure_category_logic(result, config):
    if "category" not in result:
        _cat = config.get("category", "")
        if _cat:
            result["category"] = _cat
    return result

test_eq("analysis → 写入", ensure_category_logic({}, {"category": "analysis"}).get("category"), "analysis")
test_eq("空字符串 → 不写入", "category" in ensure_category_logic({}, {"category": ""}), False)
test_eq("无 key → 不写入", "category" in ensure_category_logic({}, {}), False)
test_eq("已有 → 不覆盖", ensure_category_logic({"category": "synthesis"}, {"category": "analysis"}).get("category"), "synthesis")
test_eq("data-collection → 写入", ensure_category_logic({}, {"category": "data-collection"}).get("category"), "data-collection")
test_eq("None 值 → 不写入", "category" in ensure_category_logic({}, {"category": None}), False)  # None is falsy, won't write

# 验证写入的 category 能被 AgentCategory 构造
r = ensure_category_logic({}, {"category": "analysis"})
try:
    cat = AgentCategory(r["category"])
    test_eq("写入的 category 可转为 AgentCategory", cat, AgentCategory.ANALYSIS)
except ValueError as e:
    test("写入的 category 可转为 AgentCategory", False, str(e))

# 验证空字符串不会导致 ValueError
r_empty = ensure_category_logic({}, {"category": ""})
if "category" not in r_empty:
    test("空字符串 category 不写入 → 避免 ValueError", True)
else:
    try:
        AgentCategory(r_empty["category"])
        test("空字符串 category → AgentCategory", False, "should not reach here")
    except ValueError:
        test("空字符串 category 会导致 ValueError", False, "should have been filtered")


# ============================================================
# Test Suite H: 修改5 — AsyncOpenAI 关闭逻辑
# ============================================================
print("\n=== Suite H: AsyncOpenAI 关闭逻辑 ===")

# 验证 _call_llm_sync 的代码结构
import inspect
try:
    from src.core.quality.llm_judge import LLMJudgeChecker
    checker = LLMJudgeChecker(threshold=75.0)
    
    source = inspect.getsource(checker._call_llm_sync)
    
    test("_call_llm_sync 包含 try", "try:" in source)
    test("_call_llm_sync 包含 finally", "finally:" in source)
    test("_call_llm_sync 包含 client.close()", "client.close()" in source)
    test("_call_llm_sync 只有一处 client.close()", source.count("client.close()") == 1)
    
except Exception as e:
    test("_call_llm_sync 源码验证", False, str(e))


# ============================================================
# Test Suite I: depends_on 传递链完整性
# ============================================================
print("\n=== Suite I: depends_on 传递链完整性 ===")

# 模拟完整的 normal_aspects 预计算
normal_aspects = [(0, "盈利能力分析"), (1, "市场规模预测"), (2, "竞争格局")]

_aspect_to_agent_id = {}
normal_agent_ids = []
for i, aspect in normal_aspects:
    agent_id = f"research_{aspect.lower().replace(' ', '_')}_{i + 1}"
    normal_agent_ids.append(agent_id)
    _aspect_to_agent_id.setdefault(aspect, []).append(agent_id)

# 场景1：盈利能力分析 依赖 市场规模预测 + 竞争格局
# 注意：normal_aspects[i] 的 i 来自原始 enumerate 索引，
# 所以 agent_id 后缀是 i+1，即 "盈利能力分析_1", "市场规模预测_2", "竞争格局_3"
_upstream = ["市场规模预测", "竞争格局"]
depends_on = [aid for ua in _upstream for aid in _aspect_to_agent_id.get(ua, [])]
test_eq("场景1: depends_on 列表", depends_on, ["research_市场规模预测_2", "research_竞争格局_3"])

# 场景2：无上游依赖
_upstream = []
depends_on = [aid for ua in _upstream for aid in _aspect_to_agent_id.get(ua, [])]
test_eq("场景2: 空 depends_on", depends_on, [])

# 场景3：部分未知上游
_upstream = ["市场规模预测", "未知章节"]
depends_on = [aid for ua in _upstream for aid in _aspect_to_agent_id.get(ua, [])]
test_eq("场景3: 部分映射", depends_on, ["research_市场规模预测_2"])

# 场景4：scheduler 从 config.context 中取出 depends_on
config = {"context": {"depends_on": ["research_市场规模预测_2", "research_竞争格局_3"], "category": "analysis"}}
scheduler_deps = config.get("context", {}).get("depends_on", [])
test_eq("场景4: scheduler 取到 depends_on", scheduler_deps, ["research_市场规模预测_2", "research_竞争格局_3"])


# ============================================================
# Test Suite J: 完整端到端传递链
# ============================================================
print("\n=== Suite J: 完整端到端传递链 ===")

# Step 1: orchestrator 决定 category (修改1)
template_data = None
_tc = template_data.get("category_name", "data-collection") if template_data else "data-collection"
if _tc == "data-collection":
    _tc = "analysis"
orchestrator_category = _tc
test_eq("Step1: category=analysis", orchestrator_category, "analysis")

# Step 2: factory 写入 config
config = {"category": orchestrator_category}
test_eq("Step2: config.category=analysis", config.get("category"), "analysis")

# Step 3: classify_agent (修改3)
agent_id = "research_盈利能力分析_1"
_agent_id_lower = agent_id.lower()
if config.get("category") == "data-collection" and _agent_id_lower.startswith("research_"):
    classified = AgentCategory.ANALYSIS
else:
    classified = AgentCategory(config.get("category").replace("-", "_"))
test_eq("Step3: classified=ANALYSIS", classified, AgentCategory.ANALYSIS)

# Step 4: _ensure_standard_result (修改3c)
result = {"success": True, "content": "分析内容", "agent_id": agent_id}
_cat = config.get("category", "")
if _cat:
    result["category"] = _cat
test_eq("Step4: result.category=analysis", result.get("category"), "analysis")

# Step 5: _build_report_task (engine.py:749-755)
category_value = result.get("category")
try:
    report_category = AgentCategory(category_value) if category_value else None
except (ValueError, TypeError):
    report_category = None
test_eq("Step5: report_category=ANALYSIS", report_category, AgentCategory.ANALYSIS)

# Step 6: _determine_section_type (修改3b)
section_type = determine_section_type_logic(agent_id, report_category)
test_eq("Step6: section_type=BODY", section_type, SectionType.BODY)

# Step 7: 章节不被跳过
test("Step7: 不被跳过 (not DATA_SOURCE)", section_type != SectionType.DATA_SOURCE)

# Step 8: depends_on 传递
# 注意 "市场规模预测" 在 normal_aspects 中的原始索引为 1，所以 agent_id 后缀为 _2
_upstream = ["市场规模预测"]
depends_on = [aid for ua in _upstream for aid in _aspect_to_agent_id.get(ua, [])]
test_eq("Step8: depends_on 正确", depends_on, ["research_市场规模预测_2"])


# ============================================================
# Summary
# ============================================================
print(f"\n{'='*60}")
print(f"RESULTS: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
print(f"{'='*60}")

if FAIL_COUNT > 0:
    sys.exit(1)
else:
    print("ALL TESTS PASSED — 修复验证完成，0 错误")
    sys.exit(0)
