"""Test: P2-1 OCR/扫描件支持 + P2-2 多模态图表理解
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.skills.analysis.annual_report_parser import AnnualReportParserSkill


@pytest.fixture
def skill():
    return AnnualReportParserSkill()


class TestDetectScannedPages:
    def test_no_scanned_pages(self, skill):
        all_text = ["Normal text page " * 50, "Another page " * 50]
        result = skill._detect_scanned_pages("dummy.pdf", all_text)
        assert result == []

    def test_scanned_page_detected(self, skill):
        all_text = ["ab"]
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.images = [{"x0": 0, "y0": 0}]
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            result = skill._detect_scanned_pages("dummy.pdf", all_text)
            assert 0 in result

    def test_page_with_text_and_image_not_scanned(self, skill):
        all_text = ["This is a normal page with enough text content to not be considered scanned" * 5]
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.images = [{"x0": 0, "y0": 0}]
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            result = skill._detect_scanned_pages("dummy.pdf", all_text)
            assert 0 not in result


class TestDetectChartPages:
    def test_chart_keyword_detected(self, skill):
        text_with_chart = "如图1所示，公司营收趋势持续增长" + " padding text " * 20
        all_text = [text_with_chart]
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.images = [{"x0": 0, "y0": 0}]
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            result = skill._detect_chart_pages("dummy.pdf", all_text, [])
            assert 0 in result

    def test_no_images_no_chart(self, skill):
        all_text = ["如图1所示，营收增长"]
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.images = []
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            result = skill._detect_chart_pages("dummy.pdf", all_text, [])
            assert result == []

    def test_multiple_images_chart(self, skill):
        all_text = ["Page with multiple images and enough text content to be considered" * 3]
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.images = [{"x0": 0}, {"x0": 1}]
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            result = skill._detect_chart_pages("dummy.pdf", all_text, [])
            assert 0 in result


class TestOcrPagesViaVision:
    @pytest.mark.asyncio
    async def test_no_vision_model_skips(self, skill):
        with patch("src.config.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = ""
            result = await skill._ocr_pages_via_vision("dummy.pdf", [0, 1])
            assert result == {}

    @pytest.mark.asyncio
    async def test_ocr_with_vision_model(self, skill):
        with patch("src.config.settings") as mock_settings, \
             patch("src.core.llm_client.call_llm_vision") as mock_vision, \
             patch.object(skill, "_render_page_to_base64", return_value="fake_b64"):
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.vision_api_key = "test_key"
            mock_settings.llm.vision_base_url = "https://api.moonshot.cn/v1"
            mock_settings.llm.api_key = "fallback_key"
            mock_settings.llm.base_url = "https://api.deepseek.com/v1"
            mock_vision.return_value = {"success": True, "content": "OCR extracted text"}
            result = await skill._ocr_pages_via_vision("dummy.pdf", [0])
            assert 0 in result
            assert result[0] == "OCR extracted text"


class TestDescribeChartsViaVision:
    @pytest.mark.asyncio
    async def test_no_vision_model_skips(self, skill):
        with patch("src.config.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = ""
            result = await skill._describe_charts_via_vision("dummy.pdf", [0])
            assert result == {}

    @pytest.mark.asyncio
    async def test_chart_description_with_vision(self, skill):
        with patch("src.config.settings") as mock_settings, \
             patch("src.core.llm_client.call_llm_vision") as mock_vision, \
             patch.object(skill, "_render_page_to_base64", return_value="fake_b64"):
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.vision_api_key = "test_key"
            mock_settings.llm.vision_base_url = "https://api.moonshot.cn/v1"
            mock_settings.llm.api_key = "fallback_key"
            mock_settings.llm.base_url = "https://api.deepseek.com/v1"
            mock_vision.return_value = {"success": True, "content": "图表分析：柱状图，营收增长20%"}
            result = await skill._describe_charts_via_vision("dummy.pdf", [2])
            assert 2 in result
            assert "柱状图" in result[2]


class TestRenderPageToBase64:
    def test_render_failure_returns_none(self, skill):
        result = skill._render_page_to_base64("nonexistent.pdf", 0)
        assert result is None


class TestCallLlmVision:
    @pytest.mark.asyncio
    async def test_vision_api_with_base64_image(self):
        from src.core.llm_client import call_llm_vision
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "choices": [{"message": {"content": "Vision result"}}],
            "usage": {"total_tokens": 100},
        }
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("src.core.llm_client.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.model = "gpt-4o"
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.temperature = 0.7
            mock_settings.llm.top_p = 1.0
            result = await call_llm_vision(
                prompt="Describe this image",
                images=["dGVzdA=="],
                api_key="test",
                base_url="https://api.test.com/v1",
            )
            assert result["success"] is True
            assert result["content"] == "Vision result"
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[-1]["content"]
            assert isinstance(user_content, list)
            assert user_content[0]["type"] == "text"
            assert user_content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_vision_api_with_bytes_image(self):
        from src.core.llm_client import call_llm_vision
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "choices": [{"message": {"content": "Bytes result"}}],
            "usage": {"total_tokens": 50},
        }
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("src.core.llm_client.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.model = "gpt-4o"
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.temperature = 0.7
            mock_settings.llm.top_p = 1.0
            result = await call_llm_vision(
                prompt="Describe this",
                images=[b"fake_image_bytes"],
                api_key="test",
                base_url="https://api.test.com/v1",
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_vision_api_with_url_image(self):
        from src.core.llm_client import call_llm_vision
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "choices": [{"message": {"content": "URL result"}}],
            "usage": {"total_tokens": 80},
        }
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("src.core.llm_client.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.model = "gpt-4o"
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.temperature = 0.7
            mock_settings.llm.top_p = 1.0
            result = await call_llm_vision(
                prompt="Describe this",
                images=["https://example.com/image.png"],
                api_key="test",
                base_url="https://api.test.com/v1",
            )
            assert result["success"] is True
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[-1]["content"]
            assert user_content[1]["image_url"]["url"] == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_vision_empty_prompt_fails(self):
        from src.core.llm_client import call_llm_vision
        result = await call_llm_vision(prompt="", images=["test"])
        assert result["success"] is False
        assert result["error"] == "empty_prompt"

    @pytest.mark.asyncio
    async def test_vision_api_failure_graceful(self):
        from src.core.llm_client import call_llm_vision
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("src.core.llm_client.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.model = "gpt-4o"
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.temperature = 0.7
            mock_settings.llm.top_p = 1.0
            result = await call_llm_vision(
                prompt="test",
                images=["test_b64"],
                api_key="test",
                base_url="https://api.test.com/v1",
            )
            assert result["success"] is False
            assert result["error"] == "vision_call_failed"

    @pytest.mark.asyncio
    async def test_vision_provider_error_propagates_unmasked(self):
        """Follow-up ②: when create() raises, the ORIGINAL provider error must
        surface — never a NameError('response') from the old finally block.
        Note: call_llm_vision's contract converts provider failures into a
        failure dict (last_error -> return), so the un-masked propagation is
        asserted on the returned message."""
        from src.core.llm_client import call_llm_vision
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("provider boom"))
        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("src.core.llm_client.settings") as mock_settings:
            mock_settings.llm = MagicMock()
            mock_settings.llm.vision_model = "kimi-k2.6"
            mock_settings.llm.model = "gpt-4o"
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.temperature = 0.7
            mock_settings.llm.top_p = 1.0
            result = await call_llm_vision(
                prompt="test",
                images=["test_b64"],
                api_key="test",
                base_url="https://api.test.com/v1",
            )
        assert result["success"] is False
        assert result["error"] == "vision_call_failed"
        assert result["message"] == "provider boom"
        assert "name 'response' is not defined" not in result["message"]
        mock_client.close.assert_awaited_once()
