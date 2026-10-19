import os
import tempfile
import pytest

from src.services.image_provider import (
    ImageProvider,
    PRODUCT_KEYWORDS,
    TECH_KEYWORDS,
    CONCEPT_KEYWORDS,
    NO_IMAGE_SLIDE_TYPES,
)


class TestInit:
    def test_default_config(self):
        provider = ImageProvider()
        assert provider.cache_dir == "output/images"
        assert provider.unsplash_key is None
        assert provider.pexels_key is None
        assert provider.openai_key is None

    def test_custom_config(self):
        provider = ImageProvider(config={
            "cache_dir": "/tmp/test_imgs",
            "unsplash_api_key": "u_key",
            "pexels_api_key": "p_key",
            "openai_api_key": "o_key",
        })
        assert provider.cache_dir == "/tmp/test_imgs"
        assert provider.unsplash_key == "u_key"
        assert provider.pexels_key == "p_key"
        assert provider.openai_key == "o_key"

    def test_env_var_keys(self, monkeypatch):
        monkeypatch.setenv("UNSPLASH_API_KEY", "env_u")
        monkeypatch.setenv("PEXELS_API_KEY", "env_p")
        monkeypatch.setenv("OPENAI_API_KEY", "env_o")
        provider = ImageProvider()
        assert provider.unsplash_key == "env_u"
        assert provider.pexels_key == "env_p"
        assert provider.openai_key == "env_o"

    def test_config_overrides_env(self, monkeypatch):
        monkeypatch.setenv("UNSPLASH_API_KEY", "env_u")
        provider = ImageProvider(config={"unsplash_api_key": "cfg_u"})
        assert provider.unsplash_key == "cfg_u"


class TestExtractKeywords:
    def test_product_keyword(self):
        provider = ImageProvider()
        result = provider._extract_keywords("产品", "new product launch")
        assert len(result) == 1
        assert result[0]["type"] == "product"
        assert result[0]["keyword"] == "产品"

    def test_tech_keyword(self):
        provider = ImageProvider()
        result = provider._extract_keywords("AI技术", "")
        assert len(result) == 1
        assert result[0]["type"] == "technology"

    def test_concept_keyword(self):
        provider = ImageProvider()
        result = provider._extract_keywords("市场趋势", "")
        assert len(result) == 1
        assert result[0]["type"] == "illustration"

    def test_product_takes_priority(self):
        provider = ImageProvider()
        result = provider._extract_keywords("芯片技术", "")
        assert result[0]["type"] == "product"

    def test_no_keyword_falls_back_to_title(self):
        provider = ImageProvider()
        result = provider._extract_keywords("Hello World", "No matching keywords")
        assert len(result) == 1
        assert result[0]["keyword"] == "Hello World"
        assert result[0]["type"] == "illustration"

    def test_empty_text(self):
        provider = ImageProvider()
        result = provider._extract_keywords("", "")
        assert result == []


class TestBuildPrompt:
    def test_prompt_format(self):
        provider = ImageProvider()
        prompt = provider._build_prompt("cloud computing")
        assert "cloud computing" in prompt
        assert "Landscape" in prompt


class TestEnrichImages:
    def test_skip_no_image_slide_types(self):
        provider = ImageProvider()
        for slide_type in NO_IMAGE_SLIDE_TYPES:
            slide_data = {"slide_type": slide_type, "title": "AI技术", "content": ""}
            provider.enrich_images(slide_data)
            assert "images" not in slide_data

    def test_no_api_keys_placeholder_generated(self):
        provider = ImageProvider()
        slide_data = {
            "slide_type": "content",
            "title": "AI技术",
            "content": "test",
        }
        provider.enrich_images(slide_data)
        assert "images" in slide_data
        assert len(slide_data["images"]) == 1
        assert slide_data["images"][0]["image_type"] == "technology"

    def test_no_keywords_placeholder_from_title(self):
        provider = ImageProvider()
        slide_data = {
            "slide_type": "content",
            "title": "Hello World",
            "content": "Nothing special",
        }
        provider.enrich_images(slide_data)
        assert "images" in slide_data
        assert len(slide_data["images"]) == 1
        assert slide_data["images"][0]["alt"] == "Hello World"


class TestResolveImageSrc:
    def test_local_file_returns_path(self):
        provider = ImageProvider()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image")
            tmp = f.name
        try:
            result = provider.resolve_image_src(tmp)
            assert result == tmp
        finally:
            os.unlink(tmp)

    def test_nonexistent_local_file_returns_none(self):
        provider = ImageProvider()
        result = provider.resolve_image_src("/nonexistent/path/image.png")
        assert result is None

    def test_url_without_requests_returns_none(self, monkeypatch):
        provider = ImageProvider()
        import importlib
        import sys
        requests_mod = sys.modules.pop("requests", None)
        result = provider.resolve_image_src("https://example.com/image.jpg")
        assert result is None


