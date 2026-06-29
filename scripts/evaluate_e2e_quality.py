import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

report = json.loads(Path("data/e2e_real_report.json").read_text(encoding="utf-8"))
cache = json.loads(Path("data/research_60f0e1ed/research_result_cache.json").read_text(encoding="utf-8"))

section = report["report"]["sections"][0]
content = section["content"]
dps = section["data_points"]
key_findings = report["report"]["key_findings"]

input_content = "\n".join(s.get("content", "") for s in cache.get("sections", []))
input_dps = []
for s in cache.get("sections", []):
    input_dps.extend(s.get("data_points", []))

lines = []
lines.append("=" * 70)
lines.append("端到端测试深度质量评估报告")
lines.append("=" * 70)

lines.append(f"\n主题: {cache['topic']}")
lines.append(f"输入: {len(cache.get('sections', []))} 章节, {len(cache.get('sources', []))} 来源")
lines.append(f"输出: {len(report['report']['sections'])} 章节, {len(dps)} 数据点")

lines.append("\n" + "=" * 70)
lines.append("一、数据锚定度评估")
lines.append("=" * 70)

input_numbers = set()
for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|MB|个)', input_content):
    input_numbers.add((m.group(1), m.group(2)))

output_numbers = []
for m in re.finditer(r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|MB|个)', content):
    output_numbers.append((m.group(1), m.group(2), content[max(0, m.start()-40):m.end()+40]))

grounded = 0
ungrounded = []
for val, unit, ctx in output_numbers:
    if (val, unit) in input_numbers or any(val == iv and unit == iu for iv, iu in input_numbers):
        grounded += 1
    else:
        ungrounded.append((val, unit, ctx))

total = len(output_numbers)
lines.append(f"\n输出中数值总数: {total}")
lines.append(f"可在输入中找到依据: {grounded}")
lines.append(f"未在输入中找到依据: {len(ungrounded)}")
if total > 0:
    lines.append(f"数据锚定率: {grounded/total*100:.1f}%")

if ungrounded:
    lines.append(f"\n未锚定数值详情:")
    for val, unit, ctx in ungrounded[:15]:
        lines.append(f"  - {val} {unit}: ...{ctx}...")

lines.append("\n" + "=" * 70)
lines.append("二、数据点来源溯源")
lines.append("=" * 70)

from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source
vague_count = sum(1 for dp in dps if _is_vague_source(dp.get("source", "")))
specific_count = len(dps) - vague_count

lines.append(f"\n数据点总数: {len(dps)}")
lines.append(f"有具体来源: {specific_count}")
lines.append(f"模糊来源: {vague_count}")

if vague_count > 0:
    lines.append(f"\n模糊来源数据点:")
    for dp in dps:
        if _is_vague_source(dp.get("source", "")):
            lines.append(f"  - [{dp['metric']}] {dp['value']} {dp['unit']} 来源: {dp['source']}")

lines.append(f"\n数据点详情:")
for dp in dps:
    lines.append(f"  - [{dp['metric']}] {dp['value']} {dp['unit']} | 来源: {dp['source']}")

lines.append("\n" + "=" * 70)
lines.append("三、内容引用标注")
lines.append("=" * 70)

ref_pattern = re.compile(r'\[(\d+)\]')
ref_matches = ref_pattern.findall(content)
lines.append(f"\n引用标注数量: {len(ref_matches)}")
lines.append(f"引用标注序号: {sorted(set(int(r) for r in ref_matches)) if ref_matches else '无'}")

lines.append("\n" + "=" * 70)
lines.append("四、数据缺口标注")
lines.append("=" * 70)

gap_keywords = ["尚不充分", "无法做出可靠判断", "无法对", "尚需", "需更详细", "数据缺口", "未披露", "未提供"]
gap_mentions = []
for kw in gap_keywords:
    indices = [m.start() for m in re.finditer(kw, content)]
    for idx in indices:
        ctx = content[max(0, idx-30):idx+len(kw)+30]
        gap_mentions.append(ctx)

lines.append(f"\n数据缺口标注次数: {len(gap_mentions)}")
if gap_mentions:
    for gm in gap_mentions:
        lines.append(f"  - ...{gm}...")
else:
    lines.append("  未发现数据缺口标注（可能意味着LLM覆盖了所有内容而未标注不足）")

lines.append("\n" + "=" * 70)
lines.append("五、推理深度评估")
lines.append("=" * 70)

reasoning_keywords = ["由此推断", "可以推演", "这意味着", "表明", "反映出", "从.*可以推断", "推演", "逻辑", "核心支点"]
reasoning_count = sum(len(re.findall(kw, content)) for kw in reasoning_keywords)
lines.append(f"\n推理标记出现次数: {reasoning_count}")

lines.append(f"\n输出报告全文（前2000字）:")
lines.append(content[:2000])
lines.append("\n...")
lines.append(f"\n[全文 {len(content)} 字]")

lines.append("\n" + "=" * 70)
lines.append("六、关键发现分析")
lines.append("=" * 70)
for i, kf in enumerate(key_findings):
    lines.append(f"\n[{i+1}] {kf[:200]}")

lines.append("\n" + "=" * 70)
lines.append("七、综合评分")
lines.append("=" * 70)

anchoring_score = (grounded / total * 100) if total > 0 else 0
source_score = (specific_count / len(dps) * 100) if len(dps) > 0 else 0
gap_score = min(len(gap_mentions) * 20, 100)
reasoning_score = min(reasoning_count * 10, 100)

overall = anchoring_score * 0.4 + source_score * 0.25 + gap_score * 0.15 + reasoning_score * 0.2

lines.append(f"\n数据锚定度: {anchoring_score:.0f}/100 (权重40%)")
lines.append(f"数据来源可溯性: {source_score:.0f}/100 (权重25%)")
lines.append(f"数据缺口诚实度: {gap_score:.0f}/100 (权重15%)")
lines.append(f"推理深度: {reasoning_score:.0f}/100 (权重20%)")
lines.append(f"\n综合得分: {overall:.0f}/100")

Path("data/e2e_quality_report.txt").write_text("\n".join(lines), encoding="utf-8")
