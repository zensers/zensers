import json
import os
import pytest
from src.converters.template_selector import TemplateRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    yield
    TemplateRegistry._reset()


@pytest.fixture
def template_dir(tmp_path):
    cover = {
        "meta": {"name": "cover", "display_name": "Cover", "description": "Cover slide"},
        "background": {"type": "solid", "color": "navy"},
        "slots": [{"name": "title", "type": "text", "x": 1, "y": 2, "w": 8, "h": 1, "styles": {"font_size": 36, "bold": True, "color": "white"}}],
        "decorations": []
    }
    kpi = {
        "meta": {"name": "kpi_highlight", "display_name": "KPI Highlight", "description": "KPI cards", "min_kpis": 2, "max_kpis": 4},
        "background": {"type": "solid", "color": "white"},
        "slots": [],
        "decorations": []
    }
    (tmp_path / "cover.json").write_text(json.dumps(cover, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "kpi_highlight.json").write_text(json.dumps(kpi, ensure_ascii=False), encoding="utf-8")
    return tmp_path


class TestTemplateRegistry:
    def test_load_all_templates(self, template_dir):
        reg = TemplateRegistry(template_dir=str(template_dir))
        names = reg.list_templates()
        assert "cover" in names
        assert "kpi_highlight" in names

    def test_get_template_by_name(self, template_dir):
        reg = TemplateRegistry(template_dir=str(template_dir))
        t = reg.get("cover")
        assert t["meta"]["name"] == "cover"
        assert t["background"]["color"] == "navy"

    def test_get_nonexistent_raises_keyerror(self, template_dir):
        reg = TemplateRegistry(template_dir=str(template_dir))
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_singleton_same_instance(self, template_dir):
        a = TemplateRegistry(template_dir=str(template_dir))
        b = TemplateRegistry()
        assert a is b

    def test_reload_single_template(self, template_dir):
        reg = TemplateRegistry(template_dir=str(template_dir))
        updated = {
            "meta": {"name": "cover", "display_name": "Cover v2", "description": "Updated"},
            "background": {"type": "solid", "color": "gold"},
            "slots": [],
            "decorations": []
        }
        (template_dir / "cover.json").write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
        reg.reload("cover")
        assert reg.get("cover")["meta"]["display_name"] == "Cover v2"

    def test_reload_all_templates(self, template_dir):
        reg = TemplateRegistry(template_dir=str(template_dir))
        new_template = {
            "meta": {"name": "end", "display_name": "End", "description": "End slide"},
            "background": {"type": "solid", "color": "navy"},
            "slots": [],
            "decorations": []
        }
        (template_dir / "end.json").write_text(json.dumps(new_template, ensure_ascii=False), encoding="utf-8")
        reg.reload()
        assert "end" in reg.list_templates()

    def test_reset_clears_singleton(self, template_dir):
        a = TemplateRegistry(template_dir=str(template_dir))
        TemplateRegistry._reset()
        b = TemplateRegistry(template_dir=str(template_dir))
        assert a is not b

    def test_env_var_template_dir(self, template_dir, monkeypatch):
        monkeypatch.setenv("PPT_TEMPLATE_DIR", str(template_dir))
        TemplateRegistry._reset()
        reg = TemplateRegistry()
        assert "cover" in reg.list_templates()

    def test_meta_name_fallback_to_filename(self, tmp_path):
        t = {"meta": {}, "background": {"type": "solid", "color": "white"}, "slots": [], "decorations": []}
        (tmp_path / "my_template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        reg = TemplateRegistry(template_dir=str(tmp_path))
        assert "my_template" in reg.list_templates()
