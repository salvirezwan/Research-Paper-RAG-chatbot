from typing import List, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.rag.langgraph.state import GraphState
from backend.rag.llm_client import get_chat_model
from backend.core.logging import logger

_SYSTEM_PROMPT = """You are a document relevance grader for an academic research RAG system.

Evaluate whether the provided document chunk is relevant to answering the user's query.
Respond with ONLY one word: "relevant" or "irrelevant"."""


def grade_docs_node(state: GraphState) -> GraphState:
    query = state.get("user_query", "")
    retrieved_chunks = state.get("retrieved_chunks", [])

    if not retrieved_chunks:
        return state

    try:
        llm = get_chat_model(temperature=0.0)
        graded = _grade_with_llm(llm, query, retrieved_chunks)
    except Exception as e:
        logger.warning(f"Grade-docs LLM failed ({e}), keeping all chunks")
        graded = retrieved_chunks

    # Fallback: never return empty — keep top-2 originals
    if not graded and retrieved_chunks:
        graded = retrieved_chunks[:2]

    logger.info(
        f"[GRADE_DOCS] {len(retrieved_chunks)} retrieved → {len(graded)} relevant"
    )
    return {**state, "retrieved_chunks": graded}


def _grade_with_llm(llm, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    graded: List[Dict[str, Any]] = []
    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        if not chunk_text:
            continue

        evaluation_prompt = (
            f"User Query: {query}\n\n"
            f"Document Chunk:\n{chunk_text[:600]}\n\n"
            "Is this chunk relevant to answering the query?"
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=evaluation_prompt),
        ]

        try:
            response = llm.invoke(messages)
            grade = response.content.strip().lower()
            if "relevant" in grade:
                graded.append(chunk)
        except Exception as e:
            logger.warning(f"Grading individual chunk failed ({e}), keeping it")
            graded.append(chunk)

    return graded
