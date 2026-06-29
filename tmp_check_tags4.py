import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'E:\market_report_systerm\src\api\research_api.py', 'r', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')
py_open = None
py_close = None
for line in lines:
    stripped = line.strip()
    if stripped.startswith('_THINK_OPEN ='):
        py_open = eval(stripped.split('=',1)[1].strip())
    if stripped.startswith('_THINK_CLOSE ='):
        py_close = eval(stripped.split('=',1)[1].strip())

with open(r'E:\market_report_systerm\web\src\components\chat\ChatPanel.tsx', 'r', encoding='utf-8') as f:
    ts_content = f.read()
ts_lines = ts_content.split('\n')
ts_open = None
ts_close = None
for line in ts_lines:
    stripped = line.strip()
    if stripped.startswith('const THINK_OPEN'):
        val_part = stripped.split("= '", 1)[1]
        ts_open = val_part.rsplit("'", 1)[0]
    if stripped.startswith('const THINK_CLOSE'):
        val_part = stripped.split("= '", 1)[1]
        ts_close = val_part.rsplit("'", 1)[0]

print('OPEN match:', py_open == ts_open, f'(PY={py_open.encode("utf-8").hex()}, TS={ts_open.encode("utf-8").hex()})')
print('CLOSE match:', py_close == ts_close, f'(PY={py_close.encode("utf-8").hex()}, TS={ts_close.encode("utf-8").hex()})')
