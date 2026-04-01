"""
Integration tests for the ingestion pipeline (services/ingestion_service.py).

All external I/O (PDF parsing, ChromaDB indexing, MongoDB checkpoints) is
mocked so these tests run without real infrastructure.
"""
import pytest
from unittest.mock import AsyncMock, patch


# ── Import sanity check ────────────────────────────────────────────────────────

class TestImports:
    def test_ingestion_service_imports_successfully(self):
        """
        ingestion_service.py must import cleanly — it uses clean_pages from
        cleaner.py (previously broken as clean_text, now fixed).
        """
        import importlib
        import sys

        sys.modules.pop("backend.services.ingestion_service", None)
        # Should not raise — clean_pages exists in cleaner.py
        importlib.import_module("backend.services.ingestion_service")


# ── Pipeline step tests (with bug patched) ────────────────────────────────────

@pytest.fixture()
def patched_ingestion_service():
    """
    Import ingestion_service with the `clean_text` bug patched so we can test
    the rest of the pipeline logic.
    """
    import sys
    import types

    # Patch cleaner to expose clean_text as an alias for _clean_page
    from backend.rag.ingestion import cleaner as cleaner_mod

    # Temporarily add clean_text as an alias so the import succeeds
    cleaner_mod.clean_text = cleaner_mod._clean_page

    # Re-import the service with the patched cleaner
    sys.modules.pop("backend.services.ingestion_service", None)
    import backend.services.ingestion_service as svc

    yield svc

    # Clean up the alias
    del cleaner_mod.clean_text
    sys.modules.pop("backend.services.ingestion_service", None)


