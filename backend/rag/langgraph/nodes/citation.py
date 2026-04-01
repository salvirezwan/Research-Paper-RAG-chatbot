"""
Citation node: attach a structured references/sources block to the final answer.
Runs after the generator to ensure every response has proper citations.
"""

from typing import List, Dict, Any
from urllib.parse import quote

from backend.rag.langgraph.state import GraphState
from backend.core.config import settings
from backend.core.logging import logger

_VIEWER_BASE = f"http://localhost:{settings.STREAMLIT_PORT}/viewer"


def _build_viewer_link(
    upload_id: str = "",
    page_number: int | None = None,
    section_id: str = "",
) -> str:
    """Build a local viewer URL with optional page & section params."""
    if not upload_id:
        return ""
    params = [f"doc={upload_id}"]
    if page_number is not None and page_number >= 1:
        params.append(f"page={page_number}")
    if section_id:
        params.append(f"section={quote(section_id)}")
    return f"{_VIEWER_BASE}?{'&'.join(params)}"


def citation_node(state: GraphState) -> GraphState:
    """
    Append a formatted 'Sources' section to the final answer.

    Uses the citations list built by the generator node and the
    retrieved_chunks metadata to produce a clean bibliography block.
    """
    final_answer = state.get("final_answer", "")
    citations = state.get("citations", [])
    retrieved_chunks = state.get("retrieved_chunks", [])

    if not final_answer:
        return state

    # If no citations were generated at all, try building from chunks
    if not citations and retrieved_chunks:
        citations = _build_citations_from_chunks(retrieved_chunks)

    if not citations:
        logger.info("[CITATION] No citations to attach")
        return state

    # Build the sources block
    sources_block = _format_sources_block(citations)

    # Only append if the answer doesn't already contain a Sources section
    if "**Sources:**" not in final_answer and "**References:**" not in final_answer:
        final_answer = final_answer.rstrip() + "\n\n" + sources_block

    logger.info(f"[CITATION] Attached {len(citations)} citations to answer")
    return {**state, "final_answer": final_answer, "citations": citations}


def _build_citations_from_chunks(
    chunks: List[Dict[str, Any]],
) -> List[str]:
    """Fallback: build citation strings from chunk metadata."""
    citations: List[str] = []
    seen_titles: set = set()

    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        paper_title = metadata.get("paper_title") or "Untitled"

        # Deduplicate by paper title
        if paper_title in seen_titles:
            continue
        seen_titles.add(paper_title)

        authors = metadata.get("authors") or "Unknown authors"
        year = metadata.get("publication_year", "")
        arxiv_id = metadata.get("arxiv_id", "")
        doi = metadata.get("doi", "")
        upload_id = metadata.get("upload_id", "")
        page_number = metadata.get("page_number")
        section_id = metadata.get("section_id", "")

        citation_label = f"[{len(citations) + 1}]"
        if paper_title and paper_title != "Untitled":
            citation_label += f" {paper_title}"
        if authors and authors != "Unknown authors":
            citation_label += f" — {authors}"
        if year:
            citation_label += f" ({year})"

        # Primary link: local viewer with page navigation
        viewer_link = _build_viewer_link(upload_id, page_number, section_id)

        if viewer_link:
            citation = f"[{citation_label}]({viewer_link})"
        elif arxiv_id:
            citation = f"[{citation_label}](https://arxiv.org/abs/{arxiv_id})"
        elif doi:
            citation = f"[{citation_label}](https://doi.org/{doi})"
        else:
            citation = citation_label

        # Secondary external link
        if viewer_link and arxiv_id:
            citation += f"  ↗ [arXiv:{arxiv_id}](https://arxiv.org/abs/{arxiv_id})"
        elif viewer_link and doi:
            citation += f"  ↗ [DOI](https://doi.org/{doi})"

        citations.append(citation)

    return citations


def _format_sources_block(citations: List[str]) -> str:
    """Format a clean markdown sources block."""
    if not citations:
        return ""

    lines = ["**Sources:**"]
    for citation in citations:
        lines.append(f"- {citation}")

    return "\n".join(lines)

