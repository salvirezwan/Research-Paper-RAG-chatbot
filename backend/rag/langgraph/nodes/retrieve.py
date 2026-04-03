from typing import List, Dict, Any

from backend.rag.langgraph.state import GraphState
from backend.rag.embedding.embedder import embed_text
from backend.rag.vectorstore.chroma_client import chroma_client
from backend.crud.uploaded_doc import list_paper_ids_by_session
from backend.core.logging import logger

_RETRIEVAL_TOP_K = 5


async def retrieve_node(state: GraphState) -> GraphState:
    query = state.get("user_query", "")

    if not query:
        return {**state, "retrieved_chunks": []}

    session_id = state.get("session_id")
    upload_ids = None
    if session_id:
        try:
            upload_ids = await list_paper_ids_by_session(session_id) or None
        except Exception as e:
            logger.warning(f"[RETRIEVE] Could not fetch session paper IDs: {e}")

    query_vector = embed_text(query)
    results = chroma_client.search(query_vector, top_k=_RETRIEVAL_TOP_K, upload_ids=upload_ids)

    retrieved_chunks: List[Dict[str, Any]] = []

    for result in results:
        chunk_text = result.get("text", "")
        source_doc = str(result.get("source_document", "")).strip()

        retrieved_chunks.append({
            "text": chunk_text or f"[Retrieved from {result.get('section_id', 'unknown')}]",
            "score": result.get("score", 0.0),
            "metadata": {
                "source_document": source_doc,
                "paper_title": result.get("paper_title"),
                "authors": result.get("authors"),
                "source": result.get("source", "upload"),
                "publication_year": result.get("publication_year"),
                "arxiv_id": result.get("arxiv_id"),
                "doi": result.get("doi"),
                "section_id": result.get("section_id"),
                "page_number": result.get("page_number"),
                "chunk_index": result.get("chunk_index", 0),
                "upload_id": result.get("upload_id"),
            },
        })

    logger.info(f"[RETRIEVE] query='{query[:60]}' → {len(retrieved_chunks)} chunks")
    return {**state, "retrieved_chunks": retrieved_chunks}