class TestIngestionPipelineSteps:
    @pytest.mark.asyncio
    async def test_pipeline_runs_all_four_steps(self, patched_ingestion_service):
        """Happy-path: all 4 steps execute and return success."""
        fake_pages = ["Page one text about neural networks.", "Page two text."]
        fake_chunks = [
            {"content": "chunk 1", "source_document": "test.pdf", "chunk_index": 0},
        ]
        fake_index_result = {"status": "success", "chunks_indexed": 1, "errors": 0}

        with (
            patch("backend.services.ingestion_service.get_checkpoint",
                  new=AsyncMock(return_value=None)),
            patch("backend.services.ingestion_service.create_checkpoint",
                  new=AsyncMock(return_value="cp_id")),
            patch("backend.services.ingestion_service.mark_step_failed",
                  new=AsyncMock()),
            patch("backend.services.ingestion_service.parse_pdf",
                  return_value=fake_pages),
            patch("backend.services.ingestion_service.chunk_paper",
                  return_value=fake_chunks),
            patch("backend.services.ingestion_service.index_chunks",
                  return_value=fake_index_result),
        ):
            result = await patched_ingestion_service.run_ingestion_pipeline(
                pdf_path="/fake/paper.pdf",
                source_document="paper.pdf",
                upload_id="test_upload_id",
            )

        assert result["status"] == "success"
        assert result["pages_processed"] == 2
        assert result["chunks_created"] == 1

    @pytest.mark.asyncio
    async def test_pipeline_resumes_from_completed_parse_checkpoint(
        self, patched_ingestion_service
    ):
        """If parsing checkpoint already exists, parse_pdf should NOT be called."""
        saved_pages = ["Cached page one.", "Cached page two."]
        parse_cp = {"status": "completed", "data": {"pages": saved_pages}}
        fake_chunks = [{"content": "c", "source_document": "p.pdf", "chunk_index": 0}]

        call_log = []

        def _track_parse(path):
            call_log.append("parse_pdf")
            return saved_pages

        with (
            patch("backend.services.ingestion_service.get_checkpoint",
                  new=AsyncMock(side_effect=lambda uid, step: parse_cp if step == "parsing" else None)),
            patch("backend.services.ingestion_service.create_checkpoint",
                  new=AsyncMock(return_value="cp")),
            patch("backend.services.ingestion_service.mark_step_failed",
                  new=AsyncMock()),
            patch("backend.services.ingestion_service.parse_pdf", side_effect=_track_parse),
            patch("backend.services.ingestion_service.chunk_paper", return_value=fake_chunks),
            patch("backend.services.ingestion_service.index_chunks",
                  return_value={"chunks_indexed": 1}),
        ):
            await patched_ingestion_service.run_ingestion_pipeline(
                pdf_path="/fake/paper.pdf",
                source_document="paper.pdf",
                upload_id="uid",
            )

        assert "parse_pdf" not in call_log, "parse_pdf should not be called when checkpoint exists"

    @pytest.mark.asyncio
    async def test_pipeline_marks_step_failed_on_parse_error(
        self, patched_ingestion_service
    ):
        """A parse failure should call mark_step_failed and re-raise."""
        mark_failed = AsyncMock()

        with (
            patch("backend.services.ingestion_service.get_checkpoint",
                  new=AsyncMock(return_value=None)),
            patch("backend.services.ingestion_service.mark_step_failed", new=mark_failed),
            patch("backend.services.ingestion_service.parse_pdf",
                  side_effect=RuntimeError("PDF corrupted")),
        ):
            with pytest.raises(RuntimeError, match="PDF corrupted"):
                await patched_ingestion_service.run_ingestion_pipeline(
                    pdf_path="/bad.pdf",
                    source_document="bad.pdf",
                    upload_id="uid",
                )

        mark_failed.assert_called_once_with("uid", "parsing", "PDF corrupted")

    @pytest.mark.asyncio
    async def test_pipeline_marks_indexing_step_failed(self, patched_ingestion_service):
        """An indexing failure should call mark_step_failed for the indexing step."""
        fake_pages = ["page text"]
        fake_chunks = [{"content": "c", "source_document": "p.pdf", "chunk_index": 0}]
        mark_failed = AsyncMock()

        with (
            patch("backend.services.ingestion_service.get_checkpoint",
                  new=AsyncMock(return_value=None)),
            patch("backend.services.ingestion_service.create_checkpoint",
                  new=AsyncMock(return_value="cp")),
            patch("backend.services.ingestion_service.mark_step_failed", new=mark_failed),
            patch("backend.services.ingestion_service.parse_pdf", return_value=fake_pages),
            patch("backend.services.ingestion_service.chunk_paper", return_value=fake_chunks),
            patch("backend.services.ingestion_service.index_chunks",
                  side_effect=RuntimeError("ChromaDB unavailable")),
        ):
            with pytest.raises(RuntimeError):
                await patched_ingestion_service.run_ingestion_pipeline(
                    pdf_path="/paper.pdf",
                    source_document="paper.pdf",
                    upload_id="uid",
                )

        # mark_step_failed should have been called for the indexing step
        called_steps = [call.args[1] for call in mark_failed.call_args_list]
        assert "indexing" in called_steps

    @pytest.mark.asyncio
    async def test_pipeline_without_upload_id_skips_checkpoints(
        self, patched_ingestion_service
    ):
        """When upload_id is None no checkpoint calls should be made."""
        get_cp = AsyncMock()
        create_cp = AsyncMock()
        fake_pages = ["text"]
        fake_chunks = [{"content": "c", "source_document": "p.pdf", "chunk_index": 0}]

        with (
            patch("backend.services.ingestion_service.get_checkpoint", new=get_cp),
            patch("backend.services.ingestion_service.create_checkpoint", new=create_cp),
            patch("backend.services.ingestion_service.parse_pdf", return_value=fake_pages),
            patch("backend.services.ingestion_service.chunk_paper", return_value=fake_chunks),
            patch("backend.services.ingestion_service.index_chunks",
                  return_value={"chunks_indexed": 1}),
        ):
            await patched_ingestion_service.run_ingestion_pipeline(
                pdf_path="/paper.pdf",
                source_document="paper.pdf",
                upload_id=None,
            )

        get_cp.assert_not_called()
        create_cp.assert_not_called()
