import json
import re
from pathlib import Path

def evaluate_report(report_path, label):
    r = json.loads(Path(report_path).read_text(encoding="utf-8"))
    sections = r.get("report", r).get("sections", [])

    total_chars = 0
    total_dps = 0
    vague_dps = 0
    sections_with_data = 0

    for sec in sections:
        content = sec.get("content", "")
        total_chars += len(content)
        dps = sec.get("data_points", [])
        total_dps += len(dps)
        if dps:
            sections_with_data += 1
        for dp in dps:
            src = str(dp.get("source", ""))
            if any(p in src for p in ["综合", "行业", "多方", "相关", "公开", "未知", "网络", "媒体", "报告", "根据", "专家"]):
                vague_dps += 1

    kf = r.get("report", r).get("key_findings", [])
    has_markdown = any("#" in k or "**" in k for k in kf) if kf else False

    lines = []
    lines.append(f"[{label}]")
    lines.append(f"  章节数: {len(sections)}")
    lines.append(f"  总字数: {total_chars}")
    lines.append(f"  数据点: {total_dps} (模糊来源: {vague_dps})")
    lines.append(f"  有数据点章节: {sections_with_data}/{len(sections)}")
    lines.append(f"  关键发现: {len(kf)}条 {'(含markdown!)' if has_markdown else '(已清理)'}")

    for sec in sections:
        lines.append(f"    [{sec.get('id','')}] {sec.get('title','')}: {len(sec.get('content',''))}字, {len(sec.get('data_points',[]))}dp")

    return "\n".join(lines)

results = []
results.append(evaluate_report("data/e2e_v2_byd3_report.json", "BYD_06-19_3ch"))
results.append(evaluate_report("data/e2e_v2_latest3_report.json", "Latest_06-26_3ch"))
results.append(evaluate_report("data/e2e_final_report.json", "NVIDIA_06-22_3ch"))

print("\n".join(results))
