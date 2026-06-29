"""Transform test_data_repair.py to use patch('call_llm') instead of mock_llm"""
import re

src = open("tests/unit/report_upgrade/test_data_repair.py", "r", encoding="utf-8").read()

# 1. Remove mock_llm fixture definition
src = src.replace(
    "\n@pytest.fixture\ndef mock_llm():\n    return AsyncMock()\n\n",
    "\n",
)

# 2. Remove mock_llm from test parameter lists
src = re.sub(r'(,\s*mock_llm)(?=[),])', '', src)
src = re.sub(r'(mock_llm,\s*)', '', src)

# 3. Replace mock_llm.execute.return_value with patch + mock_call.return_value
# Pattern: find lines like `mock_llm.execute.return_value = {...}` and surrounding code
# We need to wrap the LLM-dependent code in `with patch(...) as mock_call:`

# Strategy: for each test function, find the `mock_llm.execute.return_value =` block
# and replace it + the corresponding constructor call with patched version

# This is complex - let me use a different approach: replace constructor calls
# that pass mock_llm with patched versions

# Replace DataRepairAgent constructors
src = re.sub(
    r'agent = DataRepairAgent\(mock_search, mock_scraper, mock_prompts\)',
    'agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)',
    src,
)

# Replace ConflictResolver constructors that pass mock_llm
src = re.sub(
    r'resolver = ConflictResolver\(mock_search, mock_scraper, mock_prompts\)',
    'resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)',
    src,
)

# Fix agent constructor calls (some still have old signature)
src = re.sub(
    r'DataRepairAgent\(mock_search, mock_scraper\)',
    'DataRepairAgent(mock_search, mock_scraper)',
    src,
)

# Now handle the mock_llm.execute.return_value blocks - replace with patch
# For each test function that had mock_llm, add patch decorator

# Strategy: find every `mock_llm.execute.return_value = {` block and wrap it
lines = src.split('\n')
result = []
i = 0
in_call_llm_block = False
patch_inserted = False

while i < len(lines):
    line = lines[i]
    
    # Detect mock_llm.execute.return_value = {  (should not exist anymore but just in case)
    if 'mock_llm.execute.return_value' in line:
        # Replace with patch
        indent = line[:len(line) - len(line.lstrip())]
        # Already transformed by previous regex - skip
        pass
    
    # Check for `agent = DataRepairAgent(mock_search, mock_scraper,` followed by keyword args
    # These need the with patch block
    
    result.append(line)
    i += 1

open("tests/unit/report_upgrade/test_data_repair.py", "w", encoding="utf-8").write('\n'.join(result))
print("Done basic transforms")
