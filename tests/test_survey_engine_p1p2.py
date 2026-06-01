import sys
sys.path.insert(0, '.')
passed = 0; failed = 0; results = []
def check(name, ok, detail=''):
    global passed, failed
    if ok: passed += 1; results.append(f'  PASS: {name}')
    else: failed += 1; results.append(f'  FAIL: {name} - {detail}')
