# tests/unit/search/test_caliber_checker.py
from src.core.search.caliber_checker import CaliberConsistencyChecker


def test_detect_caliber_conflict():
    checker = CaliberConsistencyChecker()
    data_points = [
        {"metric": "智能手机出货量", "value": "3.5亿", "unit": "台", "period": "2025", "geographic_scope": "中国"},
        {"metric": "智能手机出货量", "value": "3.2亿", "unit": "台", "period": "2025", "geographic_scope": "中国", "source": "IDC"},
    ]
    conflicts = checker.check(data_points)
    assert len(conflicts) >= 1
    assert conflicts[0]["metric"] == "智能手机出货量"


def test_no_conflict_same_values():
    checker = CaliberConsistencyChecker()
    data_points = [
        {"metric": "智能手机出货量", "value": "3.5亿", "unit": "台", "period": "2025"},
        {"metric": "智能手机出货量", "value": "3.5亿", "unit": "台", "period": "2025"},
    ]
    conflicts = checker.check(data_points)
    assert len(conflicts) == 0
