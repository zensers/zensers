import re
from typing import Any, Dict, Optional


class SlideDataPathResolver:
    _TOKEN_RE = re.compile(r'([^.[]+)|\[(\d+)\]')

    @classmethod
    def get(cls, slide_data: Dict, path: str, default: Any = None) -> Any:
        if not path:
            return slide_data
        current = slide_data
        for key_part, index_part in cls._TOKEN_RE.findall(path):
            if index_part:
                if not isinstance(current, list) or int(index_part) >= len(current):
                    return default
                current = current[int(index_part)]
            else:
                if not isinstance(current, dict) or key_part not in current:
                    return default
                current = current[key_part]
        return current

    @classmethod
    def set(cls, slide_data: Dict, path: str, value: Any) -> bool:
        tokens = cls._TOKEN_RE.findall(path)
        if not tokens:
            return False
        current = slide_data
        for key_part, index_part in tokens[:-1]:
            if index_part:
                if not isinstance(current, list) or int(index_part) >= len(current):
                    return False
                current = current[int(index_part)]
            else:
                if not isinstance(current, dict) or key_part not in current:
                    return False
                current = current[key_part]
        last_key, last_index = tokens[-1]
        if last_index:
            if not isinstance(current, list) or int(last_index) >= len(current):
                return False
            current[int(last_index)] = value
        else:
            if not isinstance(current, dict):
                return False
            current[last_key] = value
        return True
