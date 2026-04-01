"""Tests for POST /api/v1/chat (SSE streaming)."""
import json
from unittest.mock import patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_sse_generator(*events):
    """Return an async generator that yields the given event dicts as SSE dicts."""
    async def _gen(query):  # noqa: ARG001
        for event in events:
            yield event
    return _gen


def _parse_sse(text: str) -> list:
    """Parse raw SSE body into a list of decoded event dicts."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestChatEndpoint:
    def test_empty_query_returns_400(self, client):
        resp = client.post("/api/v1/chat", json={"query": ""})
        assert resp.status_code == 400

    def test_whitespace_only_query_returns_400(self, client):
        resp = client.post("/api/v1/chat", json={"query": "   "})
        assert resp.status_code == 400

    def test_missing_query_field_returns_422(self, client):
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422

    def test_valid_query_returns_200(self, client):
        gen = _make_sse_generator(
            {"type": "status", "data": "Routing query…"},
            {"type": "final", "data": "The answer is 42.", "citations": []},
        )
        with patch("backend.routes.chat.stream_chat", new=gen):
            resp = client.post("/api/v1/chat", json={"query": "What is the answer?"})
        assert resp.status_code == 200

    def test_response_content_type_is_event_stream(self, client):
        gen = _make_sse_generator(
            {"type": "final", "data": "Answer here.", "citations": []},
        )
        with patch("backend.routes.chat.stream_chat", new=gen):
            resp = client.post("/api/v1/chat", json={"query": "Tell me something"})
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_stream_contains_final_event(self, client):
        gen = _make_sse_generator(
            {"type": "status", "data": "Searching…"},
            {"type": "final", "data": "Here is my answer.", "citations": ["[1] Paper A"]},
        )
        with patch("backend.routes.chat.stream_chat", new=gen):
            resp = client.post("/api/v1/chat", json={"query": "Explain transformers"})

        events = _parse_sse(resp.text)
        final_events = [e for e in events if e.get("type") == "final"]
        assert len(final_events) == 1
        assert final_events[0]["data"] == "Here is my answer."

    def test_sse_final_event_includes_citations(self, client):
        citations = ["[1] Vaswani et al. (2017) - Attention Is All You Need"]
        gen = _make_sse_generator(
            {"type": "final", "data": "Answer.", "citations": citations},
        )
        with patch("backend.routes.chat.stream_chat", new=gen):
            resp = client.post("/api/v1/chat", json={"query": "Who wrote attention paper?"})

        events = _parse_sse(resp.text)
        final = next(e for e in events if e.get("type") == "final")
        assert final["citations"] == citations

    def test_sse_status_events_appear_before_final(self, client):
        gen = _make_sse_generator(
            {"type": "status", "data": "Routing…"},
            {"type": "status", "data": "Retrieving…"},
            {"type": "final", "data": "Done.", "citations": []},
        )
        with patch("backend.routes.chat.stream_chat", new=gen):
            resp = client.post("/api/v1/chat", json={"query": "Question here"})

        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert types.index("final") > types.index("status")

    def test_error_from_stream_forwarded_to_client(self, client):
        async def _error_gen(query):  # noqa: ARG001
            yield {"type": "error", "data": "LLM unavailable"}

        with patch("backend.routes.chat.stream_chat", new=_error_gen):
            resp = client.post("/api/v1/chat", json={"query": "Will this fail?"})

        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "LLM unavailable" in error_events[0]["data"]

    def test_query_is_stripped_before_processing(self, client):
        """Trailing/leading whitespace is stripped before the query is passed on."""
        received_queries = []

        async def _capture_gen(query):
            received_queries.append(query)
            yield {"type": "final", "data": "ok", "citations": []}

        with patch("backend.routes.chat.stream_chat", new=_capture_gen):
            client.post("/api/v1/chat", json={"query": "  hello world  "})

        assert received_queries == ["hello world"]
