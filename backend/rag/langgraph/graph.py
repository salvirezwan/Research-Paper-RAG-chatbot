"""
LangGraph assembly — wire all nodes into a compiled StateGraph
and expose synchronous + async-streaming entry points.
"""

from typing import AsyncIterator, Dict, Any, List

from langgraph.graph import StateGraph, END

from backend.rag.langgraph.state import GraphState
from backend.rag.langgraph.nodes.router import router_node
from backend.rag.langgraph.nodes.retrieve import retrieve_node
from backend.rag.langgraph.nodes.grade_docs import grade_docs_node
from backend.rag.langgraph.nodes.live_fetch import live_fetch_node
from backend.rag.langgraph.nodes.generator import generator_node
from backend.rag.langgraph.nodes.citation import citation_node
from backend.core.logging import logger


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_rag_graph():
    """Build and compile the research RAG LangGraph."""
    workflow = StateGraph(GraphState)

    # Register nodes
    workflow.add_node("router", router_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("live_fetch", live_fetch_node)
    workflow.add_node("grade_docs", grade_docs_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("citation", citation_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional routing: router decides retrieve vs live_fetch
    workflow.add_conditional_edges(
        "router",
        _route_decision,
        {
            "retrieve": "retrieve",
            "live_fetch": "live_fetch",
        },
    )

    # After retrieval → grade documents → generate → attach citations → END
    workflow.add_edge("retrieve", "grade_docs")
    workflow.add_edge("live_fetch", "grade_docs")
    workflow.add_edge("grade_docs", "generator")
    workflow.add_edge("generator", "citation")
    workflow.add_edge("citation", END)

    return workflow.compile()


def _route_decision(state: GraphState) -> str:
    """Return the routing key from state (set by router_node)."""
    route = state.get("route", "retrieve")
    if route not in ("retrieve", "live_fetch"):
        return "retrieve"
    return route


# ---------------------------------------------------------------------------
# Singleton graph instance
# ---------------------------------------------------------------------------

_rag_graph = None


def get_rag_graph():
    """Lazy-initialise and return the compiled RAG graph."""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
        logger.info("[GRAPH] RAG pipeline graph compiled")
    return _rag_graph


# ---------------------------------------------------------------------------
# Synchronous execution
# ---------------------------------------------------------------------------

def run_langgraph_pipeline(query: str, session_id: str = None, chat_history: List[Dict[str, str]] = None) -> str:
    """Run the full RAG pipeline synchronously and return the final answer."""
    graph = get_rag_graph()
    initial_state: GraphState = {"user_query": query, "session_id": session_id, "chat_history": chat_history or []}

    final_state = graph.invoke(initial_state)

    return final_state.get("final_answer", "No answer generated.")


# ---------------------------------------------------------------------------
# Async SSE streaming execution
# ---------------------------------------------------------------------------

async def stream_langgraph_pipeline(
    query: str,
    session_id: str = None,
    chat_history: List[Dict[str, str]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream the RAG pipeline asynchronously, yielding SSE-style events
    for each node transition and the final answer.
    """
    graph = get_rag_graph()
    initial_state: GraphState = {"user_query": query, "session_id": session_id, "chat_history": chat_history or []}

    async for event in graph.astream(initial_state):
        for node_name, node_state in event.items():
            if node_name == "router":
                route = node_state.get("route", "unknown")
                yield {
                    "type": "status",
                    "data": f"Routing query… (→ {route})",
                }

            elif node_name == "retrieve":
                count = len(node_state.get("retrieved_chunks", []))
                yield {
                    "type": "status",
                    "data": f"Retrieved {count} document chunks from local store",
                }

            elif node_name == "live_fetch":
                papers = len(node_state.get("live_papers", []))
                chunks = len(node_state.get("live_chunks", []))
                yield {
                    "type": "status",
                    "data": (
                        f"Fetched {papers} papers from external sources "
                        f"({chunks} chunks)"
                    ),
                }

            elif node_name == "grade_docs":
                count = len(node_state.get("retrieved_chunks", []))
                yield {
                    "type": "status",
                    "data": f"Evaluated relevance — {count} chunks retained",
                }

            elif node_name == "generator":
                yield {"type": "status", "data": "Generating answer…"}

            elif node_name == "citation":
                final_answer = node_state.get("final_answer")
                citations = node_state.get("citations", [])
                if final_answer:
                    yield {
                        "type": "final",
                        "data": final_answer,
                        "citations": citations,
                    }
