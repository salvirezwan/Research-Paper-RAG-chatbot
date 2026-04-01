"""Unit tests for backend/rag/ingestion/cleaner.py"""
import pytest

from backend.rag.ingestion.cleaner import clean_pages, _clean_page


# ── _clean_page (internal) ─────────────────────────────────────────────────────

class TestCleanPage:
    def test_removes_null_bytes(self):
        assert "\x00" not in _clean_page("hello\x00world")

    def test_replaces_form_feed_with_newline(self):
        result = _clean_page("page1\x0cpage2")
        assert "\x0c" not in result
        assert "\n" in result

    def test_joins_hyphenated_line_breaks(self):
        result = _clean_page("hyphen-\nated word")
        assert "hyphenated" in result
        assert "-\n" not in result

    def test_collapses_multiple_blank_lines(self):
        result = _clean_page("paragraph one\n\n\n\nparagraph two")
        assert "\n\n\n" not in result
        assert "paragraph one" in result
        assert "paragraph two" in result

    def test_removes_bare_page_numbers(self):
        text = "Some text\n42\nMore text"
        result = _clean_page(text)
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        assert "42" not in lines

    def test_keeps_non_page_number_lines(self):
        text = "See equation 42 for details."
        result = _clean_page(text)
        assert "42" in result

    def test_collapses_multiple_spaces(self):
        result = _clean_page("too   many    spaces")
        assert "  " not in result
        assert "too many spaces" in result

    def test_strips_leading_trailing_whitespace(self):
        result = _clean_page("   hello world   ")
        assert result == result.strip()

    def test_empty_string(self):
        assert _clean_page("") == ""

    def test_preserves_content_structure(self):
        text = "Introduction\n\nThis paper presents a novel method.\n\nResults\n\nWe achieved 95% accuracy."
        result = _clean_page(text)
        assert "Introduction" in result
        assert "Results" in result
        assert "novel method" in result


# ── clean_pages (public API) ───────────────────────────────────────────────────

class TestCleanPages:
    def test_returns_same_number_of_pages(self):
        pages = ["page one text", "page two text", "page three text"]
        result = clean_pages(pages)
        assert len(result) == 3

    def test_empty_pages_preserved_as_empty_strings(self):
        pages = ["content", "", "  \n  ", "more content"]
        result = clean_pages(pages)
        assert len(result) == 4
        assert result[1] == ""
        assert result[2] == ""

    def test_cleans_each_page_independently(self):
        pages = ["page with\x00null byte", "page with hyphen-\nated"]
        result = clean_pages(pages)
        assert "\x00" not in result[0]
        assert "hyphenated" in result[1]

    def test_empty_list(self):
        assert clean_pages([]) == []

    def test_single_page(self):
        pages = ["Abstract\n\nWe present a novel approach."]
        result = clean_pages(pages)
        assert len(result) == 1
        assert "Abstract" in result[0]

    def test_raises_on_non_string_page(self):
        """clean_pages should raise if a page is not a string."""
        with pytest.raises((TypeError, AttributeError)):
            clean_pages([42])  # type: ignore[list-item]
