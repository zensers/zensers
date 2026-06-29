import json
from pathlib import Path
from src.agents.fixed_agents.report_upgrade.orchestrator import _is_vague_source

def assess(report_path, label):
    r = json.loads(Path(report_path).read_text(encoding="utf-8"))
    report = r.get("report", r)
    sections = report.get("sections", [])
    kf = report.get("key_findings", [])

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  {label}")
    lines.append(f"{'='*70}")

    total_chars = sum(len(s.get("content","")) for s in sections)
    total_dps = sum(len(s.get("data_points",[])) for s in sections)
    vague_count = sum(
        sum(1 for dp in s.get("data_points",[]) if _is_vague_source(str(dp.get("source",""))))
        for s in sections
    )
    lines.append(f"  章节: {len(sections)} | 总字数: {total_chars} | 数据点: {total_dps} | 模糊来源: {vague_count}")
    lines.append(f"  关键发现: {len(kf)}条")

    lines.append(f"\n  --- 章节概况 ---")
    for s in sections:
        dps = s.get("data_points", [])
        srcs = s.get("sources", [])
        content = s.get("content", "")
        dp_sources = set()
        for dp in dps:
            src = dp.get("source", "")
            if src and not _is_vague_source(src):
                dp_sources.add(src[:40])
        lines.append(f"  [{s['id']}] {s['title']}: {len(content)}字, {len(dps)}数据点, {len(dp_sources)}具体来源")
        if dp_sources:
            for ds in list(dp_sources)[:3]:
                lines.append(f"      来源: {ds}")

    lines.append(f"\n  --- 关键发现 ---")
    for i, k in enumerate(kf[:5]):
        cleaned = k[:200]
        lines.append(f"  [{i+1}] {cleaned}")

    lines.append(f"\n  --- 数据点详情(每章节前3个) ---")
    for s in sections:
        dps = s.get("data_points", [])
        lines.append(f"  [{s['id']}]")
        for dp in dps[:3]:
            lines.append(f"    {dp.get('metric','')} = {dp.get('value','')} {dp.get('unit','')} [来源: {dp.get('source','')[:50]}]")

    lines.append(f"\n  --- 内容抽样(每章节前300字) ---")
    for s in sections:
        content = s.get("content", "")
        lines.append(f"  [{s['id']}] {content[:300]}...")
        lines.append(f"")

    return "\n".join(lines)

results = []
results.append(assess("data/e2e_v2_byd3_report.json", "比亚迪(06-19) 3章节"))
results.append(assess("data/e2e_v2_latest3_report.json", "最新数据(06-26) 3章节"))
results.append(assess("data/e2e_final_report.json", "NVIDIA(06-22) 3章节"))

output = "\n".join(results)
Path("data/full_quality_report.txt").write_text(output, encoding="utf-8")
print(output)
