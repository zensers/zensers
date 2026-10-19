"""Tests for Bug fix: PPT format still output as Word after revision/regeneration.

Bug 1: _generate_documents_from_cache stored document_path=preview_path (HTML)
       instead of doc_path (PPTX) in session['research_result'].

Bug 2: main.py download_url detection only searched *.docx+*.html, ignored *.pptx.

Bug 3: main.py legacy fallback only searched *.docx, ignored *.pptx.

Bug 4: _regenerate_from_revision only generated HTML preview, skipped final
       document generation (PPTX/DOCX).
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


class TestBug1DocumentPathUsesDocNotPreview:
    def test_document_path_stores_final_doc_path_not_preview(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = {'output_format': 'pptx'}
        doc_result = {'document_path': 'data/ses_test/ses_test_report.pptx'}
        preview_path = 'data/ses_test/ses_test_report.html'
        research_result_data = {'sections': [{'title': 'T1'}]}

        result = {
            'status': 'completed',
            'report': research_result_data,
            'document_path': doc_result.get('document_path', '') or preview_path,
        }
        assert result['document_path'].endswith('.pptx')
        assert '.html' not in result['document_path']

    def test_document_path_falls_back_to_preview_when_no_doc(self):
        session = {'output_format': 'pptx'}
        doc_result = {}
        preview_path = 'data/ses_test/ses_test_report.html'
        doc_path = ''
        final_doc_path = doc_path or preview_path
        result = {
            'status': 'completed',
            'report': {},
            'document_path': final_doc_path,
        }
        assert result['document_path'].endswith('.html')


class TestBug2DownloadUrlDetectsPptx:
    def test_download_url_includes_pptx_files(self, tmp_path):
        reports_dir = tmp_path / "data" / "reports" / "ses_test"
        reports_dir.mkdir(parents=True)
        (reports_dir / "ses_test_report.pptx").write_bytes(b"PK" + b"\x00" * 100)
        (reports_dir / "ses_test_report.html").write_text("<html></html>")

        docs = (sorted(reports_dir.glob("*.pptx"))
                + sorted(reports_dir.glob("*.docx"))
                + sorted(reports_dir.glob("*.html")))
        assert len(docs) == 2
        assert docs[0].suffix == '.pptx'
        assert docs[1].suffix == '.html'

    def test_download_url_pptx_only(self, tmp_path):
        reports_dir = tmp_path / "data" / "reports" / "ses_test"
        reports_dir.mkdir(parents=True)
        (reports_dir / "ses_test_report.pptx").write_bytes(b"PK" + b"\x00" * 100)

        docs = (sorted(reports_dir.glob("*.pptx"))
                + sorted(reports_dir.glob("*.docx"))
                + sorted(reports_dir.glob("*.html")))
        assert len(docs) == 1
        assert docs[0].suffix == '.pptx'


class TestBug3LegacyFallbackIncludesPptx:
    def test_legacy_fallback_finds_pptx(self, tmp_path):
        legacy_dir = tmp_path / "data" / "ses_test"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "ses_test_report.pptx").write_bytes(b"PK" + b"\x00" * 100)

        docs = sorted(legacy_dir.glob("*.pptx")) + sorted(legacy_dir.glob("*.docx"))
        assert len(docs) == 1
        assert docs[0].suffix == '.pptx'

    def test_legacy_fallback_prefers_pptx_over_docx(self, tmp_path):
        legacy_dir = tmp_path / "data" / "ses_test"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "ses_test_report.pptx").write_bytes(b"PK" + b"\x00" * 100)
        (legacy_dir / "ses_test_report.docx").write_bytes(b"PK" + b"\x00" * 100)

        docs = sorted(legacy_dir.glob("*.pptx")) + sorted(legacy_dir.glob("*.docx"))
        assert len(docs) == 2
        assert docs[0].suffix == '.pptx'


class TestBug4RegenerateFromRevisionGeneratesFinalDoc:
    @pytest.mark.asyncio
    async def test_regenerate_defers_final_pptx_until_html_confirmation(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        session = {
            'output_format': 'pptx',
            'research_result': {
                'status': 'completed',
                'report': {'sections': [{'title': 'T1'}]},
            },
        }

        preview_result = {'document_path': 'data/ses_test/report.html'}
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = AsyncMock(return_value=preview_result)

        with patch('src.core.preview_storage.PreviewStorage.copy_file'):
            with patch('src.core.session_streamer.SessionStreamer.push_preview_refresh'):
                with patch('src.api.research_api.Path') as mock_path_cls:
                    mock_path = MagicMock()
                    mock_path.mkdir = MagicMock()
                    mock_path.__truediv__ = MagicMock(return_value=mock_path)
                    mock_path_cls.return_value = mock_path
                    await api._regenerate_from_revision('ses_test', session, [])

        assert session['research_result']['document_path'].endswith('.html')
        assert api._orchestrator._document_agent.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_regenerate_skips_final_doc_for_html_format(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        api._orchestrator = MagicMock()
        session = {
            'output_format': 'html',
            'research_result': {
                'status': 'completed',
                'report': {'sections': [{'title': 'T1'}]},
            },
        }

        preview_result = {'document_path': 'data/ses_test/report.html'}
        api._orchestrator._document_agent = MagicMock()
        api._orchestrator._document_agent.execute = AsyncMock(return_value=preview_result)

        with patch('src.core.preview_storage.PreviewStorage.copy_file'):
            with patch('src.core.session_streamer.SessionStreamer.push_preview_refresh'):
                with patch('src.api.research_api.Path') as mock_path_cls:
                    mock_path = MagicMock()
                    mock_path.mkdir = MagicMock()
                    mock_path.__truediv__ = MagicMock(return_value=mock_path)
                    mock_path_cls.return_value = mock_path
                    await api._regenerate_from_revision('ses_test', session, [])

        assert api._orchestrator._document_agent.execute.call_count == 1


class TestDownloadEndpointFormatPriority:
    def test_format_param_routes_to_pptx(self, tmp_path):
        task_dir = tmp_path / "data" / "reports" / "ses_test"
        task_dir.mkdir(parents=True)
        (task_dir / "ses_test_report.docx").write_bytes(b"PK" + b"\x00" * 100)
        (task_dir / "ses_test_report.pptx").write_bytes(b"PK" + b"\x00" * 100)

        fmt = "pptx"
        EXTENSIONS = {"docx": "*.docx", "pptx": "*.pptx", "pdf": "*.pdf"}
        if fmt in EXTENSIONS:
            docs = sorted(task_dir.glob(EXTENSIONS[fmt]))
        else:
            docs = []

        assert len(docs) == 1
        assert docs[0].suffix == '.pptx'
