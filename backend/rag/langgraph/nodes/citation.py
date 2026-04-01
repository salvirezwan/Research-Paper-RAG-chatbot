"""
Citation node: attach a structured references/sources block to the final answer.
Runs after the generator to ensure every response has proper citations.
"""

from typing import List, Dict, Any

from backend.rag.langgraph.state import GraphState
from backend.core.logging import logger


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

        citation_text = f"[{len(citations) + 1}]"
        if paper_title and paper_title != "Untitled":
            citation_text += f" {paper_title}"
        if authors and authors != "Unknown authors":
            citation_text += f" — {authors}"
        if year:
            citation_text += f" ({year})"

        if arxiv_id:
            link = f"https://arxiv.org/abs/{arxiv_id}"
            citation = f"[{citation_text}]({link})"
        elif doi:
            link = f"https://doi.org/{doi}"
            citation = f"[{citation_text}]({link})"
        else:
            citation = citation_text

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
