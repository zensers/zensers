"""
深度评估：检查"未锚定"数值是否真的在输入数据中存在
"""
import json
import re
from pathlib import Path

report = json.loads(Path("data/e2e_v2_byd3_report.json").read_text(encoding="utf-8"))
cache_data = json.loads(Path("data/research_24c2875c/research_result_cache.json").read_text(encoding="utf-8"))

sections_3 = cache_data.get("sections", [])[:3]

input_texts = []
for sec in sections_3:
    content = sec.get("content", "")
    if isinstance(content, str):
        input_texts.append(content)
    for dp in sec.get("data_points", []):
        if isinstance(dp, dict):
            input_texts.append(dp.get("content", ""))
            input_texts.append(dp.get("title", ""))

full_input = "\n".join(input_texts)

pattern = re.compile(
    r'(\d[\d,.]*)\s*(%|亿美元|万元|亿元|万亿美元|TOPS|GHz|W|nm|美元|台|万辆|PFLOPS|GB|个|辆|亿|万|元)',
    re.IGNORECASE
)

ungrounded_details = []
for sec in report["report"]["sections"]:
    content = sec.get("content", "")
    for m in pattern.finditer(content):
        val, unit = m.group(1), m.group(2)
        search_str = f"{val}{unit}"
        if search_str not in full_input:
            val_variants = [val]
            if "." in val:
                val_variants.append(val.rstrip("0").rstrip("."))
            found = False
            for v in val_variants:
                if v in full_input:
                    found = True
                    break
            if not found:
                ctx = content[max(0, m.start()-30):m.end()+30]
                ungrounded_details.append({
                    "section": sec.get("id", ""),
                    "value": f"{val} {unit}",
                    "context": ctx,
                })

lines = []
lines.append(f"输入文本总长度: {len(full_input)} chars")
lines.append(f"报告'未锚定'数值: {len(ungrounded_details)} 个")
lines.append("")

if ungrounded_details:
    lines.append("真正未在输入数据中出现的数值:")
    for u in ungrounded_details[:20]:
        lines.append(f"  [{u['section']}] {u['value']}")
        lines.append(f"    上下文: ...{u['context']}...")
        lines.append("")
else:
    lines.append("所有数值均可在输入数据中找到依据！")

Path("data/e2e_v2_byd3_deep_eval.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
