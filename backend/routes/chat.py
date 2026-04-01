import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.schemas.chat_schema import ChatRequest
from backend.services.chat_service import stream_chat

router = APIRouter(prefix="/api/v1", tags=["Chat"])


async def _sse_generator(query: str) -> AsyncIterator[str]:
    try:
        async for event in stream_chat(query):
            event_type = event.get("type", "status")
            data = event.get("data", "")

            if event_type == "final":
                payload = {
                    "type": "final",
                    "data": data,
                    "citations": event.get("citations", []),
                }
            elif event_type == "error":
                payload = {"type": "error", "data": data}
            else:
                payload = {"type": "status", "data": data}

            yield json.dumps(payload)

    except Exception as exc:
        yield json.dumps({"type": "error", "data": f"Streaming error: {str(exc)}"})


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    return EventSourceResponse(_sse_generator(request.query.strip()))
