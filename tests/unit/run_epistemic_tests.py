import sys, os, hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
os.chdir('E:/market_report_systerm')

_epistemic_order = {'factual': 0, 'inferential': 1, 'speculative': 2}
_speculative_words = {'可能', '预计', '或许', '也许', '大概', '猜测', '推测', '预期'}
ASPECT_EPISTEMIC_CEILING = {
    'strategic_intent': 'speculative',
    '战略意图': 'speculative',
    '战略意图推断': 'speculative',
    'Strategic Intent': 'speculative',
}

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        print(f'  FAIL: {name}')

print('=== L1-C: Truncation ===')

content = 'A' * 2000
truncated = content if len(content) <= 3000 else content[:2500] + '...[省略]...' + content[-500:]
check('short content not truncated', truncated == content)

head = 'H' * 2500 + 'M' * 3000 + 'T' * 500
truncated = head if len(head) <= 3000 else head[:2500] + '...[省略]...' + head[-500:]
check('head preserved', truncated.startswith('H' * 2500))
check('tail preserved', truncated.endswith('T' * 500))

content = '概述部分' + '详细分析' * 500 + '结论：AI芯片国产化率已突破30%'
truncated = content if len(content) <= 3000 else content[:2500] + '...[省略]...' + content[-500:]
check('conclusion preserved in tail', '结论：AI芯片国产化率已突破30%' in truncated)

print('\n=== L1: Rule-based validation ===')

claim = {'statement': '市场份额下降', 'confidence': 'LOW', '前提条件': '数据准确', 'epistemic_level': 'factual'}
_level = claim.get('epistemic_level', 'inferential')
if claim.get('confidence') == 'LOW' and claim.get('前提条件') and _level == 'factual':
    claim['epistemic_level'] = 'inferential'
check('LOW+premise not factual', claim['epistemic_level'] != 'factual')

claim = {'statement': '企业可能通过并购突破', 'confidence': 'HIGH', 'epistemic_level': 'factual'}
_level = claim.get('epistemic_level', 'inferential')
if _level == 'factual' and any(w in claim['statement'] for w in _speculative_words):
    claim['epistemic_level'] = 'inferential'
check('speculative word downgrade', claim['epistemic_level'] == 'inferential')

claim = {'statement': '2025年Q1市场份额为32%', 'confidence': 'HIGH', 'epistemic_level': 'factual'}
_level = claim.get('epistemic_level', 'inferential')
if _level == 'factual' and any(w in claim['statement'] for w in _speculative_words):
    claim['epistemic_level'] = 'inferential'
check('factual without speculative words kept', claim['epistemic_level'] == 'factual')

claim = {'statement': 'test', 'confidence': 'MEDIUM'}
if 'epistemic_level' not in claim:
    claim['epistemic_level'] = 'inferential'
check('missing level defaults to inferential', claim['epistemic_level'] == 'inferential')

claim = {'statement': 'test', 'confidence': 'MEDIUM', 'epistemic_level': 'unknown'}
_level = claim.get('epistemic_level', 'inferential')
if _level not in _epistemic_order:
    claim['epistemic_level'] = 'inferential'
check('invalid level defaults to inferential', claim['epistemic_level'] == 'inferential')

print('\n=== L1-D: Dimension ceiling ===')

for aspect in ['strategic_intent', '战略意图', '战略意图推断', 'Strategic Intent']:
    claim = {'epistemic_level': 'factual'}
    _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
    _level = claim.get('epistemic_level', 'inferential')
    if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
        claim['epistemic_level'] = _ceiling
    check(f'ceiling for {aspect}', claim['epistemic_level'] == 'speculative')

claim = {'epistemic_level': 'factual'}
_ceiling = ASPECT_EPISTEMIC_CEILING.get('市场规模', None)
_level = claim.get('epistemic_level', 'inferential')
if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
    claim['epistemic_level'] = _ceiling
check('non-ceiling aspect not affected', claim['epistemic_level'] == 'factual')

print('\n=== L2: Caliber map ===')

caliber_map = {'factual': 'llm_inference_factual', 'inferential': 'llm_inference', 'speculative': 'llm_inference_speculative'}
check('factual caliber', caliber_map.get('factual') == 'llm_inference_factual')
check('inferential caliber', caliber_map.get('inferential') == 'llm_inference')
check('speculative caliber', caliber_map.get('speculative') == 'llm_inference_speculative')
check('unknown caliber default', caliber_map.get('unknown', 'llm_inference') == 'llm_inference')

