"""Syntax check all new revision system files."""
import ast
import sys

files = [
    r'E:\market_report_systerm\src\core\adjustment\revision_types.py',
    r'E:\market_report_systerm\src\core\adjustment\report_lock_manager.py',
    r'E:\market_report_systerm\src\core\adjustment\content_manipulator.py',
    r'E:\market_report_systerm\src\core\adjustment\section_locator_v2.py',
    r'E:\market_report_systerm\src\core\adjustment\section_renumberer.py',
    r'E:\market_report_systerm\src\core\adjustment\cross_reference_fixer.py',
    r'E:\market_report_systerm\src\core\adjustment\snapshot_manager.py',
    r'E:\market_report_systerm\src\core\adjustment\structural_analyzer.py',
    r'E:\market_report_systerm\src\core\adjustment\version_manager.py',
    r'E:\market_report_systerm\src\core\adjustment\revision_executor.py',
    r'E:\market_report_systerm\src\core\dialogue\revision_sub_state_machine.py',
    r'E:\market_report_systerm\src\core\intent\revision_intent_analyzer.py',
    r'E:\market_report_systerm\src\core\intent\revision_plan_generator.py',
]
for f in files:
    with open(f, 'r', encoding='utf-8') as fh:
        try:
            ast.parse(fh.read(), filename=f)
            print(f'OK: {f.split(chr(92))[-1]}')
        except SyntaxError as e:
            print(f'SYNTAX ERROR: {f.split(chr(92))[-1]} line {e.lineno}: {e.msg}')