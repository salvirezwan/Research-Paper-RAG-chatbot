"""
Service for fetching individual papers from arXiv by ID and persisting
their metadata to MongoDB (without full-text indexing — that goes through
the live_fetch LangGraph node at query time).
"""
from typing import Optional, Dict, Any

import httpx

from backend.crud.uploaded_doc import (
    get_paper_by_arxiv_id,
    create_paper_record,
)
from backend.models.uploaded_doc import PaperSource, PaperStatus
from backend.core.logging import logger

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


async def fetch_paper_by_arxiv_id(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch paper metadata from arXiv and upsert into MongoDB.

    Returns the paper metadata dict, or None on failure.
    """
    # Return existing record if already saved
    existing = await get_paper_by_arxiv_id(arxiv_id)
    if existing:
        logger.info(f"[PAPER_FETCH] arxiv_id={arxiv_id} already in DB")
        return _paper_to_dict(existing)

    params = {
        "id_list": arxiv_id,
        "max_results": 1,
    }

    try:
        resp = httpx.get(_ARXIV_API, params=params, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(f"[PAPER_FETCH] arXiv request failed for {arxiv_id}: {exc}")
        return None

    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.error(f"[PAPER_FETCH] XML parse error: {exc}")
        return None

    entry = root.find("atom:entry", _ARXIV_NS)
    if entry is None:
        logger.warning(f"[PAPER_FETCH] No entry found for arxiv_id={arxiv_id}")
        return None

    title = (entry.findtext("atom:title", "", _ARXIV_NS) or "").strip()
    summary = (entry.findtext("atom:summary", "", _ARXIV_NS) or "").strip()
    published = (entry.findtext("atom:published", "", _ARXIV_NS) or "")[:4]

    authors = [
        (a.findtext("atom:name", "", _ARXIV_NS) or "").strip()
        for a in entry.findall("atom:author", _ARXIV_NS)
    ]

    categories = [
        c.attrib.get("term", "")
        for c in entry.findall("atom:category", _ARXIV_NS)
    ]

    paper = await create_paper_record(
        filename=f"{arxiv_id}.pdf",
        stored_path="",
        file_hash=arxiv_id,
        source=PaperSource.ARXIV,
        status=PaperStatus.INDEXED,
        title=title,
        authors=authors,
        abstract=summary,
        publication_year=published,
        arxiv_id=arxiv_id,
        subject_areas=categories,
    )

    logger.info(f"[PAPER_FETCH] Saved arxiv_id={arxiv_id} to MongoDB (ID={paper.id})")
    return _paper_to_dict(paper)


def _paper_to_dict(paper) -> Dict[str, Any]:
    return {
        "paper_id": str(paper.id),
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "arxiv_id": paper.arxiv_id,
        "publication_year": paper.publication_year,
        "source": paper.source.value if paper.source else None,
        "subject_areas": paper.subject_areas,
    }
