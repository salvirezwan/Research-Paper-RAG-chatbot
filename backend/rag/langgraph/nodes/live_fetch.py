"""
Live-fetch node: retrieve papers from arXiv / Semantic Scholar by keyword,
chunk them, embed into ChromaDB, and return chunks to the pipeline.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

import httpx

from backend.rag.langgraph.state import GraphState
from backend.rag.ingestion.chunker import chunk_paper
from backend.rag.ingestion.indexer import index_chunks
from backend.core.config import settings
from backend.core.logging import logger

# ---------------------------------------------------------------------------
# arXiv helpers
# ---------------------------------------------------------------------------

_ARXIV_API = "http://export.arxiv.org/api/query"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _search_arxiv(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search arXiv API and return paper metadata + abstract text."""
    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    try:
        resp = httpx.get(_ARXIV_API, params=params, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(f"arXiv API request failed: {exc}")
        return []

    return _parse_arxiv_xml(resp.text)


def _parse_arxiv_xml(xml_text: str) -> List[Dict[str, Any]]:
    papers: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error(f"Failed to parse arXiv XML: {exc}")
        return papers

    for entry in root.findall("atom:entry", _ARXIV_NS):
        title = (entry.findtext("atom:title", "", _ARXIV_NS) or "").strip()
        summary = (entry.findtext("atom:summary", "", _ARXIV_NS) or "").strip()
        published = (entry.findtext("atom:published", "", _ARXIV_NS) or "")[:4]

        # Authors
        authors = [
            (a.findtext("atom:name", "", _ARXIV_NS) or "").strip()
            for a in entry.findall("atom:author", _ARXIV_NS)
        ]
        authors_str = ", ".join(a for a in authors if a)

        # arXiv ID from <id> tag
        raw_id = (entry.findtext("atom:id", "", _ARXIV_NS) or "")
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

        # Categories
        categories = [
            c.attrib.get("term", "")
            for c in entry.findall("atom:category", _ARXIV_NS)
        ]

        if title and summary:
            papers.append({
                "paper_title": title,
                "authors": authors_str,
                "abstract": summary,
                "publication_year": published,
                "arxiv_id": arxiv_id,
                "source": "arxiv",
                "subject_areas": ", ".join(categories),
            })

    return papers


# ---------------------------------------------------------------------------
# Semantic Scholar helpers
# ---------------------------------------------------------------------------

_S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def _search_semantic_scholar(
    query: str, max_results: int = 5
) -> List[Dict[str, Any]]:
    """Search Semantic Scholar and return paper metadata + abstract."""
    headers: Dict[str, str] = {}
    if settings.SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY

    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,year,externalIds,fieldsOfStudy",
    }

    try:
        resp = httpx.get(_S2_API, params=params, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"Semantic Scholar API request failed: {exc}")
        return []

    papers: List[Dict[str, Any]] = []
    for item in data.get("data", []):
        title = (item.get("title") or "").strip()
        abstract = (item.get("abstract") or "").strip()
        if not title or not abstract:
            continue

        authors = ", ".join(
            (a.get("name") or "") for a in (item.get("authors") or [])
        )
        ext_ids = item.get("externalIds") or {}
        fields = item.get("fieldsOfStudy") or []

        papers.append({
            "paper_title": title,
            "authors": authors,
            "abstract": abstract,
            "publication_year": str(item.get("year", "")),
            "arxiv_id": ext_ids.get("ArXiv", ""),
            "doi": ext_ids.get("DOI", ""),
            "source": "semantic_scholar",
            "subject_areas": ", ".join(fields),
        })

    return papers


# ---------------------------------------------------------------------------
# Convert fetched papers into chunk dicts & index them
# ---------------------------------------------------------------------------

def _papers_to_chunks(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn paper metadata (with abstract) into chunked + indexed form."""
    all_chunks: List[Dict[str, Any]] = []

    for paper in papers:
        abstract = paper.get("abstract", "")
        if not abstract:
            continue

        # Use chunker with abstract as a single "page"
        chunks = chunk_paper(
            pages=[abstract],
            source_document=paper.get("arxiv_id") or paper.get("paper_title", "unknown"),
            paper_title=paper.get("paper_title"),
            authors=paper.get("authors"),
            source=paper.get("source", "arxiv"),
            publication_year=paper.get("publication_year"),
            arxiv_id=paper.get("arxiv_id"),
            doi=paper.get("doi"),
            subject_areas=paper.get("subject_areas"),
        )

        all_chunks.extend(chunks)

    # Index into ChromaDB so future queries can retrieve them locally
    if all_chunks:
        try:
            result = index_chunks(all_chunks)
            logger.info(
                f"[LIVE_FETCH] Indexed {result.get('chunks_indexed', 0)} "
                f"chunks from {len(papers)} papers"
            )
        except Exception as exc:
            logger.error(f"[LIVE_FETCH] Indexing failed: {exc}")

    return all_chunks


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

def live_fetch_node(state: GraphState) -> GraphState:
    """
    Fetch papers from arXiv and/or Semantic Scholar based on the user query,
    chunk them, index into ChromaDB, and add to pipeline state.
    """
    query = state.get("user_query", "")
    max_results = settings.ARXIV_MAX_RESULTS or 5

    if not query:
        logger.warning("[LIVE_FETCH] No query provided, skipping live fetch")
        return {**state, "live_papers": [], "live_chunks": []}

    # 1. Try arXiv first
    logger.info(f"[LIVE_FETCH] Searching arXiv for: '{query[:80]}'")
    papers = _search_arxiv(query, max_results=max_results)

    # 2. Fallback / supplement with Semantic Scholar
    if len(papers) < max_results:
        remaining = max_results - len(papers)
        logger.info(
            f"[LIVE_FETCH] Supplementing with Semantic Scholar ({remaining} more)"
        )
        s2_papers = _search_semantic_scholar(query, max_results=remaining)
        papers.extend(s2_papers)

    if not papers:
        logger.warning("[LIVE_FETCH] No papers found from external sources")
        return {**state, "live_papers": [], "live_chunks": []}

    logger.info(f"[LIVE_FETCH] Found {len(papers)} papers, chunking & indexing")

    # 3. Chunk and index
    live_chunks = _papers_to_chunks(papers)

    # 4. Convert chunks to the same format as retrieved_chunks
    formatted_chunks: List[Dict[str, Any]] = []
    for chunk in live_chunks:
        formatted_chunks.append({
            "text": chunk.get("content", ""),
            "score": 1.0,  # Live-fetched papers are assumed highly relevant
            "metadata": {
                "source_document": chunk.get("source_document", ""),
                "paper_title": chunk.get("paper_title"),
                "authors": chunk.get("authors"),
                "source": chunk.get("source", "arxiv"),
                "publication_year": chunk.get("publication_year"),
                "arxiv_id": chunk.get("arxiv_id"),
                "doi": chunk.get("doi"),
                "section_id": chunk.get("section_id"),
                "page_number": chunk.get("page_number"),
                "chunk_index": chunk.get("chunk_index", 0),
            },
        })

    logger.info(
        f"[LIVE_FETCH] query='{query[:60]}' → {len(papers)} papers, "
        f"{len(formatted_chunks)} chunks"
    )

    return {
        **state,
        "live_papers": papers,
        "live_chunks": formatted_chunks,
        # Merge live chunks into retrieved_chunks so downstream nodes work uniformly
        "retrieved_chunks": state.get("retrieved_chunks", []) + formatted_chunks,
    }
