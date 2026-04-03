"""
Service for fetching individual papers from arXiv by ID, downloading the full
PDF, and running the ingestion pipeline to index the content into ChromaDB.
"""
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any

import httpx

from backend.crud.uploaded_doc import (
    get_paper_by_arxiv_id,
    create_paper_record,
    update_paper_status,
)
from backend.models.uploaded_doc import PaperSource, PaperStatus
from backend.services.ingestion_service import run_ingestion_pipeline
from backend.utils.file_storage import save_uploaded_file, get_file_hash_from_bytes
from backend.core.logging import logger

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


async def fetch_paper_by_arxiv_id(arxiv_id: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch paper metadata from arXiv, download the full PDF, and index it.
    Returns the paper metadata dict, or None on failure.
    """
    # Return existing record if already saved
    existing = await get_paper_by_arxiv_id(arxiv_id)
    if existing:
        logger.info(f"[PAPER_FETCH] arxiv_id={arxiv_id} already in DB")
        return _paper_to_dict(existing)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # ── 1. Fetch metadata ─────────────────────────────────────────────────
        try:
            resp = await client.get(_ARXIV_API, params={"id_list": arxiv_id, "max_results": 1}, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(f"[PAPER_FETCH] arXiv metadata request failed for {arxiv_id}: {exc}")
            return None

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

        # ── 2. Download PDF ───────────────────────────────────────────────────
        pdf_url = _ARXIV_PDF.format(arxiv_id=arxiv_id)
        try:
            pdf_resp = await client.get(pdf_url, timeout=90.0)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
        except httpx.HTTPError as exc:
            logger.error(f"[PAPER_FETCH] PDF download failed for {arxiv_id}: {exc}")
            return None

    # ── 3. Save PDF to disk ───────────────────────────────────────────────────
    filename = f"{arxiv_id}.pdf"
    file_hash = get_file_hash_from_bytes(pdf_bytes)
    stored_path = save_uploaded_file(pdf_bytes, filename, source="arxiv")

    # ── 4. Create MongoDB record with PROCESSING status ───────────────────────
    paper = await create_paper_record(
        filename=filename,
        stored_path=stored_path,
        file_hash=file_hash,
        source=PaperSource.ARXIV,
        status=PaperStatus.PROCESSING,
        title=title,
        authors=authors,
        abstract=summary,
        publication_year=published,
        arxiv_id=arxiv_id,
        subject_areas=categories,
        session_id=session_id,
    )
    paper_id = str(paper.id)
    logger.info(f"[PAPER_FETCH] Saved arxiv_id={arxiv_id} to MongoDB (ID={paper_id}), starting ingestion")

    # ── 5. Run ingestion pipeline ─────────────────────────────────────────────
    try:
        result = await run_ingestion_pipeline(
            pdf_path=stored_path,
            source_document=filename,
            paper_title=title,
            authors=", ".join(authors) if authors else None,
            publication_year=published,
            arxiv_id=arxiv_id,
            upload_id=paper_id,
        )
        chunk_count = result.get("chunks_created", 0)
        await update_paper_status(paper_id, PaperStatus.INDEXED, chunk_count=chunk_count)
        logger.info(f"[PAPER_FETCH] Indexed arxiv_id={arxiv_id}: {chunk_count} chunks")
        paper.status = PaperStatus.INDEXED
        paper.chunk_count = chunk_count
    except Exception as exc:
        logger.error(f"[PAPER_FETCH] Ingestion failed for arxiv_id={arxiv_id}: {exc}")
        await update_paper_status(paper_id, PaperStatus.FAILED, error_message=str(exc))
        paper.status = PaperStatus.FAILED

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
        "status": paper.status.value if paper.status else None,
        "chunk_count": paper.chunk_count,
    }
