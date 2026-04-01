import re
from typing import List, Dict, Any, Optional

from backend.core.config import settings
from backend.core.logging import logger


# Standard section headings found in research papers
_SECTION_PATTERNS = [
    # Numbered sections: "1. Introduction", "2 Related Work", "3.1 Datasets"
    r"^(\d+(?:\.\d+)*\.?)\s+([A-Z][^\n]{2,80})$",
    # Named sections (all-caps or title-case): "ABSTRACT", "Introduction", "REFERENCES"
    r"^(Abstract|Introduction|Related Work|Background|Methodology|Method|Methods|"
    r"Experiments?|Experimental Setup|Results?|Discussion|Conclusion|Conclusions|"
    r"Future Work|Acknowledgements?|References?|Appendix|Limitations?|"
    r"Ethical Considerations?)[\s:]*$",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _SECTION_PATTERNS]


def chunk_paper(
    pages: List[str],
    source_document: str,
    paper_title: Optional[str] = None,
    authors: Optional[str] = None,
    source: str = "upload",
    publication_year: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    doi: Optional[str] = None,
    subject_areas: Optional[str] = None,
    upload_id: Optional[str] = None,
    page_offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Chunk a research paper by detected sections with overlap fallback.

    Returns a list of chunk dicts ready for embedding and indexing.
    """
    full_text = "\n\n".join(pages)
    sections = _split_into_sections(full_text)

    if sections:
        chunks = _chunks_from_sections(
            sections=sections,
            pages=pages,
            source_document=source_document,
            paper_title=paper_title,
            authors=authors,
            source=source,
            publication_year=publication_year,
            arxiv_id=arxiv_id,
            doi=doi,
            subject_areas=subject_areas,
            upload_id=upload_id,
            page_offset=page_offset,
        )
    else:
        # Fallback: paragraph-level chunking with size limit + overlap
        chunks = _chunk_by_paragraphs(
            pages=pages,
            source_document=source_document,
            paper_title=paper_title,
            authors=authors,
            source=source,
            publication_year=publication_year,
            arxiv_id=arxiv_id,
            doi=doi,
            subject_areas=subject_areas,
            upload_id=upload_id,
            page_offset=page_offset,
        )

    logger.info(f"Chunked '{source_document}': {len(chunks)} chunks")
    return chunks


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _split_into_sections(full_text: str) -> List[tuple[str, str]]:
    """
    Split text into (heading, body) tuples by detecting section headings.
    Returns empty list if no headings found.
    """
    lines = full_text.split("\n")
    sections: List[tuple[str, List[str]]] = []
    current_heading: Optional[str] = None
    current_body: List[str] = []

    for line in lines:
        stripped = line.strip()
        if _is_section_heading(stripped):
            if current_body:
                sections.append((current_heading, "\n".join(current_body)))
            current_heading = stripped
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        sections.append((current_heading, "\n".join(current_body)))

    return [(h, b) for h, b in sections if b.strip()]


def _is_section_heading(line: str) -> bool:
    if not line or len(line) > 100:
        return False
    return any(p.match(line) for p in _COMPILED_PATTERNS)


def _chunks_from_sections(
    sections: List[tuple[str, str]],
    pages: List[str],
    source_document: str,
    paper_title: Optional[str],
    authors: Optional[str],
    source: str,
    publication_year: Optional[str],
    arxiv_id: Optional[str],
    doi: Optional[str],
    subject_areas: Optional[str],
    upload_id: Optional[str],
    page_offset: int,
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for section_idx, (heading, body) in enumerate(sections):
        section_id = heading.strip() if heading else f"section_{section_idx + 1}"
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

        current_chunk: List[str] = []
        current_size = 0
        para_idx = 0

        for para in paragraphs:
            para_size = len(para)

            if current_size + para_size > settings.CHUNK_SIZE and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                if len(chunk_text.strip()) >= 50:
                    chunks.append(_build_chunk(
                        content=chunk_text,
                        source_document=source_document,
                        paper_title=paper_title,
                        authors=authors,
                        source=source,
                        publication_year=publication_year,
                        arxiv_id=arxiv_id,
                        doi=doi,
                        subject_areas=subject_areas,
                        section_id=section_id,
                        paragraph_ref=f"para_{para_idx}",
                        page_number=_find_page(chunk_text, pages, page_offset),
                        chunk_index=chunk_index,
                        upload_id=upload_id,
                    ))
                    chunk_index += 1

                # Overlap: keep last paragraph
                overlap = current_chunk[-1:] if current_chunk else []
                current_chunk = overlap
                current_size = sum(len(p) for p in current_chunk)

            current_chunk.append(para)
            current_size += para_size + 2
            para_idx += 1

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if len(chunk_text.strip()) >= 50:
                chunks.append(_build_chunk(
                    content=chunk_text,
                    source_document=source_document,
                    paper_title=paper_title,
                    authors=authors,
                    source=source,
                    publication_year=publication_year,
                    arxiv_id=arxiv_id,
                    doi=doi,
                    subject_areas=subject_areas,
                    section_id=section_id,
                    paragraph_ref=f"para_{para_idx}",
                    page_number=_find_page(chunk_text, pages, page_offset),
                    chunk_index=chunk_index,
                    upload_id=upload_id,
                ))
                chunk_index += 1

    return chunks


def _chunk_by_paragraphs(
    pages: List[str],
    source_document: str,
    paper_title: Optional[str],
    authors: Optional[str],
    source: str,
    publication_year: Optional[str],
    arxiv_id: Optional[str],
    doi: Optional[str],
    subject_areas: Optional[str],
    upload_id: Optional[str],
    page_offset: int,
) -> List[Dict[str, Any]]:
    full_text = "\n\n".join(pages)
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

    chunks: List[Dict[str, Any]] = []
    current_chunk: List[str] = []
    current_size = 0
    chunk_index = 0

    for para in paragraphs:
        para_size = len(para)

        if current_size + para_size > settings.CHUNK_SIZE and current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if len(chunk_text.strip()) >= 50:
                chunks.append(_build_chunk(
                    content=chunk_text,
                    source_document=source_document,
                    paper_title=paper_title,
                    authors=authors,
                    source=source,
                    publication_year=publication_year,
                    arxiv_id=arxiv_id,
                    doi=doi,
                    subject_areas=subject_areas,
                    section_id=f"chunk_{chunk_index + 1}",
                    paragraph_ref=None,
                    page_number=_find_page(chunk_text, pages, page_offset),
                    chunk_index=chunk_index,
                    upload_id=upload_id,
                ))
                chunk_index += 1

            overlap = current_chunk[-1:] if current_chunk else []
            current_chunk = overlap
            current_size = sum(len(p) for p in current_chunk)

        current_chunk.append(para)
        current_size += para_size + 2

    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        if len(chunk_text.strip()) >= 50:
            chunks.append(_build_chunk(
                content=chunk_text,
                source_document=source_document,
                paper_title=paper_title,
                authors=authors,
                source=source,
                publication_year=publication_year,
                arxiv_id=arxiv_id,
                doi=doi,
                subject_areas=subject_areas,
                section_id=f"chunk_{chunk_index + 1}",
                paragraph_ref=None,
                page_number=_find_page(chunk_text, pages, page_offset),
                chunk_index=chunk_index,
                upload_id=upload_id,
            ))

    return chunks


def _build_chunk(
    content: str,
    source_document: str,
    paper_title: Optional[str],
    authors: Optional[str],
    source: str,
    publication_year: Optional[str],
    arxiv_id: Optional[str],
    doi: Optional[str],
    subject_areas: Optional[str],
    section_id: Optional[str],
    paragraph_ref: Optional[str],
    page_number: Optional[int],
    chunk_index: int,
    upload_id: Optional[str],
) -> Dict[str, Any]:
    chunk: Dict[str, Any] = {
        "content": content,
        "source_document": source_document,
        "source": source,
        "chunk_index": chunk_index,
    }
    if paper_title:
        chunk["paper_title"] = paper_title
    if authors:
        chunk["authors"] = authors
    if publication_year:
        chunk["publication_year"] = publication_year
    if arxiv_id:
        chunk["arxiv_id"] = arxiv_id
    if doi:
        chunk["doi"] = doi
    if subject_areas:
        chunk["subject_areas"] = subject_areas
    if section_id:
        chunk["section_id"] = section_id
    if paragraph_ref:
        chunk["paragraph_ref"] = paragraph_ref
    if page_number is not None:
        chunk["page_number"] = page_number
    if upload_id:
        chunk["upload_id"] = upload_id
    return chunk


def _find_page(text: str, pages: List[str], page_offset: int = 0) -> Optional[int]:
    if not text or not pages:
        return None

    search_snippet = " ".join(text.split())[:100]
    if not search_snippet:
        return None

    first_words = " ".join(search_snippet.split()[:5])

    for page_idx, page_text in enumerate(pages):
        normalized_page = " ".join(page_text.split())
        if search_snippet in normalized_page:
            return page_idx + 1 + page_offset
        if first_words and first_words in normalized_page:
            return page_idx + 1 + page_offset

    return 1 + page_offset
