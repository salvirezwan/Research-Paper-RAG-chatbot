"""Tests for the upload API routes."""
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_paper(
    paper_id: str = "64a1b2c3d4e5f6a7b8c9d0e1",
    filename: str = "test.pdf",
    status: str = "indexed",
    chunk_count: int = 10,
):
    """Return a MagicMock that looks like a ResearchPaper ODM object."""
    paper = MagicMock()
    paper.id = paper_id
    paper.filename = filename
    paper.status = MagicMock()
    paper.status.value = status
    paper.source = MagicMock()
    paper.source.value = "upload"
    paper.title = "Test Paper Title"
    paper.authors = ["Alice", "Bob"]
    paper.abstract = None
    paper.publication_year = "2024"
    paper.arxiv_id = None
    paper.doi = None
    paper.subject_areas = []
    paper.chunk_count = chunk_count
    paper.uploaded_at = datetime.now(timezone.utc)
    paper.processed_at = datetime.now(timezone.utc)
    paper.stored_path = f"/uploads/upload/{filename}"
    paper.file_hash = "abc123"
    paper.error_message = None
    return paper


# ── POST /api/v1/upload ────────────────────────────────────────────────────────

class TestUploadEndpoint:
    def test_valid_pdf_upload_returns_200(self, client, minimal_pdf_bytes):
        paper = _make_paper(status="uploaded", chunk_count=0)
        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)),
            patch("backend.routes.upload.save_uploaded_file", return_value="/uploads/test.pdf"),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/upload",
                files={"file": ("test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
            )
        assert resp.status_code == 200

    def test_upload_returns_paper_id(self, client, minimal_pdf_bytes):
        paper = _make_paper(status="uploaded", chunk_count=0)
        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)),
            patch("backend.routes.upload.save_uploaded_file", return_value="/uploads/test.pdf"),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/upload",
                files={"file": ("test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
            )
        body = resp.json()
        assert "paper_id" in body
        assert body["paper_id"] == str(paper.id)

    def test_non_pdf_file_rejected(self, client):
        resp = client.post(
            "/api/v1/upload",
            files={"file": ("notes.txt", io.BytesIO(b"plain text"), "text/plain")},
        )
        assert resp.status_code == 415

    def test_duplicate_upload_rejected_without_force(self, client, minimal_pdf_bytes):
        existing = _make_paper()
        with patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=existing)):
            resp = client.post(
                "/api/v1/upload",
                files={"file": ("test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
                data={"force_reupload": "false"},
            )
        assert resp.status_code == 409

    def test_force_reupload_replaces_existing(self, client, minimal_pdf_bytes):
        existing = _make_paper()
        new_paper = _make_paper(paper_id="new000000000000000000001", status="uploaded")
        with (
            patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=existing)),
            patch("backend.routes.upload.chroma_client") as mock_chroma,
            patch("backend.routes.upload.delete_uploaded_file"),
            patch("backend.routes.upload.delete_paper", new=AsyncMock(return_value=True)),
            patch("backend.routes.upload.save_uploaded_file", return_value="/uploads/test.pdf"),
            patch("backend.routes.upload.create_paper_record", new=AsyncMock(return_value=new_paper)),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/upload",
                files={"file": ("test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
                data={"force_reupload": "true"},
            )
        assert resp.status_code == 200

    def test_invalid_metadata_json_returns_422(self, client, minimal_pdf_bytes):
        with patch("backend.routes.upload.get_paper_by_hash", new=AsyncMock(return_value=None)):
            resp = client.post(
                "/api/v1/upload",
                files={"file": ("test.pdf", io.BytesIO(minimal_pdf_bytes), "application/pdf")},
                data={"metadata": "{not valid json}"},
            )
        assert resp.status_code == 422


# ── GET /api/v1/upload/{paper_id} ─────────────────────────────────────────────

class TestGetUploadStatus:
    def test_returns_200_for_existing_paper(self, client):
        paper = _make_paper()
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=paper)):
            resp = client.get("/api/v1/upload/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.status_code == 200

    def test_response_has_status_field(self, client):
        paper = _make_paper(status="indexed")
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=paper)):
            resp = client.get("/api/v1/upload/64a1b2c3d4e5f6a7b8c9d0e1")
        assert "status" in resp.json()

    def test_returns_404_for_missing_paper(self, client):
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=None)):
            resp = client.get("/api/v1/upload/000000000000000000000000")
        assert resp.status_code == 404


# ── DELETE /api/v1/upload/{paper_id} ──────────────────────────────────────────

class TestDeleteUpload:
    def test_delete_returns_200(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.chroma_client"),
            patch("backend.routes.upload.delete_uploaded_file"),
            patch("backend.routes.upload.delete_paper", new=AsyncMock(return_value=True)),
        ):
            resp = client.delete("/api/v1/upload/64a1b2c3d4e5f6a7b8c9d0e1")
        assert resp.status_code == 200

    def test_delete_nonexistent_returns_404(self, client):
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=None)):
            resp = client.delete("/api/v1/upload/000000000000000000000000")
        assert resp.status_code == 404

    def test_delete_response_includes_paper_id(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.chroma_client"),
            patch("backend.routes.upload.delete_uploaded_file"),
            patch("backend.routes.upload.delete_paper", new=AsyncMock(return_value=True)),
        ):
            resp = client.delete("/api/v1/upload/64a1b2c3d4e5f6a7b8c9d0e1")
        assert "paper_id" in resp.json()


# ── POST /api/v1/upload/{paper_id}/reindex ────────────────────────────────────

class TestReindexEndpoint:
    def test_reindex_returns_200(self, client):
        paper = _make_paper()
        with (
            patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=paper)),
            patch("backend.routes.upload.chroma_client"),
            patch("backend.routes.upload.update_paper_status", new=AsyncMock()),
            patch("backend.routes.upload.process_upload_async", new=AsyncMock()),
        ):
            resp = client.post("/api/v1/upload/64a1b2c3d4e5f6a7b8c9d0e1/reindex")
        assert resp.status_code == 200

    def test_reindex_nonexistent_returns_404(self, client):
        with patch("backend.routes.upload.get_paper_by_id", new=AsyncMock(return_value=None)):
            resp = client.post("/api/v1/upload/000000000000000000000000/reindex")
        assert resp.status_code == 404
