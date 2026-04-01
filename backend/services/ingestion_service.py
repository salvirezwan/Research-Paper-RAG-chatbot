from typing import Optional

from backend.rag.ingestion.parser import parse_pdf
from backend.rag.ingestion.cleaner import clean_pages
from backend.rag.ingestion.chunker import chunk_paper
from backend.rag.ingestion.indexer import index_chunks
from backend.core.logging import logger
from backend.crud.checkpoint import (
    create_checkpoint,
    get_checkpoint,
    mark_step_failed,
)


async def run_ingestion_pipeline(
    pdf_path: str,
    source_document: str,
    paper_title: Optional[str] = None,
    authors: Optional[str] = None,
    publication_year: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    doi: Optional[str] = None,
    subject_areas: Optional[str] = None,
    upload_id: Optional[str] = None,
) -> dict:
    """
    Parse → clean → chunk → index a research paper PDF.

    Each step is checkpointed in MongoDB so the pipeline can resume on failure.
    """
    logger.info(f"[INGESTION] Starting pipeline for '{source_document}'")

    # ------------------------------------------------------------------
    # Step 1: Parse PDF → list of page strings
    # ------------------------------------------------------------------
    parse_cp = await get_checkpoint(upload_id, "parsing") if upload_id else None

    if parse_cp and parse_cp.get("status") == "completed":
        pages = parse_cp["data"].get("pages", [])
        logger.info(f"[INGESTION][CHECKPOINT] Step 1 resumed: {len(pages)} pages")
    else:
        try:
            pages = parse_pdf(pdf_path)
        except Exception as exc:
            if upload_id:
                await mark_step_failed(upload_id, "parsing", str(exc))
            raise

        if upload_id:
            await create_checkpoint(
                upload_id, "parsing",
                {"pages": pages, "total_pages": len(pages)},
                status="completed",
            )
        logger.info(f"[INGESTION] Step 1 complete: {len(pages)} pages parsed")

    # ------------------------------------------------------------------
    # Step 2: Clean text
    # ------------------------------------------------------------------
    clean_cp = await get_checkpoint(upload_id, "cleaning") if upload_id else None

    if clean_cp and clean_cp.get("status") == "completed":
        cleaned_pages = clean_cp["data"].get("pages", [])
        logger.info(f"[INGESTION][CHECKPOINT] Step 2 resumed: {len(cleaned_pages)} pages")
    else:
        try:
            cleaned_pages = clean_pages(pages)
        except Exception as exc:
            if upload_id:
                await mark_step_failed(upload_id, "cleaning", str(exc))
            raise

        if upload_id:
            await create_checkpoint(
                upload_id, "cleaning",
                {"pages": cleaned_pages},
                status="completed",
            )
        logger.info("[INGESTION] Step 2 complete: text cleaned")

    # ------------------------------------------------------------------
    # Step 3: Chunk
    # ------------------------------------------------------------------
    chunk_cp = await get_checkpoint(upload_id, "chunking") if upload_id else None

    if chunk_cp and chunk_cp.get("status") == "completed":
        chunks = chunk_cp["data"].get("chunks", [])
        logger.info(f"[INGESTION][CHECKPOINT] Step 3 resumed: {len(chunks)} chunks")
    else:
        try:
            chunks = chunk_paper(
                pages=cleaned_pages,
                source_document=source_document,
                paper_title=paper_title,
                authors=authors,
                source="upload",
                publication_year=publication_year,
                arxiv_id=arxiv_id,
                doi=doi,
                subject_areas=subject_areas,
                upload_id=upload_id,
            )
        except Exception as exc:
            if upload_id:
                await mark_step_failed(upload_id, "chunking", str(exc))
            raise

        if upload_id:
            await create_checkpoint(
                upload_id, "chunking",
                {"chunks": chunks, "total_chunks": len(chunks)},
                status="completed",
            )
        logger.info(f"[INGESTION] Step 3 complete: {len(chunks)} chunks created")

    # ------------------------------------------------------------------
    # Step 4: Embed + index into ChromaDB
    # ------------------------------------------------------------------
    index_cp = await get_checkpoint(upload_id, "indexing") if upload_id else None

    if index_cp and index_cp.get("status") == "completed":
        indexing_result = index_cp["data"].get("result", {})
        logger.info(
            f"[INGESTION][CHECKPOINT] Step 4 resumed: "
            f"{indexing_result.get('chunks_indexed', 0)} chunks"
        )
    else:
        try:
            indexing_result = index_chunks(chunks, upload_id=upload_id)
        except Exception as exc:
            if upload_id:
                await mark_step_failed(upload_id, "indexing", str(exc))
            raise

        if upload_id:
            await create_checkpoint(
                upload_id, "indexing",
                {"result": indexing_result},
                status="completed",
            )
        logger.info(
            f"[INGESTION] Step 4 complete: "
            f"{indexing_result.get('chunks_indexed', 0)} chunks indexed"
        )

    logger.info(f"[INGESTION] Pipeline complete for '{source_document}'")

    return {
        "status": "success",
        "pages_processed": len(pages),
        "chunks_created": len(chunks),
        "indexing_result": indexing_result,
    }
