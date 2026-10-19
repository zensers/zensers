import json
from pathlib import Path
from typing import Dict, List, Optional

REQUIRED_FIELDS = ["id", "name", "priority", "aspects", "content"]


def validate_framework(data: Dict) -> List[str]:
    """Validate a framework JSON object. Required: id, name, priority, aspects, content."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if "id" in data and not isinstance(data["id"], str):
        errors.append("id must be a string")
    if "name" in data and not isinstance(data["name"], str):
        errors.append("name must be a string")
    if "priority" in data:
        if not isinstance(data["priority"], int):
            errors.append("priority must be an integer")
        elif data["priority"] < 1:
            errors.append("priority must be >= 1")
    if "aspects" in data:
        if not isinstance(data["aspects"], list):
            errors.append("aspects must be a list")
        elif not data["aspects"]:
            errors.append("aspects must not be empty")
        else:
            for i, a in enumerate(data["aspects"]):
                if not isinstance(a, str) or not a:
                    errors.append(f"aspects[{i}] must be a non-empty string")
    if "content" in data and not isinstance(data["content"], str):
        errors.append("content must be a string")
    return errors


def validate_all_frameworks(frameworks_dir: Optional[Path] = None) -> Dict[str, List[str]]:
    if frameworks_dir is not None:
        dirs = [frameworks_dir]
    else:
        dirs = [
            Path(__file__).parent / "frameworks",
            Path(__file__).parents[3] / "data" / "knowledge" / "methodology" / "frameworks",
        ]
    results = {}
    seen_ids = set()
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError) as e:
                results[f.name] = [f"File error: {e}"]
                continue
            fw_id = data.get("id")
            if fw_id and fw_id in seen_ids:
                continue
            if fw_id:
                seen_ids.add(fw_id)
            errors = validate_framework(data)
            if errors:
                results[f.name] = errors
    return results
