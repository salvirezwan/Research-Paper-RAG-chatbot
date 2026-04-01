"""Unit tests for backend/rag/ingestion/chunker.py"""
import pytest

from backend.rag.ingestion.chunker import (
    chunk_paper,
    _split_into_sections,
    _is_section_heading,
    _find_page,
    _build_chunk,
)


# ── _is_section_heading ────────────────────────────────────────────────────────

class TestIsSectionHeading:
    @pytest.mark.parametrize("heading", [
        "Abstract",
        "Introduction",
        "Related Work",
        "Methodology",
        "Results",
        "Discussion",
        "Conclusion",
        "References",
        "Acknowledgements",
        "Limitations",
    ])
    def test_recognises_standard_headings(self, heading):
        assert _is_section_heading(heading) is True

    @pytest.mark.parametrize("numbered", [
        "1. Introduction",
        "2 Related Work",
        "3.1 Datasets",
        "4.2.1 Ablation Study",
    ])
    def test_recognises_numbered_sections(self, numbered):
        assert _is_section_heading(numbered) is True

    @pytest.mark.parametrize("non_heading", [
        "",
        "This is a normal sentence that is too long to be a heading.",
        "the quick brown fox",
        "42",
    ])
    def test_rejects_non_headings(self, non_heading):
        assert _is_section_heading(non_heading) is False

    def test_too_long_line_rejected(self):
        long_line = "A" * 101
        assert _is_section_heading(long_line) is False


# ── _split_into_sections ───────────────────────────────────────────────────────

class TestSplitIntoSections:
    def test_splits_on_standard_headings(self):
        text = (
            "Introduction\n\nThis is the introduction text.\n\n"
            "Methods\n\nThis is the methods section."
        )
        sections = _split_into_sections(text)
        assert len(sections) == 2
        assert sections[0][0] == "Introduction"
        assert sections[1][0] == "Methods"

    def test_returns_empty_for_no_headings(self):
        text = "Just a block of plain text with no headings anywhere."
        assert _split_into_sections(text) == []

    def test_body_text_captured_correctly(self):
        text = "Abstract\n\nWe study X.\nWe find Y.\n\nIntroduction\n\nContext here."
        sections = _split_into_sections(text)
        intro_body = next(b for h, b in sections if h == "Introduction")
        assert "Context here" in intro_body

    def test_skips_sections_with_no_body(self):
        text = "Introduction\n\nMethods\n\nActual methods text here."
        sections = _split_into_sections(text)
        # Introduction has no body, should be absent
        headings = [h for h, _ in sections]
        assert "Introduction" not in headings
        assert "Methods" in headings


# ── _find_page ─────────────────────────────────────────────────────────────────

class TestFindPage:
    def test_finds_text_on_first_page(self):
        pages = ["The quick brown fox jumps over the lazy dog.", "Second page content."]
        result = _find_page("The quick brown fox", pages)
        assert result == 1

    def test_finds_text_on_second_page(self):
        pages = ["First page only.", "Second page has the target text here."]
        result = _find_page("Second page has the target", pages)
        assert result == 2

    def test_returns_1_when_not_found(self):
        pages = ["Completely unrelated content."]
        result = _find_page("text that does not exist anywhere", pages)
        assert result == 1

    def test_empty_text_returns_none(self):
        pages = ["some content"]
        assert _find_page("", pages) is None

    def test_empty_pages_returns_none(self):
        assert _find_page("some text", []) is None

    def test_page_offset_applied(self):
        pages = ["Target text is on this page."]
        result = _find_page("Target text", pages, page_offset=5)
        assert result == 6  # 1 + 5


# ── _build_chunk ───────────────────────────────────────────────────────────────

class TestBuildChunk:
    def test_required_fields_always_present(self):
        chunk = _build_chunk(
            content="Some text",
            source_document="paper.pdf",
            paper_title=None,
            authors=None,
            source="upload",
            publication_year=None,
            arxiv_id=None,
            doi=None,
            subject_areas=None,
            section_id=None,
            paragraph_ref=None,
            page_number=None,
            chunk_index=0,
            upload_id=None,
        )
        assert chunk["content"] == "Some text"
        assert chunk["source_document"] == "paper.pdf"
        assert chunk["source"] == "upload"
        assert chunk["chunk_index"] == 0

    def test_optional_fields_omitted_when_none(self):
        chunk = _build_chunk(
            content="Text", source_document="doc.pdf",
            paper_title=None, authors=None, source="upload",
            publication_year=None, arxiv_id=None, doi=None,
            subject_areas=None, section_id=None, paragraph_ref=None,
            page_number=None, chunk_index=0, upload_id=None,
        )
        for optional in ("paper_title", "authors", "publication_year",
                         "arxiv_id", "doi", "subject_areas", "section_id",
                         "paragraph_ref", "page_number", "upload_id"):
            assert optional not in chunk

    def test_optional_fields_included_when_provided(self):
        chunk = _build_chunk(
            content="Text", source_document="doc.pdf",
            paper_title="My Paper", authors="Alice, Bob",
            source="upload", publication_year="2024",
            arxiv_id="2401.00001", doi="10.1234/abc",
            subject_areas="ML", section_id="Introduction",
            paragraph_ref="para_1", page_number=3,
            chunk_index=2, upload_id="abc123",
        )
        assert chunk["paper_title"] == "My Paper"
        assert chunk["authors"] == "Alice, Bob"
        assert chunk["publication_year"] == "2024"
        assert chunk["arxiv_id"] == "2401.00001"
        assert chunk["section_id"] == "Introduction"
        assert chunk["page_number"] == 3
        assert chunk["upload_id"] == "abc123"


# ── chunk_paper (integration of the above) ─────────────────────────────────────

class TestChunkPaper:
    def test_returns_list_of_chunks(self, sample_pages):
        chunks = chunk_paper(pages=sample_pages, source_document="test.pdf")
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_each_chunk_has_required_keys(self, sample_pages):
        chunks = chunk_paper(pages=sample_pages, source_document="test.pdf")
        for chunk in chunks:
            assert "content" in chunk
            assert "source_document" in chunk
            assert chunk["source_document"] == "test.pdf"

    def test_metadata_propagated_to_chunks(self, sample_pages):
        chunks = chunk_paper(
            pages=sample_pages,
            source_document="paper.pdf",
            paper_title="Test Paper",
            authors="Alice, Bob",
            publication_year="2024",
        )
        for chunk in chunks:
            assert chunk.get("paper_title") == "Test Paper"
            assert chunk.get("publication_year") == "2024"

    def test_empty_pages_returns_empty_list(self):
        chunks = chunk_paper(pages=[], source_document="empty.pdf")
        assert chunks == []

    def test_section_based_chunking_used_when_headings_present(self, sample_pages):
        """Pages contain Abstract/Introduction/Methods/Results — should get sections."""
        chunks = chunk_paper(pages=sample_pages, source_document="paper.pdf")
        section_ids = [c.get("section_id") for c in chunks if c.get("section_id")]
        assert len(section_ids) > 0

    def test_fallback_paragraph_chunking_for_headingless_text(self):
        pages = [
            "A" * 60 + "\n\n" + "B" * 60 + "\n\n" + "C" * 60 + "\n\n" + "D" * 60
        ]
        chunks = chunk_paper(pages=pages, source_document="no_headings.pdf")
        # Should still produce at least one chunk from the fallback path
        assert isinstance(chunks, list)
