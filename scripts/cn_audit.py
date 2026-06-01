"""Final Chinese text audit"""
import re, os

files = [
    "src/survey/engine/persona_models.py",
    "src/survey/engine/persona_templates.py",
    "src/survey/engine/persona_generator.py",
    "src/survey/engine/prompt_builder.py",
    "src/survey/engine/simulation_engine.py",
    "src/survey/engine/cost_monitor.py",
    "src/survey/engine/errors.py",
    "src/survey/engine/alignment_engine.py",
    "src/survey/engine/calibrator.py",
    "src/survey/engine/focus_group.py",
    "src/survey/engine/data/__init__.py",
    "src/survey/backends/factory.py",
    "src/survey/backends/ai_simulation.py",
    "src/survey/analysis/descriptive.py",
    "src/survey/analysis/sentiment.py",
    "src/survey/analysis/wordcloud.py",
    "src/survey/analysis/crosstab.py",
    "src/survey/analysis/report_builder.py",
    "src/survey/task_api.py",
    "src/survey/__init__.py",
    "src/api/main.py",
    "src/agents/fixed_agents/cross_synthesis_agent.py",
]

clean, data_only, mixed = 0, 0, 0
for fp in files:
    if not os.path.exists(fp):
        print(f"  MISSING: {fp}")
        continue
    with open(fp, encoding="utf-8") as f:
        content = f.read()
    cn = len(re.findall(r"[\u4e00-\u9fff]", content))
    if cn == 0:
        print(f"  CLEAN      {fp}")
        clean += 1
    else:
        # Check if Chinese is only in data values (quoted strings in dicts/lists)
        comment_lines = len(re.findall(r"#.*[\u4e00-\u9fff]", content))
        log_lines = len(re.findall(r"(logger\.|raise |Error\(|message=|f\").*[\u4e00-\u9fff]", content))
        code_chinese = comment_lines + log_lines
        if code_chinese == 0:
            print(f"  DATA-ONLY  {fp} ({cn} chars in string values)")
            data_only += 1
        else:
            print(f"  MIXED      {fp} ({cn} chars, {comment_lines} comment lines, {log_lines} log/error lines)")
            mixed += 1

print(f"\nSummary: {clean} clean, {data_only} data-only, {mixed} mixed")
print("Data-only files have Chinese only in template/prompt/error string values - acceptable.")
print("Mixed files may need manual review of remaining comments/logs.")
