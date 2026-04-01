from langchain_core.messages import HumanMessage, SystemMessage

from backend.rag.langgraph.state import GraphState
from backend.rag.llm_client import get_chat_model
from backend.core.logging import logger

_LIVE_FETCH_KEYWORDS = [
    "latest", "recent", "new paper", "new papers", "find papers",
    "search papers", "arxiv", "fetch", "download", "retrieve paper",
    "papers on", "research on", "find research",
]

_SYSTEM_PROMPT = """You are a routing assistant for an academic research RAG system.

Classify the user's query into one of two categories:
1. "retrieve" - The user wants to query papers already in the local database
2. "live_fetch" - The user wants to find/fetch new papers from arXiv or the internet by topic/keyword

Respond with ONLY one word: either "retrieve" or "live_fetch"."""


def router_node(state: GraphState) -> GraphState:
    query = state.get("user_query", "")

    if not query:
        return {**state, "route": "retrieve"}

    try:
        llm = get_chat_model(temperature=0.0)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"User query: {query}"),
        ]
        response = llm.invoke(messages)
        route = response.content.strip().lower()

        if route not in ("retrieve", "live_fetch"):
            route = "retrieve"

    except Exception as e:
        logger.warning(f"Router LLM failed ({e}), falling back to keyword heuristic")
        query_lower = query.lower()
        route = (
            "live_fetch"
            if any(kw in query_lower for kw in _LIVE_FETCH_KEYWORDS)
            else "retrieve"
        )

    logger.info(f"[ROUTER] query='{query[:80]}' → route='{route}'")
    return {**state, "route": route}
