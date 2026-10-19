import json
import os
import re
from typing import Dict, List, Optional


class TemplateRegistry:
    _instance = None
    _initialized = False

    def __new__(cls, template_dir: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, template_dir: Optional[str] = None):
        if TemplateRegistry._initialized:
            return
        TemplateRegistry._initialized = True
        if template_dir is None:
            env_dir = os.environ.get("PPT_TEMPLATE_DIR")
            if env_dir and os.path.isdir(env_dir):
                template_dir = env_dir
            else:
                base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                candidate = os.path.join(base, "config", "ppt_templates")
                if os.path.isdir(candidate):
                    template_dir = candidate
                else:
                    template_dir = os.path.join(os.getcwd(), "config", "ppt_templates")
        self.template_dir = template_dir
        self._templates: Dict[str, Dict] = {}
        self._load_all()

    def _load_all(self):
        if not os.path.isdir(self.template_dir):
            return
        for fname in os.listdir(self.template_dir):
            if fname.endswith(".json"):
                path = os.path.join(self.template_dir, fname)
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                name = config.get("meta", {}).get("name") or fname.replace(".json", "")
                self._templates[name] = config

    def get(self, name: str) -> Dict:
        return self._templates[name]

    def list_templates(self) -> List[str]:
        return list(self._templates.keys())

    def reload(self, name: Optional[str] = None):
        if name:
            fname = f"{name}.json"
            path = os.path.join(self.template_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                self._templates[name] = json.load(f)
        else:
            self._templates.clear()
            self._load_all()

    @classmethod
    def _reset(cls):
        cls._instance = None
        cls._initialized = False


class TemplateSelector:
    _STOP_WORDS = frozenset({
        'to', 'up', 'from', 'of', 'the', 'a', 'an', 'in', 'on', 'at', 'by',
        'for', 'and', 'or', 'with', 'as', 'is', 'was', 'reached', 'hit',
        'grew', 'gained', 'climbed', 'reach', 'yoy', 'cagr', 'per', 'each',
    })

    _ABS_RE = re.compile(
        r'(?<!\d)(?!(?:19|20)\d{2})'
        r'((?:\d+\.\d+|\d{1,})\s*(?:万亿|亿|万|[BMK]|家|倍|个|辆|台|颗|款|项|人|名|次|期|支|条)'
        r'(?:\s*(?:USD|CNY|EUR|元|美元))?'
        r'|\d+\.\d+[TBMK](?!\w)'
        r'|\d\s*[BMK]\s*(?:USD|CNY|EUR|元|美元))'
        r'(?!\d)',
        re.I,
    )

    _PCT_RE = re.compile(r'(\d+\.?\d*)\s*%')

    _NUM_UNIT_RE = re.compile(r'(?<!第)([\d.]+)\s*(万亿|亿|万|[BMK]|家|倍|个|辆|台|颗|款|项|人|名|次|期|支|条)', re.I)

    _PCT_TOKEN_RE = re.compile(r'^[\d.]+%?$')

    _TREND_UP_RE = re.compile(r'(grew|increased|up|rose|surged|增长|上升)', re.I)
    _TREND_DOWN_RE = re.compile(r'(declined|decreased|down|fell|dropped|下降|减少)', re.I)

    def _detect_kpis(self, items: List[str]) -> List[Dict]:
        kpis = []
        for item in items:
            kpi = {}
            abs_match = self._ABS_RE.search(item)
            pct_match = self._PCT_RE.search(item)

            if abs_match:
                # Version/phase identifiers such as ``Version 2B`` and
                # ``Phase 3B`` are not business KPIs, even though they share
                # the same number-unit shape as a real metric.
                preceding_text = item[:abs_match.start()].rstrip()
                if re.search(r"(?:version|phase)\s*$", preceding_text, re.I):
                    continue
                num_unit = self._NUM_UNIT_RE.match(abs_match.group(1))
                if num_unit:
                    kpi["number"] = num_unit.group(1) + num_unit.group(2)
                else:
                    kpi["number"] = abs_match.group(1).split()[0]
                if pct_match:
                    kpi["trend"] = pct_match.group(0)
                else:
                    kpi["trend"] = None
            elif pct_match:
                kpi["number"] = pct_match.group(0)
                kpi["trend"] = None
            else:
                continue

            if ":" in item:
                kpi["label"] = item.split(":")[0].strip()[:30]
            else:
                num_pos = item.find(kpi["number"])
                prefix = item[:num_pos].strip()
                words = re.split(r'[,;；\s]+', prefix)
                meaningful = [
                    w for w in words
                    if w.lower() not in self._STOP_WORDS
                    and len(w) > 1
                    and not self._PCT_TOKEN_RE.match(w)
                ]
                kpi["label"] = " ".join(meaningful[-3:])[:30] if meaningful else ""

            if self._TREND_UP_RE.search(item):
                kpi["trend_direction"] = "up"
            elif self._TREND_DOWN_RE.search(item):
                kpi["trend_direction"] = "down"
            else:
                kpi["trend_direction"] = None

            kpi["original_text"] = item
            kpis.append(kpi)
        return kpis

    def _detect_comparison(self, items: List[str]) -> Optional[Dict]:
        if not items:
            return None

        left_items: List[str] = []
        right_items: List[str] = []
        left_title: Optional[str] = None
        right_title: Optional[str] = None
        separator_found = False

        if any(item.strip() == "---" for item in items):
            sep_idx = next(i for i, item in enumerate(items) if item.strip() == "---")
            left_items = items[:sep_idx]
            right_items = items[sep_idx + 1:]
            return {
                "left": {"title": "", "items": left_items},
                "right": {"title": "", "items": right_items},
            }

        unmatched: List[str] = []
        for item in items:
            matched = False
            for sep in [" vs ", " VS ", " vs. ", "对比", "——"]:
                if sep in item:
                    parts = item.split(sep, 1)
                    left_part = parts[0].strip()
                    right_part = parts[1].strip()
                    if not separator_found:
                        left_title = left_part[:30]
                        right_title = right_part[:30]
                    else:
                        left_items.append(left_part)
                        right_items.append(right_part)
                    separator_found = True
                    matched = True
                    break
            if not matched:
                unmatched.append(item)

        if separator_found:
            for item in unmatched:
                if len(left_items) <= len(right_items):
                    left_items.append(item)
                else:
                    right_items.append(item)
            return {
                "left": {"title": left_title or "", "items": left_items},
                "right": {"title": right_title or "", "items": right_items},
            }

        mid = len(items) // 2
        if mid == 0 or len(items) < 5:
            return None
        return {
            "left": {"title": "", "items": items[:mid]},
            "right": {"title": "", "items": items[mid:]},
        }

    def select_and_enhance(self, slide_data: Dict, section_index: int = 0) -> str:
        items = slide_data.get("items", [])
        kpis = self._detect_kpis(items) if items else []
        comparison = self._detect_comparison(items) if items else None
        template_name = self._select(slide_data, section_index, kpis, comparison)
        self._enhance_slide_data(slide_data, template_name, section_index, kpis, comparison)
        return template_name

    def _select(self, slide_data: Dict, section_index: int = 0, kpis: List[Dict] = None, comparison: Optional[Dict] = None) -> str:
        slide_type = slide_data.get("slide_type", "content")
        items = slide_data.get("items", [])
        images = slide_data.get("images", [])
        table = slide_data.get("table_data", [])

        if slide_type == "cover":
            return "cover"
        if slide_type == "toc":
            return "toc"
        if slide_type == "end":
            return "end"
        if slide_type in ("section_title", "section-title"):
            return "section_title"
        if slide_type == "findings":
            return "findings"
        if slide_type == "data" and table:
            return "data_table"

        kpis = kpis or []
        if not kpis:
            existing_kpi = slide_data.get("kpi_data", [])
            if existing_kpi and len(existing_kpi) >= 2:
                kpis = existing_kpi
        has_comparison = comparison is not None
        has_images = bool(images)

        if kpis and len(kpis) >= 2 and has_images:
            return "kpi_highlight"
        if kpis and len(kpis) >= 2 and not has_images:
            return "kpi_highlight"
        if has_comparison:
            return "comparison"
        if len(images) >= 2 and not table:
            if not items or len(items) <= 2:
                return "chart_split"
        if images and not table:
            if not items or len(items) <= 2:
                return "chart_full"
        if slide_type == "data" and images:
            return "chart_full"
        if items and images:
            return "content_left_right"
        return "content_text_only"

    def _enhance_slide_data(self, slide_data: Dict, template_name: str, section_index: int, kpis: List[Dict] = None, comparison: Optional[Dict] = None):
        items = slide_data.get("items", [])

        if template_name == "kpi_highlight":
            kpis = kpis or self._detect_kpis(items)
            if kpis:
                slide_title = slide_data.get("title", "")
                for kpi in kpis:
                    if not kpi.get("label") and slide_title:
                        kpi["label"] = slide_title[:30]
                slide_data["kpi_data"] = kpis

        if template_name == "comparison":
            comp = comparison if comparison is not None else self._detect_comparison(items)
            if comp:
                slide_data["comparison_data"] = comp

        if template_name == "section_title":
            slide_data["section_number"] = section_index
            if not slide_data.get("section_summary"):
                content = slide_data.get("content", "")
                slide_data["section_summary"] = content[:100] if content else ""

        if template_name in ("kpi_highlight", "chart_full", "chart_split"):
            if not slide_data.get("insight_text"):
                content = slide_data.get("content", "")
                if content:
                    sentences = re.split(r'[.!?。！？]\s*', content)
                    slide_data["insight_text"] = sentences[-1].strip()[:120] if sentences else content[:120]