class TestGetImage:
    def test_product_type_routes_to_stock(self):
        provider = ImageProvider()
        provider._search_stock = lambda kw: "/fake/stock.jpg"
        result = provider.get_image("芯片", "product")
        assert result == "/fake/stock.jpg"

    def test_technology_type_stock_first(self):
        provider = ImageProvider()
        provider._search_stock = lambda kw: "/fake/stock.jpg"
        provider._generate_ai = lambda kw: None
        result = provider.get_image("AI", "technology")
        assert result == "/fake/stock.jpg"

    def test_technology_type_ai_fallback(self):
        provider = ImageProvider()
        provider._search_stock = lambda kw: None
        provider._generate_ai = lambda kw: "/fake/ai.jpg"
        result = provider.get_image("AI", "technology")
        assert result == "/fake/ai.jpg"

    def test_illustration_type_ai_first(self):
        provider = ImageProvider()
        provider._generate_ai = lambda kw: "/fake/ai.jpg"
        provider._search_stock = lambda kw: None
        result = provider.get_image("趋势", "illustration")
        assert result == "/fake/ai.jpg"

    def test_illustration_type_stock_fallback(self):
        provider = ImageProvider()
        provider._generate_ai = lambda kw: None
        provider._search_stock = lambda kw: "/fake/stock.jpg"
        result = provider.get_image("趋势", "illustration")
        assert result == "/fake/stock.jpg"

    def test_cache_hit(self):
        provider = ImageProvider()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            provider._cache["test:technology:landscape"] = tmp
            result = provider.get_image("test", "technology", "landscape")
            assert result == tmp
        finally:
            os.unlink(tmp)

    def test_cache_stale_returns_new(self):
        provider = ImageProvider()
        provider._cache["test:technology:landscape"] = "/nonexistent/path.jpg"
        provider._search_stock = lambda kw: "/new/stock.jpg"
        result = provider.get_image("test", "technology", "landscape")
        assert result == "/new/stock.jpg"


class TestDownload:
    def test_download_creates_file(self):
        provider = ImageProvider(config={"cache_dir": tempfile.mkdtemp()})
        mock_response = type("Resp", (), {"status_code": 200, "content": b"fake_jpg_data"})()
        import unittest.mock as mock
        with mock.patch("requests.get", return_value=mock_response):
            result = provider._download("https://example.com/img.jpg", "test")
        assert result is not None
        assert os.path.isfile(result)

    def test_download_caches_file(self):
        provider = ImageProvider(config={"cache_dir": tempfile.mkdtemp()})
        mock_response = type("Resp", (), {"status_code": 200, "content": b"fake_jpg_data"})()
        import unittest.mock as mock
        with mock.patch("requests.get", return_value=mock_response):
            result1 = provider._download("https://example.com/img.jpg", "test")
            result2 = provider._download("https://example.com/img.jpg", "test")
        assert result1 == result2

    def test_download_http_error_returns_none(self):
        provider = ImageProvider(config={"cache_dir": tempfile.mkdtemp()})
        mock_response = type("Resp", (), {"status_code": 404, "content": b""})()
        import unittest.mock as mock
        with mock.patch("requests.get", return_value=mock_response):
            result = provider._download("https://example.com/img.jpg", "test")
        assert result is None


class TestSearchUnsplash:
    def test_no_key_returns_none(self):
        provider = ImageProvider()
        result = provider._search_unsplash("test")
        assert result is None

    def test_with_key_returns_url(self):
        provider = ImageProvider(config={"unsplash_api_key": "test_key"})
        mock_response = type("Resp", (), {
            "status_code": 200,
            "json": lambda self: {"results": [{"urls": {"regular": "https://img.jpg"}}]},
        })()
        import unittest.mock as mock
        with mock.patch("requests.get", return_value=mock_response):
            result = provider._search_unsplash("test")
        assert result == "https://img.jpg"


class TestSearchPexels:
    def test_no_key_returns_none(self):
        provider = ImageProvider()
        result = provider._search_pexels("test")
        assert result is None

    def test_with_key_returns_url(self):
        provider = ImageProvider(config={"pexels_api_key": "test_key"})
        mock_response = type("Resp", (), {
            "status_code": 200,
            "json": lambda self: {"photos": [{"src": {"large": "https://img.jpg"}}]},
        })()
        import unittest.mock as mock
        with mock.patch("requests.get", return_value=mock_response):
            result = provider._search_pexels("test")
        assert result == "https://img.jpg"


class TestCallDalle:
    def test_no_key_returns_none(self):
        provider = ImageProvider()
        result = provider._call_dalle("test prompt")
        assert result is None
