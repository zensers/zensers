"""Scan for dead imports and orphaned code references"""
import ast, glob, os

src_root = "E:/market_report_systerm/src"

all_files = []
for root, dirs, files in os.walk(src_root):
    for f in files:
        if f.endswith(".py"):
            all_files.append(os.path.join(root, f))

print(f"Total Python files in src: {len(all_files)}")

# Check for references to feedback_executor
print("\n=== References to feedback_executor ===")
for f in all_files:
    with open(f, "r", encoding="utf-8") as fh:
        content = fh.read()
    if "feedback_executor" in content:
        for i, line in enumerate(content.split("\n"), 1):
            if "feedback_executor" in line:
                rel = f[len(src_root)+1:]
                print(f"  {rel}:{i}: {line.strip()[:100]}")

# Check for references to agent_coordinator
print("\n=== References to agent_coordinator ===")
for f in all_files:
    with open(f, "r", encoding="utf-8") as fh:
        content = fh.read()
    if "agent_coordinator" in content:
        for i, line in enumerate(content.split("\n"), 1):
            if "agent_coordinator" in line:
                rel = f[len(src_root)+1:]
                print(f"  {rel}:{i}: {line.strip()[:100]}")

# Check for DeprecationWarning exports
print("\n=== __init__.py with deprecation markers ===")
for root, dirs, files in os.walk(src_root):
    if "__init__.py" in files:
        path = os.path.join(root, "__init__.py")
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        if "DeprecationWarning" in content or "deprecated" in content.lower():
            rel = path[len(src_root)+1:]
            print(f"  {rel}")

# Check for unreachable/empty conditional branches
print("\n=== Files with 'if False:' or dead conditionals ===")
import re
for f in all_files:
    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
        try:
            tree = ast.parse(fh.read())
        except SyntaxError:
            continue
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Constant) and node.test.value is False:
                rel = f[len(src_root)+1:]
                print(f"  {rel}:{node.lineno}: if False found")
                break

# Check for empty except blocks
print("\n=== Empty except blocks ===")
for f in all_files:
    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
        try:
            tree = ast.parse(fh.read())
        except SyntaxError:
            continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.body and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                rel = f[len(src_root)+1:]
                print(f"  {rel}:{node.lineno}: except: pass")
