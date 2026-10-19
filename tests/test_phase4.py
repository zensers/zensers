"""Phase 4 verification test"""
import sys; sys.path.insert(0, '.')
from src.survey.engine import DistributionAligner, SimulationCalibrator, CalibrationReport
print('1. Phase 4 imports OK')

from src.survey.engine.persona_models import PersonaV2, PersonaType

# 2. DistributionAligner
da = DistributionAligner()
personas = [PersonaV2(persona_id=f'p{i}', persona_type=PersonaType.CONSUMER, name=f'U{i}', age=i*5+20, gender='M' if i%2==0 else 'F', city='Beijing', occupation='T') for i in range(20)]
report = da.get_distribution_report(personas)
assert 'age' in report
print(f'2. Distribution report dims: {list(report.keys())}')

# 3. Alignment
aligned = da.align(personas, target_size=15)
assert len(aligned) <= 15
print(f'3. Align: {len(personas)} -> {len(aligned)}')

# 4. Calibrator - missing data raises error
cal = SimulationCalibrator()
try:
    cal.calibrate(None, [], 'nonexistent_benchmark')
    print('4. ERROR: Should have raised')
except Exception as e:
    print(f'4. Missing data raised: {type(e).__name__}')

# 5. CalibrationReport serialization
cr = CalibrationReport(overall_fidelity=0.85, variance_ratio=0.92, distribution_overlap=0.78)
d = cr.to_dict()
assert d['overall_fidelity'] == 0.85
print(f'5. Report dict: fidelity={d["overall_fidelity"]}')

# 6. Distribution similarity math
from src.survey.engine.calibrator import SimulationCalibrator as Cal
sim = Cal._distribution_similarity({'A': 0.5, 'B': 0.5}, {'A': 0.5, 'B': 0.5})
assert abs(sim - 1.0) < 0.001
print(f'6. Similarity (identical): {sim:.4f}')

sim2 = Cal._distribution_similarity({'A': 1.0}, {'B': 1.0})
print(f'7. Similarity (different): {sim2:.4f}')

vr = Cal._variance_ratio({'A': 0.5, 'B': 0.5}, {'A': 0.5, 'B': 0.5})
print(f'8. Variance ratio (identical): {vr:.4f}')

oc = Cal._overlap_coefficient({'A': 0.6, 'B': 0.4}, {'A': 0.5, 'B': 0.5})
assert abs(oc - 0.9) < 0.001
print(f'9. Overlap: {oc:.4f}')

print('=== ALL PHASE 4 TESTS PASSED ===')
