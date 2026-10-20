# -*- coding: utf-8 -*-
import pytest

import src.converters.ppt_theme as ppt_theme
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

    def test_cache_returns_equal_content(self):
        first = load_theme("default")
        second = load_theme("default")
        assert first == second
        assert first is not second

    def test_cache_avoids_rereading_file(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "cached.json").write_text('{"colors": {"navy": "123456"}}', encoding="utf-8")
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))

        calls = []
        original = ppt_theme._resolve_theme_path

        def counting(name):
            calls.append(name)
            return original(name)

        monkeypatch.setattr(ppt_theme, "_resolve_theme_path", counting)

        first = load_theme("themes/cached")
        second = load_theme("themes/cached")
        assert len(calls) == 1
        assert first == second

    def test_non_hex_color_falls_back_to_default(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "badhex.json").write_text(
            '{"colors": {"navy": "GGGGGG"}}',
            encoding="utf-8",
        )
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))
        theme = load_theme("themes/badhex")
        assert theme["colors"]["navy"] == DEFAULT_THEME["colors"]["navy"]

    def test_hash_prefix_is_stripped(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "hash.json").write_text(
            '{"colors": {"navy": "#123ABC", "gold": "#ABC"}}',
            encoding="utf-8",
        )
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))
        theme = load_theme("themes/hash")
        assert theme["colors"]["navy"] == "123ABC"
        assert theme["colors"]["gold"] == "ABC"

    def test_non_dict_colors_falls_back_entirely(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir()
        (theme_dir / "strcolors.json").write_text(
            '{"colors": "red", "fonts": {"default": "SimHei"}}',
            encoding="utf-8",
        )
        monkeypatch.setenv("PPT_THEME_DIR", str(tmp_path))
        theme = load_theme("themes/strcolors")
        assert theme["colors"] == DEFAULT_THEME["colors"]
        assert theme["fonts"]["default"] == "SimHei"
