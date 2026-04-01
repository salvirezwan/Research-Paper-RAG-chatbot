"""
Generator node: build a context-augmented prompt from retrieved chunks,
call Groq LLM, and produce a cited research answer.
"""

from typing import List, Dict, Any
from urllib.parse import quote

from langchain_core.messages import HumanMessage, SystemMessage

from backend.rag.langgraph.state import GraphState
from backend.rag.llm_client import get_chat_model
from backend.core.config import settings
from backend.core.logging import logger

_VIEWER_BASE = f"http://localhost:{settings.STREAMLIT_PORT}/viewer"

_SYSTEM_PROMPT = """You are an expert academic research assistant.

Your role is to:
1. Answer questions accurately based on the provided research paper context
2. Cite sources using the citation numbers provided (e.g., [1], [2])
3. Synthesize information from multiple sources when relevant
4. Be precise, well-structured, and scholarly in tone
5. If the context is insufficient to answer the question, say so clearly

Always cite your sources using the citation numbers provided in the context.
When multiple sources support a point, cite all of them (e.g., [1][3])."""


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


def generator_node(state: GraphState) -> GraphState:
    """Generate a cited answer from retrieved chunks using Groq LLM."""
    query = state.get("user_query", "")
    retrieved_chunks = state.get("retrieved_chunks", [])

    llm = get_chat_model(temperature=0.3)

    # Build context and citation list
    context_parts: List[str] = []
    citations: List[str] = []

    for i, chunk in enumerate(retrieved_chunks, 1):
        chunk_text = chunk.get("text", "")
        metadata = chunk.get("metadata", {})

        if not chunk_text:
            continue

        paper_title = metadata.get("paper_title") or "Untitled"
        authors = metadata.get("authors") or "Unknown authors"
        source = metadata.get("source", "")
        year = metadata.get("publication_year", "")
        arxiv_id = metadata.get("arxiv_id", "")
        doi = metadata.get("doi", "")
        section_id = metadata.get("section_id", "")
        upload_id = metadata.get("upload_id", "")
        page_number = metadata.get("page_number")

        # Build citation label
        citation_label = f"[{i}]"
        if paper_title and paper_title != "Untitled":
            citation_label += f" {paper_title}"
        if authors and authors != "Unknown authors":
            citation_label += f" — {authors}"
        if year:
            citation_label += f" ({year})"
        if section_id:
            citation_label += f", §{section_id}"

        # Build local viewer link (primary — opens PDF at the right page)
        viewer_link = _build_viewer_link(upload_id, page_number, section_id)

        if viewer_link:
            citation_full = f"[{citation_label}]({viewer_link})"
        elif arxiv_id:
            citation_full = f"[{citation_label}](https://arxiv.org/abs/{arxiv_id})"
        elif doi:
            citation_full = f"[{citation_label}](https://doi.org/{doi})"
        else:
            citation_full = citation_label

        # Add external reference link as secondary info
        external_ref = ""
        if viewer_link and arxiv_id:
            external_ref = f"  ↗ [arXiv:{arxiv_id}](https://arxiv.org/abs/{arxiv_id})"
        elif viewer_link and doi:
            external_ref = f"  ↗ [DOI](https://doi.org/{doi})"

        if external_ref:
            citation_full += external_ref

        logger.debug(
            f"[GENERATOR] Citation [{i}]: title='{paper_title}', "
            f"authors='{authors}', source='{source}', "
            f"page={page_number}, section='{section_id}'"
        )

        context_parts.append(f"[{i}]\n{chunk_text}")
        citations.append(citation_full)

    context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."

    # Build user message
    user_content = f"Research Question: {query}\n\n"

    if context_parts:
        user_content += "Relevant Research Context:\n" + context + "\n\n"
    else:
        user_content += (
            "No relevant documents were found in the database. "
            "Please indicate this in your response.\n\n"
        )

    user_content += (
        "Please provide a comprehensive, well-structured answer based on "
        "the research context above. Include inline citations [1], [2], etc. "
        "where applicable."
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    try:
        response = llm.invoke(messages)
        final_answer = response.content.strip()
    except Exception as e:
        logger.error(f"[GENERATOR] LLM invocation failed: {e}")
        final_answer = (
            f"I encountered an error while generating the answer: {str(e)}\n\n"
            f"Based on the retrieved context, here is a summary:\n{context[:500]}"
        )

    logger.info(
        f"[GENERATOR] query='{query[:60]}' → "
        f"answer_len={len(final_answer)}, citations={len(citations)}"
    )

    return {**state, "final_answer": final_answer, "citations": citations}

