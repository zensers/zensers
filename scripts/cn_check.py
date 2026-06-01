"""Verify code-level Chinese is cleaned"""
import re, os

files = [
    "src/survey/backends/ai_simulation.py",
    "src/survey/backends/factory.py",
    "src/survey/task_api.py",
    "src/survey/analysis/report_builder.py",
    "src/survey/engine/simulation_engine.py",
]

for fp in files:
    with open(fp, encoding="utf-8") as f:
        lines = f.readlines()
    code_cn = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # Skip pure string data lines
        if s.startswith('"') or s.startswith("'") or s.startswith("f'"):
            continue
        if re.search(r"[\u4e00-\u9fff]", s):
            # Check if Chinese is in a comment
            if "#" in s:
                comment = s[s.index("#") + 1 :]
                if re.search(r"[\u4e00-\u9fff]", comment):
                    print(f"COMMENT {fp}:{i+1}: {s[:80]}")
                    code_cn += 1
    print(f"{fp}: {code_cn} code-level Chinese lines")

print("\nDone. Zero code-level Chinese = fully clean.")
