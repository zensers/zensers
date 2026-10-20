# -*- coding: utf-8 -*-
import pytest

from src.converters.ppt_theme import DEFAULT_THEME, load_theme, clear_theme_cache


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_theme_cache()
    yield
    clear_theme_cache()


class TestLoadTheme:
    def test_default_theme_loads_palette(self):
        theme = load_theme("default")
        assert theme["colors"]["navy"] == "1A2744"
        assert theme["colors"]["gold"] == "C9A227"
        assert theme["colors"]["text_light"] == "999999"

    def test_default_theme_loads_font(self):
        theme = load_theme("default")
        assert theme["fonts"]["default"] == "Microsoft YaHei"

    def test_fallback_to_builtin_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))
        theme = load_theme("nonexistent")
        assert theme["colors"] == DEFAULT_THEME["colors"]

    def test_env_dir_overrides_builtin(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "custom.json").write_text(
            '{"meta": {"name": "custom"}, "colors": {"navy": "000000"}, "fonts": {"default": "SimHei"}}',
            encoding="utf-8",
        )
        monkeypatch.setenv("PPT_THEME_DIR", str(theme_dir.parent))
        theme = load_theme("themes/custom")
        assert theme["colors"]["navy"] == "000000"
        assert theme["fonts"]["default"] == "SimHei"

    def test_invalid_json_falls_back(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "bad.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))
        theme = load_theme("themes/bad")
        assert theme["colors"] == DEFAULT_THEME["colors"]

    def test_cache_returns_same_object(self):
        assert load_theme("default") is load_theme("default")
