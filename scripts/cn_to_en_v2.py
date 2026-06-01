"""
Remove Chinese characters from docstrings, comments, and log messages.
Preserves Chinese characters in template DATA values (city names etc).
"""
import re, os

ROOT = r"E:\market_report_systerm"

def has_chinese(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s))

def strip_chinese_from_line(line):
    """Remove Chinese characters from a line, preserving structure"""
    # Don't touch lines that are likely data values
    s = line.strip()
    
    # Preserve lines that are pure string data in lists/dicts (template values)
    # These are typically: "北京", "男", "女", etc.
    if s.startswith('"') or s.startswith("'"):
        # This is a string value - only process if it looks like a comment/docstring
        return line
    
    # Process docstrings
    if '"""' in line:
        # Only clean Chinese from the docstring text, not from data
        parts = line.split('"""')
        cleaned = []
        for i, part in enumerate(parts):
            if has_chinese(part) and len(part) > 2:
                # Remove Chinese characters
                clean = re.sub(r'[\u4e00-\u9fff]+', '', part)
                clean = re.sub(r'\s+', ' ', clean).strip()
                cleaned.append(clean)
            else:
                cleaned.append(part)
        return '"""'.join(cleaned)
    
    # Process comments
    if '#' in line:
        idx = line.index('#')
        before = line[:idx]
        comment = line[idx:]
        if has_chinese(comment):
            clean = re.sub(r'[\u4e00-\u9fff]+', '', comment)
            clean = re.sub(r'\s+', ' ', clean)
            return before + clean
    
    # Process string literals that look like log messages (contain spaces, common patterns)
    if has_chinese(line) and ('logger.' in line or 'raise ' in line or 'Error(' in line or 'message=' in line):
        # Replace Chinese in log/error strings
        clean = re.sub(r'[\u4e00-\u9fff]+', '', line)
        clean = re.sub(r'\s+', ' ', clean)
        return clean
    
    return line

def process_file(fp):
    path = os.path.join(ROOT, fp)
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    changed = False
    
    in_docstring = False
    docstring_buffer = []
    
    for line in lines:
        stripped = line.rstrip()
        
        # Track multi-line docstrings
        if '"""' in stripped:
            count = stripped.count('"""')
            if count == 2:
                # One-liner docstring
                if has_chinese(stripped):
                    clean = re.sub(r'[\u4e00-\u9fff]+', '', stripped)
                    clean = re.sub(r'\s+', ' ', clean)
                    new_lines.append(clean + '\n')
                    changed = True
                else:
                    new_lines.append(line)
                continue
            elif count == 1:
                if in_docstring:
                    # End of docstring
                    docstring_buffer.append(stripped)
                    # Process buffer
                    combined = '\n'.join(docstring_buffer)
                    if has_chinese(combined):
                        clean = re.sub(r'[\u4e00-\u9fff]+', '', combined)
                        clean_lines = clean.split('\n')
                        for cl in clean_lines:
                            new_lines.append(cl + '\n')
                        changed = True
                    else:
                        for dl in docstring_buffer:
                            new_lines.append(dl + '\n')
                    docstring_buffer = []
                    in_docstring = False
                else:
                    # Start of docstring
                    in_docstring = True
                    docstring_buffer.append(stripped)
                continue
        
        if in_docstring:
            docstring_buffer.append(stripped)
            continue
        
        # Handle regular lines
        new_line = strip_chinese_from_line(stripped)
        if new_line != stripped:
            new_lines.append(new_line + '\n')
            changed = True
        else:
            new_lines.append(line)
    
    # Handle unclosed docstrings
    if docstring_buffer:
        for dl in docstring_buffer:
            if has_chinese(dl):
                clean = re.sub(r'[\u4e00-\u9fff]+', '', dl)
                new_lines.append(clean + '\n')
                changed = True
            else:
                new_lines.append(dl + '\n')
    
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        remaining = len(re.findall(r'[\u4e00-\u9fff]', open(path, encoding='utf-8').read()))
        return True, remaining
    return False, 0

# Process all modified files
files = [
    "src/survey/engine/persona_models.py",
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
    "src/survey/analysis/crosstab.py",
    "src/survey/analysis/report_builder.py",
    "src/survey/task_api.py",
    "src/survey/__init__.py",
    "src/api/main.py",
    "src/agents/fixed_agents/cross_synthesis_agent.py",
]

print("Processing files to remove Chinese from docstrings/comments/logs...")
for fp in files:
    if os.path.exists(os.path.join(ROOT, fp)):
        changed, remaining = process_file(fp)
        if changed:
            print(f"  MODIFIED ({remaining} remaining): {fp}")
        else:
            print(f"  SKIPPED: {fp}")
    else:
        print(f"  NOT FOUND: {fp}")

print("\nChecking for remaining Chinese text...")
remaining_files = []
for fp in files:
    path = os.path.join(ROOT, fp)
    if os.path.exists(path):
        content = open(path, encoding='utf-8').read()
        # Count Chinese chars but exclude lines that are data values (in quotes after assignment)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        if chinese_chars > 0:
            remaining_files.append((fp, chinese_chars))
            
if remaining_files:
    print(f"\n{len(remaining_files)} files still have Chinese text:")
    for fp, count in sorted(remaining_files, key=lambda x: -x[1]):
        print(f"  {fp}: {count} Chinese characters")
else:
    print("\nAll files clean!")
