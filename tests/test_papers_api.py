"""Tests for the papers API routes."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_paper(paper_id: str = "64a1b2c3d4e5f6a7b8c9d0e1", arxiv_id: str = None):
    p = MagicMock()
    p.id = paper_id
    p.filename = "paper.pdf"
    p.title = "Attention Is All You Need"
    p.authors = ["Vaswani", "Shazeer"]
    p.abstract = "We propose the Transformer..."
    p.source = MagicMock(value="upload")
    p.status = MagicMock(value="indexed")
    p.publication_year = "2017"
    p.arxiv_id = arxiv_id
    p.doi = None
    p.subject_areas = ["ML", "NLP"]
    p.chunk_count = 42
    p.uploaded_at = datetime.now(timezone.utc)
    p.processed_at = datetime.now(timezone.utc)
    p.stored_path = "/uploads/paper.pdf"
    return p


# ── GET /api/v1/papers ─────────────────────────────────────────────────────────

class TestListPapers:
    def test_returns_200(self, client):
        with (
            patch("backend.routes.papers.list_papers", new=AsyncMock(return_value=[])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=0)),
        ):
            resp = client.get("/api/v1/papers")
        assert resp.status_code == 200

    def test_response_has_papers_and_total(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.papers.list_papers", new=AsyncMock(return_value=[paper])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=1)),
        ):
            resp = client.get("/api/v1/papers")
        body = resp.json()
        assert "papers" in body
        assert "total" in body
        assert body["total"] == 1

    def test_paper_fields_in_response(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.papers.list_papers", new=AsyncMock(return_value=[paper])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=1)),
        ):
            resp = client.get("/api/v1/papers")
        p = resp.json()["papers"][0]
        assert p["title"] == "Attention Is All You Need"
        assert "paper_id" in p
        assert "status" in p

    def test_pagination_params_accepted(self, client):
        with (
            patch("backend.routes.papers.list_papers", new=AsyncMock(return_value=[])),
            patch("backend.routes.papers.count_papers", new=AsyncMock(return_value=0)),
        ):
            resp = client.get("/api/v1/papers?limit=10&offset=20")
        assert resp.status_code == 200

    def test_limit_out_of_range_rejected(self, client):
        resp = client.get("/api/v1/papers?limit=0")
        assert resp.status_code == 422


# ── GET /api/v1/papers/{paper_id} ─────────────────────────────────────────────

class TestGetPaper:
    def test_returns_200_for_existing(self, client):
        paper = _make_paper()
        with patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=paper)):
            resp = client.get("/api/v1/papers/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.status_code == 200

    def test_returns_404_for_missing(self, client):
        with patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=None)):
            resp = client.get("/api/v1/papers/000000000000000000000000")
        assert resp.status_code == 404

    def test_response_includes_title(self, client):
        paper = _make_paper()
        with patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=paper)):
            resp = client.get("/api/v1/papers/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.json()["title"] == "Attention Is All You Need"


# ── DELETE /api/v1/papers/{paper_id} ──────────────────────────────────────────

class TestDeletePaper:
    def test_delete_returns_200(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.papers.chroma_client"),
            patch("backend.routes.papers.delete_uploaded_file"),
            patch("backend.routes.papers.delete_paper", new=AsyncMock(return_value=True)),
        ):
            resp = client.delete("/api/v1/papers/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.status_code == 200

    def test_delete_returns_paper_id(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.papers.chroma_client"),
            patch("backend.routes.papers.delete_uploaded_file"),
            patch("backend.routes.papers.delete_paper", new=AsyncMock(return_value=True)),
        ):
            resp = client.delete("/api/v1/papers/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.json()["paper_id"] == "64a1b2c3d4e5f6a7b8c9d0e1"

    def test_delete_missing_paper_returns_404(self, client):
        with patch("backend.routes.papers.get_paper_by_id", new=AsyncMock(return_value=None)):
            resp = client.delete("/api/v1/papers/000000000000000000000000")
        assert resp.status_code == 404


# ── POST /api/v1/papers/fetch/arxiv/{arxiv_id} ────────────────────────────────

class TestFetchArxivPaper:
    def test_fetch_success_returns_200(self, client):
        result = {
            "paper_id": "64a1b2c3d4e5f6a7b8c9d0e1",
            "title": "Attention Is All You Need",
            "arxiv_id": "1706.03762",
        }
        with patch(
            "backend.routes.papers.fetch_paper_by_arxiv_id",
            new=AsyncMock(return_value=result),
        ):
            resp = client.post("/api/v1/papers/fetch/arxiv/1706.03762")
        assert resp.status_code == 200

    def test_fetch_success_includes_title(self, client):
        result = {
            "paper_id": "64a1b2c3d4e5f6a7b8c9d0e1",
            "title": "Attention Is All You Need",
            "arxiv_id": "1706.03762",
        }
        with patch(
            "backend.routes.papers.fetch_paper_by_arxiv_id",
            new=AsyncMock(return_value=result),
        ):
            resp = client.post("/api/v1/papers/fetch/arxiv/1706.03762")
        assert "message" in resp.json()

    def test_fetch_failure_returns_502(self, client):
        with patch(
            "backend.routes.papers.fetch_paper_by_arxiv_id",
            new=AsyncMock(return_value=None),
        ):
            resp = client.post("/api/v1/papers/fetch/arxiv/9999.99999")
        assert resp.status_code == 502