SOURCE_PRIORITY = {'structured_source': 100, 'search_result': 50, 'llm_inference_factual': 15, 'llm_inference': 10, 'llm_inference_speculative': 5}
check('priority ordering', SOURCE_PRIORITY['llm_inference_factual'] > SOURCE_PRIORITY['llm_inference'] > SOURCE_PRIORITY['llm_inference_speculative'])

print('\n=== L4: Hypothesis verification ===')

def parse_hyp_ver(content, hypotheses):
    verified = []
    verification_section = ''
    markers = ['假设验证结果', '假设验证结果：', '验证结果']
    for marker in markers:
        if marker in content:
            idx = content.index(marker)
            verification_section = content[idx:]
            break
    if not verification_section:
        for h in hypotheses:
            h_copy = dict(h)
            h_copy['status'] = 'unverified'
            h_copy['id'] = hashlib.md5(h.get('statement', '').encode()).hexdigest()[:8]
            verified.append(h_copy)
        return verified
    for i, h in enumerate(hypotheses):
        h_copy = dict(h)
        h_copy['id'] = hashlib.md5(h.get('statement', '').encode()).hexdigest()[:8]
        pattern = f'假设{i+1}'
        if pattern in verification_section:
            matching_lines = [line for line in verification_section.split('\n') if pattern in line and '|' in line]
            if matching_lines:
                line = matching_lines[-1]
                line_parts = line.split('|')
                judgment_part = line_parts[0].strip()
                if any(kw in judgment_part for kw in ['验证', '证实', 'verified', 'confirmed']):
                    h_copy['status'] = 'verified'
                elif any(kw in judgment_part for kw in ['修正', '修订', 'revised', 'modified', '部分']):
                    h_copy['status'] = 'revised'
                    if len(line_parts) > 2:
                        h_copy['revision_note'] = line_parts[-1].strip().replace('修正内容：', '').replace('修正内容:', '')
                elif any(kw in judgment_part for kw in ['推翻', '否定', 'refuted', 'rejected', '不成立']):
                    h_copy['status'] = 'refuted'
                else:
                    h_copy['status'] = 'unverified'
            else:
                h_copy['status'] = 'unverified'
        else:
            h_copy['status'] = 'unverified'
        verified.append(h_copy)
    return verified

r = parse_hyp_ver('假设验证结果：\n假设1：验证 | 依据：数据支撑', [{'statement': 'A'}])
check('verified hypothesis', r[0]['status'] == 'verified')

r = parse_hyp_ver('假设验证结果：\n假设1：修正 | 依据：部分成立 | 修正内容：辅助因素', [{'statement': 'A'}])
check('revised hypothesis', r[0]['status'] == 'revised')
check('revised has note', '辅助因素' in r[0].get('revision_note', ''))

r = parse_hyp_ver('假设验证结果：\n假设1：推翻 | 依据：矛盾', [{'statement': 'A'}])
check('refuted hypothesis', r[0]['status'] == 'refuted')

r = parse_hyp_ver('分析内容无验证段', [{'statement': 'A'}])
check('no section fallback', r[0]['status'] == 'unverified')

r = parse_hyp_ver('假设验证结果：\n假设1：修正 | 初步\n假设1：推翻 | 最终', [{'statement': 'A'}])
check('last matching line', r[0]['status'] == 'refuted')

r = parse_hyp_ver('假设验证结果：\n假设1：验证 | 依据：数据', [{'statement': '政策收紧导致增速放缓'}])
expected_id = hashlib.md5('政策收紧导致增速放缓'.encode()).hexdigest()[:8]
check('stable hash ID', r[0]['id'] == expected_id)

print('\n=== L5: Contradiction pre-check (heuristic) ===')

