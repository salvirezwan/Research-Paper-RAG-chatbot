from typing import TypedDict, Optional, List, Dict, Any


class GraphState(TypedDict, total=False):
    """State passed between all LangGraph nodes in the research RAG pipeline."""

    # Input
    user_query: str
    session_id: Optional[str]

    # Routing decision
    route: str  # "retrieve" | "live_fetch"

    # Retrieval
    retrieved_chunks: List[Dict[str, Any]]  # each: {text, metadata, score}

    # Live fetch from arXiv / Semantic Scholar
    live_papers: List[Dict[str, Any]]       # paper metadata dicts from external APIs
    live_chunks: List[Dict[str, Any]]       # chunks extracted from live papers

    # Generation
    citations: List[str]                    # formatted citation strings
    final_answer: Optional[str]
