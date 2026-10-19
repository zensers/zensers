"""
Systematic inconsistency scanner for Zensers.
Scans 4 dimensions to find all bugs like the ones we fixed.

Usage: python tools/system_audit.py
"""
import ast
import re
import sys
from pathlib import Path
from typing import List, Set, Dict, Tuple

ROOT = Path(__file__).parent.parent

# ============================================================
# SCAN 1: Action Consistency
# Checks that every action defined in prompts, used in code,
# and handled in dispatchers is consistent.
# ============================================================

def scan_action_consistency() -> List[str]:
    issues = []
    
    # Source 1: Base system prompt (conversation.md)
    prompt_file = ROOT / "prompts" / "agents" / "conversation.md"
    prompt_text = prompt_file.read_text(encoding="utf-8")
    
    # Find action in output format example
    action_in_prompt = set()
    m = re.search(r'"action":\s*"([^"]+(?:\s*\|\s*[^"]+)*)"', prompt_text)
    if m:
        for a in m.group(1).split("|"):
            action_in_prompt.add(a.strip())
    
    # Source 2: Action Selection Rules in _llm_converse
    api_file = ROOT / "src" / "api" / "research_api.py"
    api_text = api_file.read_text(encoding="utf-8")
    
    action_in_prompt_rules = set()
    # Find action descriptions in the prompt f-string
    for m in re.finditer(r'action":\s*"(\w+)"', api_text):
        action_in_prompt_rules.add(m.group(1))
    
    # Source 3: Code handlers
    handler_actions = set()
    for m in re.finditer(r'if action == "(\w+)"', api_text):
        handler_actions.add(m.group(1))
    for m in re.finditer(r'elif action == "(\w+)"', api_text):
        handler_actions.add(m.group(1))
    for m in re.finditer(r'conv_result\.get\("action",\s*"(\w+)"\)', api_text):
        handler_actions.add(m.group(1))
    
    all_actions = action_in_prompt | action_in_prompt_rules | handler_actions
    
    # Check: action in prompt but no handler
    for a in sorted(action_in_prompt):
        if a not in handler_actions and a not in action_in_prompt_rules:
            issues.append(f"[ACTION] '{a}' is in base prompt output format but has NO handler and NO rule")
    
    # Check: action in prompt rules but no handler
    for a in sorted(action_in_prompt_rules):
        if a not in handler_actions and a != "continue_chat":
            issues.append(f"[ACTION] '{a}' is in Action Selection Rules but has NO handler")
    
    # Check: action handled but not in prompt rules
    for a in sorted(handler_actions):
        if a not in action_in_prompt_rules and a not in ["continue_chat"]:
            issues.append(f"[ACTION] '{a}' is handled in code but has NO rule in Action Selection Rules")
    
    # Check: action in prompt but not in rules
    for a in sorted(action_in_prompt):
        if a not in action_in_prompt_rules and a != "continue_chat":
            issues.append(f"[ACTION] '{a}' is in base prompt output format but has NO rule in Action Selection Rules")
    
    return issues


# ============================================================
# SCAN 2: Session State Machine
# Checks that mode transitions are valid and complete.
# ============================================================

def scan_state_transitions() -> List[str]:
    issues = []
    api_file = ROOT / "src" / "api" / "research_api.py"
    api_text = api_file.read_text(encoding="utf-8")
    
    # Find all places where session["mode"] is set
    mode_sets = []
    for m in re.finditer(r'session\["mode"\]\s*=\s*"(\w+)"', api_text):
        line = api_text[:m.start()].count('\n') + 1
        mode_sets.append((line, m.group(1)))
    
    # Find all places where session["status"] is set
    status_sets = []
    for m in re.finditer(r'session\["status"\]\s*=\s*"(\w+)"', api_text):
        line = api_text[:m.start()].count('\n') + 1
        status_sets.append((line, m.group(1)))
    
    # Find all places where session["paused"] is set
    paused_sets = []
    for m in re.finditer(r'session\["paused"\]\s*=\s*(True|False)', api_text):
        line = api_text[:m.start()].count('\n') + 1
        paused_sets.append((line, m.group(1)))
    
    # Check: mode="research" without current_step=6 nearby
    for line, mode_str in mode_sets:
        if mode_str == "research":
            start = max(0, line - 5)
            excerpt_lines = api_text.split('\n')[start:line+2]
            excerpt = '\n'.join(excerpt_lines)
            if 'current_step' not in excerpt and 'step' not in excerpt:
                issues.append(f"[STATE] Line {line}: mode='research' set without current_step nearby")
    
    return issues


# ============================================================
# SCAN 3: Async Race Conditions
# Finds patterns that can cause race conditions.
# ============================================================

def scan_race_conditions() -> List[str]:
    issues = []
    api_file = ROOT / "src" / "api" / "research_api.py"
    api_text = api_file.read_text(encoding="utf-8")
    
    # Find asyncio.create_task calls (background tasks)
    for m in re.finditer(r'asyncio\.create_task\(self\.(\w+)', api_text):
        line = api_text[:m.start()].count('\n') + 1
        func = m.group(1)
        issues.append(f"[RACE] Line {line}: asyncio.create_task({func}()) runs in background")
    
    # Find _cancel_existing_task calls
    cancel_calls = []
    for m in re.finditer(r'self\._cancel_existing_task\((\w+)\)', api_text):
        line = api_text[:m.start()].count('\n') + 1
        cancel_calls.append((line, m.group(1)))
    
    # Find places where session state is read without lock after create_task
    # (simplified: just flag all create_task sites)
    for m in re.finditer(r'asyncio\.create_task', api_text):
        line = api_text[:m.start()].count('\n') + 1
        # Check if there's a return immediately after
        after = api_text[m.end():m.end()+200]
        if 'return' in after[:50]:
            issues.append(f"[RACE] Line {line}: create_task followed by immediate return — caller may read stale state")
    
    # Check: executor.execute is async but called via create_task without tracking
    for m in re.finditer(r'executor\.execute\((\w+)', api_text):
        line = api_text[:m.start()].count('\n') + 1
        before = api_text[max(0, m.start()-100):m.start()]
        if 'create_task' not in before:
            issues.append(f"[RACE] Line {line}: executor.execute() called directly, not via create_task")
    
    return issues


