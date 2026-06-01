"""Multi-region data system test"""
import sys; sys.path.insert(0, '.')
from src.survey.engine.data import list_regions, load_region, RegionData

regions = list_regions()
print('Available regions:', regions)
for rid in regions:
    rd = RegionData(rid)
    age_keys = list(rd.age.keys())[:3]
    gender_keys = list(rd.gender.keys())
    src = rd.meta.get('source_en', '?')
    print(f'  {rid}: age={age_keys}, gender={gender_keys}')
    print(f'    source: {src}')

from src.survey.engine.alignment_engine import DistributionAligner
da = DistributionAligner(region='us')
assert 'Male' in da._target_distributions['gender']
gk = list(da._target_distributions.get('gender', {}).keys())
print(f'US aligner: gender keys={gk}')

da.set_region('eu')
assert da._region == 'eu'
print(f'Switched to EU: region={da._region}')

from src.survey.engine.persona_models import PersonaV2, PersonaType
personas = [PersonaV2(persona_id=f'p{i}', persona_type=PersonaType.CONSUMER, name=f'U{i}', age=30+i, gender='Male', city='Berlin', occupation='Engineer') for i in range(50)]
result = da.align(personas, dimensions=['age', 'gender'], target_size=30)
assert len(result) == 30
print(f'EU align: {len(personas)} -> {len(result)}')

try:
    load_region('nonexistent')
except FileNotFoundError as e:
    print(f'Missing region error: expected - {e.args[0][:60]}...')

from src.survey.engine import list_regions as eng_regions
print(f'Engine exports list_regions: {list(eng_regions().keys())}')

print('=== ALL REGION TESTS PASSED ===')
