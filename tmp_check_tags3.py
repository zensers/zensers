import sys
sys.stdout.reconfigure(encoding='utf-8')

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

print('TS OPEN hex:', ts_open.encode('utf-8').hex())
print('TS CLOSE hex:', ts_close.encode('utf-8').hex())
print('TS OPEN chars:', [hex(ord(c)) for c in ts_open])
print('TS CLOSE chars:', [hex(ord(c)) for c in ts_close])
