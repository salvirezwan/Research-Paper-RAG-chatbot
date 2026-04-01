from typing import Optional

from backend.models.uploaded_doc import PaperStatus
from backend.crud.uploaded_doc import update_paper_status
from backend.services.ingestion_service import run_ingestion_pipeline
from backend.core.exceptions import ProcessingError
from backend.core.logging import logger


async def process_upload_async(
    paper_id: str,
    file_path: str,
    filename: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    publication_year: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    doi: Optional[str] = None,
    subject_areas: Optional[str] = None,
) -> dict:
    """
    Background task: run the full ingestion pipeline for an uploaded PDF.
    Updates MongoDB status at each stage.
    """
    try:
        await update_paper_status(paper_id, PaperStatus.PROCESSING)

        result = await run_ingestion_pipeline(
            pdf_path=file_path,
            source_document=filename,
            paper_title=title,
            authors=authors,
            publication_year=publication_year,
            arxiv_id=arxiv_id,
            doi=doi,
            subject_areas=subject_areas,
            upload_id=paper_id,
        )

        chunk_count = result.get("chunks_created", 0)
        await update_paper_status(
            paper_id,
            PaperStatus.INDEXED,
            chunk_count=chunk_count,
        )

        logger.info(f"[UPLOAD_SERVICE] paper_id={paper_id} indexed: {chunk_count} chunks")
        return {"status": "success", "paper_id": paper_id, "chunks_indexed": chunk_count}

    except Exception as exc:
        logger.error(f"[UPLOAD_SERVICE] Failed for paper_id={paper_id}: {exc}")
        await update_paper_status(paper_id, PaperStatus.FAILED, error_message=str(exc))
        raise ProcessingError(f"Document processing failed: {exc}")
