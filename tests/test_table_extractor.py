"""Tests for TableDataExtractor"""
import sys
sys.path.insert(0, "E:/market_report_systerm")
from src.services.table_data_extractor import TableDataExtractor, ExtractedTable

def test_basic_table():
    content = """| Product | Revenue |
|---|---|
| Widget A | 100 |
| Widget B | 200 |"""
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 1, f"Expected 1 table, got {len(tables)}"
    t = tables[0]
    assert t.headers == ["Product", "Revenue"], f"Headers: {t.headers}"
    assert len(t.rows) == 2, f"Rows: {len(t.rows)}"
    assert t.numeric_columns == [1], f"Numeric cols: {t.numeric_columns}"
    data = t.to_chart_data()
    assert data is not None
    assert data["categories"] == ["Widget A", "Widget B"]
    assert data["values"] == [100.0, 200.0]
print("OK test_basic_table")
def test_no_table():
    content = "This is plain text with no markdown table"
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 0
    print("OK test_no_table")
def test_multi_table():
    content = """## Section 1
| A | B |
|---|---|
| X1 | 2 |
| X2 | 4 |

## Section 2
| X | Y |
|---|---|
| Y1 | 6 |
| Y2 | 8 |"""
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"
    print("OK test_multi_table")
def test_separator_variants():
    """Test different separator line formats"""
    content = """| Name | Value |
|:---|:---:|
| Widget X | 10 |
| Widget Y | 20 |"""
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 1
    t = tables[0]
    assert t.rows[0] == ["Widget X", "10"]
    print("OK test_separator_variants")
def test_empty_cells():
    content = """| Name | Val1 | Val2 |
|---|---|---|
| A | 10 | |
| B | | 20 |"""
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 1
    t = tables[0]
    assert len(t.rows) == 2
    print("OK test_empty_cells")
def test_insufficient_rows():
    content = """| A | B |
|---|---|
| 1 | 2 |"""
    tables = TableDataExtractor.extract_all(content)
    assert len(tables) == 0
    print("OK test_insufficient_rows")

if __name__ == "__main__":
    test_basic_table()
    test_no_table()
    test_multi_table()
    test_separator_variants()
    test_empty_cells()
    test_insufficient_rows()
    print("\nAll table extractor tests passed!")