# ============================================================
# SCAN 4: Error Recovery
# Finds places where exceptions could leave the system in
# an inconsistent state.
# ============================================================

def scan_error_recovery() -> List[str]:
    issues = []
    api_file = ROOT / "src" / "api" / "research_api.py"
    api_text = api_file.read_text(encoding="utf-8")
    
    # Find bare "except:" or "except Exception:" that might swallow critical errors
    for m in re.finditer(r'except\s*(Exception)?\s*:', api_text):
        line = api_text[:m.start()].count('\n') + 1
        # Check what's in the try block
        block_start = api_text.rfind('try:', 0, m.start())
        if block_start >= 0:
            block = api_text[block_start:m.start()]
            if 'session[' in block or 'session.' in block:
                issues.append(f"[ERROR] Line {line}: broad except around session modification — may lose state changes")
    
    # Find places where session is modified but not wrapped in try/except
    for m in re.finditer(r'session\["(\w+)"\]\s*=', api_text):
        line = api_text[:m.start()].count('\n') + 1
        # Check if inside try block
        before = api_text[:m.start()]
        last_try = before.rfind('try:')
        last_except = before.rfind('except')
        if last_try > last_except:
            pass  # Inside try block, OK
        else:
            # Not in try block, but this is common and usually fine
            pass
    
    # Find return statements after session modification without explicit save
    for m in re.finditer(r'session\[.+\]\s*=.+', api_text):
        line = api_text[:m.start()].count('\n') + 1
        after = api_text[m.end():m.end()+100]
        if 'return' in after and 'session_manager' not in after:
            issues.append(f"[ERROR] Line {line}: session modified then returned — persistence relies on __setitem__")
    
    return issues


# ============================================================
# SCAN 5: Conversation History Consistency
# Checks that all LLM interactions are properly logged.
# ============================================================

def scan_history_consistency() -> List[str]:
    issues = []
    api_file = ROOT / "src" / "api" / "research_api.py"
    api_text = api_file.read_text(encoding="utf-8")
    
    # Find all places where _llm_converse is called
    for m in re.finditer(r'await self\._llm_converse\((\w+)', api_text):
        line = api_text[:m.start()].count('\n') + 1
        before = api_text[:m.start()]
        # Check if user message was added to history before the call
        last_history_append = before.rfind('history.append')
        last_llm_call = before.rfind('_llm_converse')
        if last_history_append < last_llm_call and last_llm_call > 0:
            issues.append(f"[HISTORY] Line {line}: _llm_converse called but no history.append before it")
    
    # Find all places where llm_converse returns "processing" (tool call)
    # These need to save the assistant message to history
    for m in re.finditer(r'status.*processing.*tool_call', api_text):
        line = api_text[:m.start()].count('\n') + 1
        # Check if there's a history.append nearby
        before = api_text[:m.start()]
        last_history = before.rfind('history.append')
        if last_history > 0:
            before_history = api_text[last_history-100:last_history]
            if 'assistant' not in before_history:
                issues.append(f"[HISTORY] Line {line}: tool_call processing path doesn't save assistant message to history")
    
    return issues


# ============================================================
# RUN ALL SCANS
# ============================================================

def main():
    print("=" * 70)
    print("Zensers Systematic Inconsistency Scanner")
    print("=" * 70)
    
    all_issues = []
    
    print("\n[1/5] Action Consistency Scan...")
    issues = scan_action_consistency()
    all_issues.extend(issues)
    for i in issues:
        print(f"  {i}")
    if not issues:
        print("  (none found)")
    
    print("\n[2/5] State Transition Scan...")
    issues = scan_state_transitions()
    all_issues.extend(issues)
    for i in issues:
        print(f"  {i}")
    if not issues:
        print("  (none found)")
    
    print("\n[3/5] Race Condition Scan...")
    issues = scan_race_conditions()
    all_issues.extend(issues)
    for i in issues:
        print(f"  {i}")
    if not issues:
        print("  (none found)")
    
    print("\n[4/5] Error Recovery Scan...")
    issues = scan_error_recovery()
    all_issues.extend(issues)
    for i in issues:
        print(f"  {i}")
    if not issues:
        print("  (none found)")
    
    print("\n[5/5] History Consistency Scan...")
    issues = scan_history_consistency()
    all_issues.extend(issues)
    for i in issues:
        print(f"  {i}")
    if not issues:
        print("  (none found)")
    
    print("\n" + "=" * 70)
    print(f"Total issues found: {len(all_issues)}")
    if len(all_issues) == 0:
        print("CLEAN - No inconsistencies detected")
    else:
        for i in all_issues:
            print(f"  {i}")
    print("=" * 70)


if __name__ == "__main__":
    main()