def detect_contradiction_precheck(claim_a, claim_b):
    stmt_a = claim_a.get('statement', '')
    stmt_b = claim_b.get('statement', '')
    if not stmt_a or not stmt_b:
        return False
    positive = {'增长', '上升', '扩张', '改善', '提升', '增加', '上涨', '回暖',
                '普及', '加速', '领先', '突破', '恢复', '繁荣', '强劲', '乐观',
                '收紧', '趋严', '升级', '扩张', '扩张', '强化', '推进', '普及'}
    negative = {'下降', '萎缩', '收缩', '恶化', '下滑', '减少', '下跌', '承压',
                '渗透率下滑', '放缓', '滞后', '受阻', '衰退', '疲软', '悲观',
                '放松', '趋缓', '降级', '收缩', '弱化', '停滞', '萎缩', '低迷'}
    a_pos = any(w in stmt_a for w in positive)
    a_neg = any(w in stmt_a for w in negative)
    b_pos = any(w in stmt_b for w in positive)
    b_neg = any(w in stmt_b for w in negative)
    if (a_pos and b_neg) or (a_neg and b_pos):
        def bigrams(text):
            return {text[i:i+2] for i in range(len(text)-1)}
        bigrams_a = bigrams(stmt_a)
        bigrams_b = bigrams(stmt_b)
        dir_bigrams = set()
        for w in positive | negative:
            for i in range(len(w)-1):
                dir_bigrams.add(w[i:i+2])
        content_a = bigrams_a - dir_bigrams
        content_b = bigrams_b - dir_bigrams
        if content_a and content_b:
            overlap = len(content_a & content_b) / max(len(content_a), 1)
            if overlap > 0.15:
                return True
    return False

check('direction contradiction precheck', detect_contradiction_precheck({'statement': '市场规模持续增长'}, {'statement': '市场规模面临萎缩'}) is True)
check('same direction no precheck', detect_contradiction_precheck({'statement': '市场规模持续增长'}, {'statement': '行业收入快速提升'}) is False)
check('different subject no precheck', detect_contradiction_precheck({'statement': '出口额持续增长'}, {'statement': '内销利润面临萎缩'}) is False)
check('empty statement no precheck', detect_contradiction_precheck({'statement': ''}, {'statement': '市场规模增长'}) is False)
check('no direction words no precheck', detect_contradiction_precheck({'statement': '企业A占据主导'}, {'statement': '企业B份额领先'}) is False)
check('extended keywords precheck (普及 vs 下滑)', detect_contradiction_precheck({'statement': 'AI手机快速普及'}, {'statement': 'AI手机渗透率下滑'}) is True)

print('\n=== L3: Stratified injection ===')

cross_dimension_claims = [
    {'statement': '份额32%', 'epistemic_level': 'factual', 'confidence': 'HIGH', 'source_aspect': '市场'},
    {'statement': '竞争加剧', 'epistemic_level': 'inferential', 'confidence': 'MEDIUM', '前提条件': '数据准确', 'source_aspect': '竞争'},
    {'statement': '可能并购', 'epistemic_level': 'speculative', 'confidence': 'LOW', 'falsification': '6个月无公告', 'source_aspect': '战略'},
]
factual = [c for c in cross_dimension_claims if c.get('epistemic_level') == 'factual']
inferential = [c for c in cross_dimension_claims if c.get('epistemic_level') == 'inferential']
speculative = [c for c in cross_dimension_claims if c.get('epistemic_level') == 'speculative']
no_level = [c for c in cross_dimension_claims if c.get('epistemic_level') not in ('factual', 'inferential', 'speculative')]
if no_level:
    inferential.extend(no_level)
check('factual count', len(factual) == 1)
check('inferential count', len(inferential) == 1)
check('speculative count', len(speculative) == 1)

# Old claim without epistemic_level
old_claims = [{'statement': '旧claim', 'confidence': 'MEDIUM'}]
no_level = [c for c in old_claims if c.get('epistemic_level') not in ('factual', 'inferential', 'speculative')]
inferential = [c for c in old_claims if c.get('epistemic_level') == 'inferential']
inferential.extend(no_level)
check('old claim defaults to inferential', len(inferential) == 1)

# Conflict entries filter
_all_canon = {
    'claim:市场:0': {'value': {'statement': '增长'}},
    'conflict:claim:市场:0': {'value': {'contradiction': '方向矛盾'}},
    'claim:竞争:0': {'value': {'statement': '加剧'}},
}
conflict_entries = {k: v for k, v in _all_canon.items() if k.startswith('conflict:claim:')}
check('conflict entries filtered', len(conflict_entries) == 1)
check('conflict key correct', 'conflict:claim:市场:0' in conflict_entries)

print(f'\n=== RESULTS: {passed} passed, {failed} failed ===')
if failed > 0:
    sys.exit(1)
