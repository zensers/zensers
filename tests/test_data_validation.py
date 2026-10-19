"""Data validation test"""
import sys; sys.path.insert(0, '.')
from src.survey.engine.data import list_regions, load_region, validate_region_data

regions = list_regions()
print('Available regions:', regions)

for rid in regions:
    rd = load_region(rid)
    meta = rd['meta']
    src = meta.get('source_en', '?')
    url = meta.get('source_url', 'MISSING')
    print(f'{rid}: source={src}')
    print(f'  url={url}')
    
    for dim in ('age', 'gender', 'education'):
        dist = rd.get(dim, {})
        total = sum(dist.values())
        label = 'OK' if abs(total - 1.0) < 0.05 else 'SUSPICIOUS'
        print(f'  {dim}: sum={total:.3f} [{label}]')

    warnings = validate_region_data(rid)
    if warnings:
        for w in warnings:
            print(f'  WARNING: {w}')
    print()

print('=== ALL DATA VALIDATED ===')
