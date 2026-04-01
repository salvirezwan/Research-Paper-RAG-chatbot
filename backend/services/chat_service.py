from typing import AsyncIterator, Dict, Any

from backend.rag.langgraph.graph import run_langgraph_pipeline, stream_langgraph_pipeline


def process_chat(query: str) -> Dict[str, Any]:
    """Run the RAG pipeline synchronously and return the final answer."""
    try:
        final_answer = run_langgraph_pipeline(query)
        return {
            "query": query,
            "answer": final_answer,
            "status": "success",
        }
    except Exception as e:
        return {
            "query": query,
            "answer": f"Error processing query: {str(e)}",
            "status": "error",
        }


async def stream_chat(query: str) -> AsyncIterator[Dict[str, Any]]:
    """Stream RAG pipeline events for SSE delivery."""
    try:
        async for event in stream_langgraph_pipeline(query):
            yield event
    except Exception as e:
        yield {
            "type": "error",
            "data": f"Error processing query: {str(e)}",
        }
