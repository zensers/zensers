"""Test: _ThinkTagFilter splits streaming tokens into thinking and normal content"""

import pytest
from src.api.research_api import _ThinkTagFilter, _THINK_OPEN, _THINK_CLOSE


class TestThinkTagFilter:

    def test_passthrough_normal_text(self):
        f = _ThinkTagFilter()
        result = f.feed("Hello world")
        assert result == [('text', 'Hello world')]

    def test_passthrough_multiple_chunks(self):
        f = _ThinkTagFilter()
        assert f.feed("Hello ") == [('text', 'Hello ')]
        assert f.feed("world ") == [('text', 'world ')]
        assert f.feed("test") == [('text', 'test')]

    def test_filter_complete_think_block(self):
        f = _ThinkTagFilter()
        result = f.feed("Before %sinternal%s After" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('text', 'Before '), ('think', 'internal'), ('text', ' After')]

    def test_filter_think_at_start(self):
        f = _ThinkTagFilter()
        result = f.feed("%sthinking...%sOutput" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('think', 'thinking...'), ('text', 'Output')]

    def test_filter_think_at_end(self):
        f = _ThinkTagFilter()
        result = f.feed("Output%sthinking...%s" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('text', 'Output'), ('think', 'thinking...')]

    def test_filter_only_think_content(self):
        f = _ThinkTagFilter()
        result = f.feed("%sthinking...%s" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('think', 'thinking...')]

    def test_filter_multiple_think_blocks(self):
        f = _ThinkTagFilter()
        result = f.feed("A%sfirst%sB%ssecond%sC" % (_THINK_OPEN, _THINK_CLOSE, _THINK_OPEN, _THINK_CLOSE))
        assert result == [('text', 'A'), ('think', 'first'), ('text', 'B'), ('think', 'second'), ('text', 'C')]

    def test_think_tag_split_across_chunks(self):
        f = _ThinkTagFilter()
        assert f.feed("Before <thi") == [('text', 'Before ')]
        assert f.feed("nk>think text</thi") == [('think', 'think text')]
        assert f.feed("nk> After") == [('text', ' After')]

    def test_empty_feed_returns_empty(self):
        f = _ThinkTagFilter()
        assert f.feed("") == []

    def test_flush_after_consumed_text_returns_empty(self):
        f = _ThinkTagFilter()
        f.feed("Hello")
        assert f.flush() == []

    def test_feed_after_think_block_returns_remaining(self):
        f = _ThinkTagFilter()
        f.feed("Start%sthinking%s" % (_THINK_OPEN, _THINK_CLOSE))
        r = f.feed("End")
        assert r == [('text', 'End')]

    def test_flush_during_think_block_returns_buffered(self):
        f = _ThinkTagFilter()
        r = f.feed("Before%sthinking..." % _THINK_OPEN)
        assert r == [('text', 'Before'), ('think', 'thinking...')]
        assert f.flush() == []

    def test_partial_open_tag_at_buffer_end_is_held_back(self):
        f = _ThinkTagFilter()
        result = f.feed("text <thi")
        assert result == [('text', 'text ')]

    def test_think_tag_adjacent_no_spaces(self):
        f = _ThinkTagFilter()
        result = f.feed("A%st%sB" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('text', 'A'), ('think', 't'), ('text', 'B')]

    def test_chunk_breaks_at_tag_boundary(self):
        f = _ThinkTagFilter()
        assert f.feed("A") == [('text', 'A')]
        assert f.feed(_THINK_OPEN) == []
        assert f.feed("inner") == [('think', 'inner')]
        assert f.feed(_THINK_CLOSE) == []
        assert f.feed("B") == [('text', 'B')]

    def test_large_realistic_streaming_scenario(self):
        f = _ThinkTagFilter()
        chunks = [
            "Based",
            " on",
            " the",
            " analysis",
            ",",
            " I",
            " " + _THINK_OPEN,
            "The",
            " user",
            " wants",
            " market",
            " data",
            " for",
            " 2024",
            "." + _THINK_CLOSE,
            " recommend",
            " searching",
            " for",
            " the",
            " latest",
            " reports.",
        ]
        results: list[tuple[str, str]] = []
        for chunk in chunks:
            results.extend(f.feed(chunk))
        text_parts = [text for typ, text in results if typ == 'text']
        think_parts = [text for typ, text in results if typ == 'think']
        assert "".join(text_parts) == "Based on the analysis, I  recommend searching for the latest reports."
        assert "".join(think_parts) == "The user wants market data for 2024."

    def test_think_blocks_can_be_empty(self):
        f = _ThinkTagFilter()
        result = f.feed("%s%sHello" % (_THINK_OPEN, _THINK_CLOSE))
        assert result == [('text', 'Hello')]

    def test_nested_think_like_content_preserved(self):
        f = _ThinkTagFilter()
        result = f.feed("I think this is a good idea")
        assert result == [('text', 'I think this is a good idea')]
