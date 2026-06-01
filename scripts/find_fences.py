import re
with open('E:/market_report_systerm/docs/REVISION_SYSTEM_REDESIGN.md', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(len(lines)-1):
    t = lines[i].strip()
    t2 = lines[i+1].strip()
    if t == '```' and t2.startswith('###'):
        print(f'FENCE->HEADING at L{i+1}: ``` -> {t2}')
    if t == '```' and i+1 < len(lines) and lines[i+1].strip() == '```':
        print(f'EMPTY FENCE at L{i+1}-{i+2}')
