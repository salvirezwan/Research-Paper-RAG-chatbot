import json
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.core.config import settings
from backend.core.exceptions import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    FileSizeExceededError,
    InvalidFileTypeError,
)
from backend.core.logging import logger
from backend.crud.uploaded_doc import (
    count_papers,
    create_paper_record,
    delete_paper,
    get_paper_by_hash,
    get_paper_by_id,
    list_papers,
    update_paper_status,
)
from backend.models.uploaded_doc import PaperSource, PaperStatus
from backend.rag.vectorstore.chroma_client import chroma_client
from backend.schemas.upload_schema import (
    PaperListResponse,
    UploadRequest,
    UploadResponse,
    UploadStatusResponse,
)
from backend.services.upload_service import process_upload_async
from backend.utils.file_storage import (
    delete_uploaded_file,
    get_file_hash_from_bytes,
    save_uploaded_file,
)

router = APIRouter(prefix="/api/v1", tags=["Upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="Research paper PDF"),
    metadata: Optional[str] = Form(None, description='Optional JSON: {"title": "...", "authors": "..."}'),
    force_reupload: bool = Form(False),
    session_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    if not file.content_type or file.content_type not in settings.ALLOWED_FILE_TYPES:
        raise InvalidFileTypeError()

    content = await file.read()

    if len(content) > settings.MAX_FILE_SIZE:
        raise FileSizeExceededError()

    file_hash = get_file_hash_from_bytes(content)

    existing = await get_paper_by_hash(file_hash)
    if existing:
        if not force_reupload:
            raise DuplicateDocumentError()
        # Remove old vectors and record to allow clean re-upload
        try:
            chroma_client.delete_by_document(existing.filename)
        except Exception as exc:
            logger.warning(f"Could not delete old vectors: {exc}")
        delete_uploaded_file(existing.stored_path)
        await delete_paper(str(existing.id))
        logger.info(f"Cleared existing paper for re-upload: {existing.filename}")

    filename = file.filename or "unknown.pdf"

    # Parse optional metadata JSON
    meta_obj: Optional[UploadRequest] = None
    if metadata:
        try:
            meta_obj = UploadRequest(**json.loads(metadata))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {exc}")

    title = meta_obj.title if meta_obj else None
    authors = meta_obj.authors if meta_obj else None
    publication_year = meta_obj.publication_year if meta_obj else None

    stored_path = save_uploaded_file(content, filename, source="upload")

    paper = await create_paper_record(
        filename=filename,
        stored_path=stored_path,
        file_hash=file_hash,
        source=PaperSource.UPLOAD,
        status=PaperStatus.UPLOADED,
        title=title,
        authors=[a.strip() for a in authors.split(",")] if authors else None,
        publication_year=publication_year,
        session_id=session_id,
    )

    paper_id = str(paper.id)

    background_tasks.add_task(
        process_upload_async,
        paper_id=paper_id,
        file_path=stored_path,
        filename=filename,
        title=title,
        authors=authors,
        publication_year=publication_year,
    )

    logger.info(f"Document uploaded: {filename} (ID: {paper_id})")

    return UploadResponse(
        paper_id=paper_id,
        filename=filename,
        status=PaperStatus.UPLOADED.value,
        message="Paper uploaded successfully. Processing in background.",
    )


@router.get("/upload/{paper_id}", response_model=UploadStatusResponse)
async def get_upload_status(paper_id: str):
    try:
        paper = await get_paper_by_id(paper_id)
    except Exception:
        raise DocumentNotFoundError()

    if not paper:
        raise DocumentNotFoundError()

    return UploadStatusResponse(
        paper_id=paper_id,
        status=paper.status,
        filename=paper.filename,
        chunk_count=paper.chunk_count,
        error_message=paper.error_message,
        uploaded_at=paper.uploaded_at,
        processed_at=paper.processed_at,
    )


@router.get("/uploads", response_model=PaperListResponse)
async def list_uploaded_papers(
    source: Optional[PaperSource] = Query(None),
    status: Optional[PaperStatus] = Query(None),
    publication_year: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
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

    return PaperListResponse(
        papers=[
            {
                "id": str(p.id),
                "filename": p.filename,
                "title": p.title,
                "authors": p.authors,
                "source": p.source.value,
                "status": p.status.value,
                "publication_year": p.publication_year,
                "arxiv_id": p.arxiv_id,
                "chunk_count": p.chunk_count,
                "uploaded_at": p.uploaded_at.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
            }
            for p in papers
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/upload/{paper_id}")
async def delete_document(paper_id: str):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    try:
        chroma_client.delete_by_document(paper.filename)
    except Exception as exc:
        logger.error(f"Error deleting from ChromaDB: {exc}")

    delete_uploaded_file(paper.stored_path)

    success = await delete_paper(paper_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document record")

    return {"message": "Document deleted successfully", "paper_id": paper_id}


@router.post("/upload/{paper_id}/reindex")
async def reindex_document(
    paper_id: str,
    background_tasks: BackgroundTasks,
):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    # arXiv papers fetched with old code have no stored PDF — re-fetch instead
    if paper.arxiv_id and (not paper.stored_path or not os.path.exists(paper.stored_path)):
        from backend.crud.uploaded_doc import delete_paper as _delete_paper
        from backend.services.paper_fetch_service import fetch_paper_by_arxiv_id
        try:
            chroma_client.delete_by_document(paper.filename)
        except Exception:
            pass
        await _delete_paper(paper_id)
        background_tasks.add_task(fetch_paper_by_arxiv_id, paper.arxiv_id)
        return {"message": "Re-fetching and indexing from arXiv", "paper_id": paper_id}

    try:
        chroma_client.delete_by_document(paper.filename)
    except Exception as exc:
        logger.error(f"Error deleting existing vectors: {exc}")

    await update_paper_status(paper_id, PaperStatus.UPLOADED, chunk_count=0)

    background_tasks.add_task(
        process_upload_async,
        paper_id=paper_id,
        file_path=paper.stored_path,
        filename=paper.filename,
        title=paper.title,
        authors=", ".join(paper.authors) if paper.authors else None,
        publication_year=paper.publication_year,
        arxiv_id=paper.arxiv_id,
        doi=paper.doi,
    )

    return {"message": "Re-indexing started", "paper_id": paper_id}


@router.get("/uploads/{paper_id}/view")
async def view_document(paper_id: str):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    if not paper.stored_path or not os.path.exists(paper.stored_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=paper.stored_path,
        media_type="application/pdf",
        filename=paper.filename,
        headers={"Content-Disposition": f'inline; filename="{paper.filename}"'},
    )
