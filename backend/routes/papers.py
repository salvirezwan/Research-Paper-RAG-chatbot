from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.core.exceptions import DocumentNotFoundError
from backend.core.logging import logger
from backend.crud.uploaded_doc import (
    count_papers,
    delete_paper,
    get_paper_by_id,
    list_papers,
)
from backend.models.uploaded_doc import PaperSource, PaperStatus
from backend.rag.vectorstore.chroma_client import chroma_client
from backend.schemas.paper_schema import PaperResponse
from backend.services.paper_fetch_service import fetch_paper_by_arxiv_id
from backend.utils.file_storage import delete_uploaded_file

router = APIRouter(prefix="/api/v1/papers", tags=["Papers"])


@router.get("", summary="List all indexed papers")
async def list_papers_endpoint(
    source: Optional[PaperSource] = Query(None),
    status: Optional[PaperStatus] = Query(None),
    publication_year: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    papers = await list_papers(
        source=source,
        status=status,
        publication_year=publication_year,
        limit=limit,
        offset=offset,
    )
    total = await count_papers(source=source, status=status)

    return {
        "papers": [
            {
                "paper_id": str(p.id),
                "filename": p.filename,
                "title": p.title,
                "authors": p.authors,
                "abstract": p.abstract,
                "source": p.source.value,
                "status": p.status.value,
                "publication_year": p.publication_year,
                "arxiv_id": p.arxiv_id,
                "doi": p.doi,
                "subject_areas": p.subject_areas,
                "chunk_count": p.chunk_count,
                "uploaded_at": p.uploaded_at.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
            }
            for p in papers
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: str):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    return PaperResponse(
        paper_id=str(paper.id),
        filename=paper.filename,
        title=paper.title,
        authors=paper.authors,
        abstract=paper.abstract,
        source=paper.source,
        status=paper.status,
        publication_year=paper.publication_year,
        arxiv_id=paper.arxiv_id,
        doi=paper.doi,
        subject_areas=paper.subject_areas,
        chunk_count=paper.chunk_count,
        uploaded_at=paper.uploaded_at,
        processed_at=paper.processed_at,
    )


@router.delete("/{paper_id}")
async def delete_paper_endpoint(paper_id: str):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    try:
        chroma_client.delete_by_document(paper.filename)
    except Exception as exc:
        logger.error(f"ChromaDB delete failed for {paper.filename}: {exc}")

    if paper.stored_path:
        delete_uploaded_file(paper.stored_path)

    success = await delete_paper(paper_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete paper record")

    return {"message": "Paper deleted", "paper_id": paper_id}


@router.post("/fetch/arxiv/{arxiv_id}")
async def fetch_arxiv_paper(arxiv_id: str):
    """
    Fetch a paper's metadata from arXiv by ID and save it to MongoDB.
    The paper's abstract is available for immediate RAG querying via live_fetch.
    """
    result = await fetch_paper_by_arxiv_id(arxiv_id)
    if not result:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch paper {arxiv_id} from arXiv",
        )

    logger.info(f"[PAPERS API] Fetched arxiv_id={arxiv_id}")
    return {"message": "Paper fetched and saved", **result}
