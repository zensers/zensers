# -*- coding: utf-8 -*-
import json

import pytest


class TestResolveOutputFormat:
    """_resolve_output_format: structured field > legacy marker > docx default."""

    def _make_api(self):
        # ResearchAPI 构造过重，helper 是纯函数式方法，跳过 __init__。
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_legacy_marker_still_parsed(self):
        api = self._make_api()
        session = {}
        text = '确认开始研究\n__SELECTED_SECTIONS__:["A","B"]__OUTPUT_FORMAT__:pptx'
        sections, fmt = api._resolve_output_format(session, text)
        assert fmt == "pptx"
        assert sections == ["A", "B"]

    def test_structured_field_wins_over_marker(self):
        api = self._make_api()
        session = {"_output_format_structured": "html"}
        text = '确认\n__SELECTED_SECTIONS__:["A"]__OUTPUT_FORMAT__:pptx'
        _, fmt = api._resolve_output_format(session, text)
        assert fmt == "html"
        assert "_output_format_structured" not in session  # 消费即清除

    def test_invalid_structured_ignored_marker_used(self):
        api = self._make_api()
        session = {"_output_format_structured": "exe"}  # 非法值不入 session，但防御性测试
        text = '确认\n__SELECTED_SECTIONS__:["A"]__OUTPUT_FORMAT__:pdf'
        _, fmt = api._resolve_output_format(session, text)
        assert fmt == "pdf"

    def test_invalid_format_falls_back_to_docx(self):
        api = self._make_api()
        session = {"_output_format_structured": "exe"}
        _, fmt = api._resolve_output_format(session, "确认")
        assert fmt == "docx"

    def test_default_docx_no_markers(self):
        api = self._make_api()
        session = {}
        sections, fmt = api._resolve_output_format(session, "确认开始研究")
        assert fmt == "docx"
        assert sections is None

    def test_marker_json_still_works_with_structured_absent(self):
        api = self._make_api()
        session = {}
        payload = json.dumps(["章节一", "章节二"], ensure_ascii=False)
        text = f'确认\n__SELECTED_SECTIONS__:{payload}__OUTPUT_FORMAT__:html'
        sections, fmt = api._resolve_output_format(session, text)
        assert fmt == "html"
        assert sections == ["章节一", "章节二"]

    def test_invalid_marker_format_falls_back_to_docx(self):
        # 旧语义：marker 携带非法格式时，回退 docx，selected_sections 仍解析
        api = self._make_api()
        session = {}
        text = '确认\n__SELECTED_SECTIONS__:["A"]__OUTPUT_FORMAT__:exe'
        sections, fmt = api._resolve_output_format(session, text)
        assert fmt == "docx"
        assert sections == ["A"]

    def test_marker_bad_json_format_still_applied(self):
        # 旧语义：json 解析失败时 selected_sections=None，但格式仍生效
        api = self._make_api()
        session = {}
        text = '确认\n__SELECTED_SECTIONS__:{bad json}__OUTPUT_FORMAT__:pptx'
        sections, fmt = api._resolve_output_format(session, text)
        assert fmt == "pptx"
        assert sections is None
