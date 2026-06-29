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

print('PY OPEN hex:', py_open.encode('utf-8').hex())
print('PY CLOSE hex:', py_close.encode('utf-8').hex())
print('PY OPEN chars:', [hex(ord(c)) for c in py_open])
print('PY CLOSE chars:', [hex(ord(c)) for c in py_close])
