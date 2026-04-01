from typing import List, Dict, Any

from backend.rag.embedding.embedder import embed_text
from backend.rag.vectorstore.chroma_client import chroma_client
from backend.core.config import settings
from backend.core.logging import logger


def index_chunks(chunks: List[Dict[str, Any]], upload_id: str = None) -> Dict[str, Any]:
    """
    Embed each chunk and insert into ChromaDB.

    Args:
        chunks:    List of chunk dicts produced by chunker.chunk_paper().
        upload_id: MongoDB document ID of the uploaded paper (optional override).

    Returns:
        Dict with status, chunks_indexed, and errors count.
    """
    if not chunks:
        return {"status": "success", "chunks_indexed": 0, "errors": 0}

    vectors = []
    metadata_list = []
    errors = 0

    for chunk_idx, chunk in enumerate(chunks):
        try:
            content = chunk.get("content", "")
            if not content or not str(content).strip():
                logger.debug(f"Skipping empty chunk at index {chunk_idx}")
                continue

            vector = embed_text(str(content))

            if not vector or len(vector) != settings.EMBED_DIMENSIONS:
                logger.error(
                    f"Invalid embedding dimensions for chunk {chunk_idx}: "
                    f"expected {settings.EMBED_DIMENSIONS}, got {len(vector) if vector else 0}"
                )
                errors += 1
                continue

            chroma_metadata: Dict[str, Any] = {
                "source_document": str(chunk.get("source_document", "")),
                "source": str(chunk.get("source", "upload")),
                "chunk_index": int(chunk.get("chunk_index", chunk_idx)),
                "content": str(content),
            }

            for str_field in [
                "paper_title", "authors", "publication_year",
                "arxiv_id", "doi", "subject_areas",
                "section_id", "paragraph_ref",
            ]:
                val = chunk.get(str_field)
                if val is not None:
                    chroma_metadata[str_field] = str(val)

            page_number = chunk.get("page_number")
            if page_number is not None:
                chroma_metadata["page_number"] = int(page_number)

            effective_upload_id = upload_id or chunk.get("upload_id")
            if effective_upload_id:
                chroma_metadata["upload_id"] = str(effective_upload_id)

            vectors.append(vector)
            metadata_list.append(chroma_metadata)

        except Exception as e:
            logger.error(
                f"Error processing chunk {chunk_idx} for indexing: {e}. "
                f"source_document='{chunk.get('source_document', 'unknown')}', "
                f"chunk_index={chunk.get('chunk_index', chunk_idx)}",
                exc_info=True,
            )
            errors += 1
            continue

    if not vectors:
        return {
            "status": "error",
            "chunks_indexed": 0,
            "errors": errors,
            "message": "No valid chunks to index",
        }

    try:
        logger.info(f"Indexing {len(vectors)} chunks to ChromaDB...")
        result = chroma_client.insert_batch(vectors=vectors, metadata_list=metadata_list)

        chunks_indexed = result.get("points_count", len(vectors))
        logger.info(f"Successfully indexed {chunks_indexed} chunks to ChromaDB")

        return {
            "status": "success",
            "chunks_indexed": chunks_indexed,
            "errors": errors,
        }

    except Exception as e:
        logger.error(
            f"Error indexing chunks to ChromaDB: {e}. "
            f"Attempted {len(vectors)} vectors.",
            exc_info=True,
        )
        return {
            "status": "error",
            "chunks_indexed": 0,
            "errors": errors + len(vectors),
            "message": str(e),
        }
