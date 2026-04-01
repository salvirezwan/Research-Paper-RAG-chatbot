"""
Shared fixtures for the Academic Research RAG test suite.

Heavy optional dependencies (chromadb, motor, sentence_transformers, fitz,
unstructured) are stubbed out at the sys.modules level *before* any backend
module is imported.  This lets the test suite run without those packages
installed, and without a live MongoDB or ChromaDB instance.
"""
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Stub heavy optional dependencies BEFORE any backend import ────────────────
# chromadb — chroma_client.py creates a PersistentClient at module load time
_chroma_stub = MagicMock()
_chroma_stub.PersistentClient.return_value = MagicMock()
sys.modules.setdefault("chromadb", _chroma_stub)
sys.modules.setdefault("chromadb.config", MagicMock())

# motor — mongodb_client.py creates AsyncIOMotorClient at module load time
_motor_stub = MagicMock()
sys.modules.setdefault("motor", _motor_stub)
sys.modules.setdefault("motor.motor_asyncio", MagicMock())

# pymongo — only used for error types; a mock is fine
sys.modules.setdefault("pymongo", MagicMock())
sys.modules.setdefault("pymongo.errors", MagicMock())

# sentence_transformers — heavy model loader
sys.modules.setdefault("sentence_transformers", MagicMock())

# fitz (PyMuPDF) — binary extension
sys.modules.setdefault("fitz", MagicMock())

# unstructured — large optional dep
sys.modules.setdefault("unstructured", MagicMock())
sys.modules.setdefault("unstructured.partition", MagicMock())
sys.modules.setdefault("unstructured.partition.pdf", MagicMock())

# langchain / langgraph — LLM stack; not needed for unit/route tests
sys.modules.setdefault("langchain_core", MagicMock())
sys.modules.setdefault("langchain_core.messages", MagicMock())
sys.modules.setdefault("langchain_core.language_models", MagicMock())
sys.modules.setdefault("langchain_groq", MagicMock())
sys.modules.setdefault("langgraph", MagicMock())
sys.modules.setdefault("langgraph.graph", MagicMock())

# sseclient — frontend only
sys.modules.setdefault("sseclient", MagicMock())

# ── Now safe to import backend ─────────────────────────────────────────────────
from unittest.mock import patch  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """
    FastAPI TestClient with startup/shutdown events mocked so tests do not
    require a live MongoDB or ChromaDB instance.
    """
    with (
        patch("backend.data.init_db.init_database", new=AsyncMock(return_value=True)),
        patch(
            "backend.data.mongodb_client.close_mongodb_connection",
            new=AsyncMock(return_value=None),
        ),
    ):
        from backend.main import app  # imported here so patches are active

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── Reusable data fixtures ─────────────────────────────────────────────────────

@pytest.fixture()
def minimal_pdf_bytes() -> bytes:
    """
    A minimal valid-looking PDF byte string (enough for hash / storage tests).
    Not a real parseable PDF — use only where parsing is mocked.
    """
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 1\ntrailer<</Size 1>>\n%%EOF"


@pytest.fixture()
def sample_pages() -> list:
    """Two pages of realistic research-paper text."""
    return [
        (
            "Abstract\n\n"
            "We present a novel approach to neural machine translation using "
            "transformer architectures.  Our method achieves state-of-the-art "
            "results on WMT 2023 benchmarks.\n\n"
            "Introduction\n\n"
            "Neural machine translation (NMT) has transformed the field.  "
            "Previous work [1] demonstrated that attention mechanisms are key."
        ),
        (
            "Methods\n\n"
            "We train a 6-layer transformer with 512 hidden units and 8 attention "
            "heads.  Training uses the Adam optimiser with a learning rate of 1e-4.\n\n"
            "Results\n\n"
            "Our model achieves 34.2 BLEU on newstest2023, outperforming all "
            "prior baselines by a significant margin."
        ),
    ]
