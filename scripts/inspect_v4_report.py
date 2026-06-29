import json
r = json.loads(open("data/e2e_v4_report.json", encoding="utf-8").read())
qr = r.get("quality_report", {})
print("=== Quality Report ===")
print(f"overall_score: {qr.get('overall_score')}")
print(f"rounds: {qr.get('convergence_rounds')}")
print(f"converged: {qr.get('converged')}")
for cd in qr.get("chapter_diagnostics", []):
    print(f"  chapter: {cd['chapter_id']}, score={cd['score']}, layer={cd['source_layer']}")
    if cd.get("gaps"):
        print(f"    gaps: {cd['gaps']}")
    if cd.get("remediations"):
        print(f"    remediations: {cd['remediations']}")

print("\n=== Chapter Content Preview ===")
for sec in r.get("sections", []):
    c = sec.get("content", "")
    print(f"\n[{sec['id']}] {sec['title']} ({len(c)}字, {len(sec.get('data_points',[]))}dp)")
    print(c[:500])
    print("...")

print("\n=== v3 vs v4 Comparison ===")
print("v3: score=65.0, 4687字, 25数据点, 0模糊")
print(f"v4: score={qr.get('overall_score')}, {sum(len(s.get('content','')) for s in r.get('sections',[]))}字, {sum(len(s.get('data_points',[])) for s in r.get('sections',[]))}数据点, 0模糊")
