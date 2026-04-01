"""
End-to-end smoke tests for the full upload → ingest → chat pipeline.

All external services (MongoDB, ChromaDB, Groq) are mocked.
These tests verify the full request/response flow through the FastAPI app
and the integration between route → service → RAG pipeline layers.
"""
import io
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _paper(pid="aabbccddeeff001122334455", status="indexed", chunk_count=5):
    p = MagicMock()
    p.id = pid
    p.filename = "smoke_test.pdf"
    p.status = MagicMock(value=status)
    p.source = MagicMock(value="upload")
    p.title = "Smoke Test Paper"
    p.authors = ["Tester"]
    p.abstract = "A paper used for smoke testing."
    p.publication_year = "2024"
    p.arxiv_id = None
    p.doi = None
    p.subject_areas = []
    p.chunk_count = chunk_count
    p.uploaded_at = datetime.now(timezone.utc)
    p.processed_at = datetime.now(timezone.utc)
    p.stored_path = "/uploads/upload/smoke_test.pdf"
    p.file_hash = "deadbeef" * 8
    p.error_message = None
    return p


# ── Smoke Test: Upload → Status ────────────────────────────────────────────────

class TestUploadToStatusSmoke:
    def test_upload_then_check_status(self, client, minimal_pdf_bytes):
        """
        Smoke test: upload a PDF → verify 200 + paper_id → poll status endpoint.
        """
        paper = _paper(status="uploaded", chunk_count=0)

        # 1. Upload
        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)),
            patch("backend.routes.upload.save_uploaded_file", return_value=paper.stored_path),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            upload_resp = client.post(
                "/api/v1/upload",
                files={"file": ("smoke_test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
            )

        assert upload_resp.status_code == 200, upload_resp.text
        paper_id = upload_resp.json()["paper_id"]
        assert paper_id

        # 2. Check status
        indexed_paper = _paper(pid=paper_id, status="indexed", chunk_count=5)
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=indexed_paper)):
            status_resp = client.get(f"/api/v1/upload/{paper_id}")

        assert status_resp.status_code == 200
        assert status_resp.json()["status"].value == "indexed"

    def test_upload_then_list_papers(self, client, minimal_pdf_bytes):
        """Upload a paper and verify it appears in the papers list."""
        paper = _paper(status="indexed", chunk_count=7)

        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)),
            patch("backend.routes.upload.save_uploaded_file", return_value=paper.stored_path),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            client.post(
                "/api/v1/upload",
                files={"file": ("smoke_test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
            )

        with (
            patch("backend.routes.papers.list_papers", new=AsyncMock(return_value=[paper])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=1)),
        ):
            list_resp = client.get("/api/v1/papers")

        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1
        assert list_resp.json()["papers"][0]["title"] == "Smoke Test Paper"


# ── Smoke Test: Chat Pipeline ──────────────────────────────────────────────────

class TestChatSmoke:
    def test_chat_produces_final_answer(self, client):
        """Full chat flow: query → SSE stream → final answer with citations."""
        async def _rag_stream(query):
            yield {"type": "status", "data": "Routing query…"}
            yield {"type": "status", "data": "Retrieving relevant chunks…"}
            yield {"type": "status", "data": "Generating answer…"}
            yield {
                "type": "final",
                "data": (
                    "Transformer models use self-attention mechanisms.\n\n"
                    "**Sources:**\n[1] Vaswani et al. (2017) - Attention Is All You Need"
                ),
                "citations": ["[1] Vaswani et al. (2017) - Attention Is All You Need"],
            }

        with patch("backend.routes.chat.stream_chat", new=_rag_stream):
            resp = client.post(
                "/api/v1/chat",
                json={"query": "How do transformer models work?"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        # Parse SSE events
        events = []
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        status_events = [e for e in events if e["type"] == "status"]
        final_events = [e for e in events if e["type"] == "final"]

        assert len(status_events) >= 1
        assert len(final_events) == 1
        assert "self-attention" in final_events[0]["data"]
        assert len(final_events[0]["citations"]) == 1

    def test_chat_with_no_indexed_papers_still_responds(self, client):
        """Even with no papers, the chat endpoint should return a response (live_fetch path)."""
        async def _live_fetch_stream(query):
            yield {"type": "status", "data": "No local papers — fetching from arXiv…"}
            yield {
                "type": "final",
                "data": "Based on arXiv papers: ...",
                "citations": [],
            }

        with patch("backend.routes.chat.stream_chat", new=_live_fetch_stream):
            resp = client.post(
                "/api/v1/chat",
                json={"query": "What is quantum computing?"},
            )

        assert resp.status_code == 200
        events = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        assert any(e["type"] == "final" for e in events)


# ── Smoke Test: Upload → Delete lifecycle ─────────────────────────────────────

class TestUploadDeleteLifecycle:
    def test_upload_then_delete(self, client, minimal_pdf_bytes):
        """Upload a paper then delete it — both steps should succeed."""
        paper = _paper()

        # Upload
        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)),
            patch("backend.routes.upload.save_uploaded_file", return_value=paper.stored_path),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            upload = client.post(
                "/api/v1/upload",
                files={"file": ("smoke_test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
            )
        assert upload.status_code == 200
        pid = upload.json()["paper_id"]

        # Delete via papers API
        with (
            patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.papers.chroma_client"),
            patch("backend.routes.papers.delete_uploaded_file"),
            patch("backend.routes.papers.delete_paper", new=AsyncMock(return_value=True)),
        ):
            delete = client.delete(f"/api/v1/papers/{pid}")

        assert delete.status_code == 200
        assert delete.json()["paper_id"] == pid

        # Verify gone — subsequent lookup returns 404
        with patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=None)):
            gone = client.get(f"/api/v1/papers/{pid}")
        assert gone.status_code == 404


# ── Smoke Test: arXiv fetch ────────────────────────────────────────────────────

class TestArxivFetchSmoke:
    def test_fetch_arxiv_paper_appears_in_library(self, client):
        """Fetch an arXiv paper → verify it is returned from the papers list."""
        fetch_result = {
            "paper_id": "arxiv000000000000000001",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "arxiv_id": "1810.04805",
        }
        arxiv_paper = _paper(pid="arxiv000000000000000001")
        arxiv_paper.title = fetch_result["title"]
        arxiv_paper.arxiv_id = "1810.04805"

        with patch(
            "backend.routes.papers.fetch_paper_by_arxiv_id",
            new=AsyncMock(return_value=fetch_result),
        ):
            fetch_resp = client.post("/api/v1/papers/fetch/arxiv/1810.04805")

        assert fetch_resp.status_code == 200
        assert "message" in fetch_resp.json()

        # Paper should now appear in list
        with (
            patch("backend.routes.papers.list_papers",
                  new=AsyncMock(return_value=[arxiv_paper])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=1)),
        ):
            list_resp = client.get("/api/v1/papers")

        assert list_resp.json()["total"] == 1
        assert "BERT" in list_resp.json()["papers"][0]["title"]
