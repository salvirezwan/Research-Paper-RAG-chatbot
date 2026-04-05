---
title: Research Paper RAG Chatbot
emoji: 🔬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Research Paper RAG Chatbot

An AI-powered agentic RAG (Retrieval-Augmented Generation) system for students and researchers. Upload research papers or fetch them live from arXiv, then query across them in natural language with cited, context-aware responses — streamed in real time.

**Live Demo:** [Hugging Face Spaces](https://huggingface.co/spaces/salvirezwan/Research-Paper-RAG-chatbot)

---

## Features

- **Upload PDFs** — ingest your own research papers with a 4-step checkpointed pipeline
- **Fetch from arXiv** — download and index papers directly by arXiv ID
- **Agentic RAG pipeline** — LangGraph StateGraph with adaptive routing, document grading, and cited answer generation
- **Real-time streaming** — chat responses streamed via Server-Sent Events (SSE)
- **Session isolation** — each browser session has its own paper library and vector search scope
- **PDF Viewer** — read papers in-browser with page navigation

---

## Architecture

### RAG Pipeline (LangGraph StateGraph)

```
User Query → Router → [retrieve | live_fetch] → grade_docs → generator → citation → END
```

| Node | File | Description |
|------|------|-------------|
| **Router** | `nodes/router.py` | LLM classifies query as "retrieve" or "live_fetch" |
| **Retrieve** | `nodes/retrieve.py` | Searches local ChromaDB; scoped to session's papers |
| **Live Fetch** | `nodes/live_fetch.py` | Fetches from arXiv, indexes chunks |
| **Grade Docs** | `nodes/grade_docs.py` | LLM grades each chunk as relevant/irrelevant |
| **Generator** | `nodes/generator.py` | Builds context, calls Groq LLM, returns cited answer |
| **Citation** | `nodes/citation.py` | Appends formatted Sources block with arXiv/DOI links |

### Ingestion Pipeline (4-step, checkpointed)

```
PDF → Parse (PyMuPDF) → Clean → Chunk → Embed (BAAI/bge-base-en-v1.5) → ChromaDB
```

Each step is checkpointed in MongoDB. Retrying a failed ingestion skips already-completed steps.

### Storage

| Store | Purpose |
|-------|---------|
| ChromaDB | Vector embeddings for semantic search |
| MongoDB | Paper records, ingestion checkpoints, request logs |
| Local disk | Uploaded PDF files (`uploads/documents/`, `uploads/arxiv/`) |

### API Routes

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/chat` | SSE streaming chat |
| `POST /api/v1/upload` | Upload a PDF |
| `GET /api/v1/papers` | List papers (session-scoped) |
| `DELETE /api/v1/papers/{id}` | Delete a paper |
| `POST /api/v1/papers/fetch/arxiv/{id}` | Fetch & index an arXiv paper |
| `GET /api/v1/uploads/{id}/view` | Serve PDF for viewer |
| `GET /api/v1/health` | Health check |

---

## Quick Start (Local)

### Prerequisites

- Python 3.11+
- MongoDB running on `localhost:27017`
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### 1. Clone the repo

```bash
git clone https://github.com/salvirezwan/Research-Paper-RAG-chatbot.git
cd "Research-Paper-RAG-chatbot/Academic Research RAG"
```

### 2. Install dependencies

```bash
# Using uv (recommended)
pip install uv
uv sync

# Or using pip
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE_NAME=academic_research_rag
CHROMA_PERSIST_PATH=./data/chroma_db
CHROMA_COLLECTION_NAME=research_papers
GROQ_MODEL=llama-3.3-70b-versatile
EMBED_MODEL_NAME=BAAI/bge-base-en-v1.5
UPLOAD_DIR=uploads/documents
```

> Get a free Groq API key at [console.groq.com](https://console.groq.com)

### 4. Run

```bash
# Option A — dev shortcut (Windows, opens two terminals)
.\dev.bat

# Option B — manual
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
streamlit run frontend/app.py
```

- Backend: http://localhost:8000
- Frontend: http://localhost:8501
- API Docs: http://localhost:8000/docs

---

## Docker (Full Stack)

```bash
docker compose -f docker/docker-compose.yml up --build
```

- Frontend: http://localhost:8501
- Backend: http://localhost:8000

---

## Hugging Face Spaces Deployment

The app runs as a single Docker container on a free HF Space (2 vCPU / 16 GB RAM).

### Process layout

```
supervisord (PID 1)
├── nginx        → port 7860  (reverse proxy)
│   ├── /api/*  → 127.0.0.1:8000  (FastAPI)
│   └── /*      → 127.0.0.1:8501  (Streamlit)
├── uvicorn      → port 8000
└── streamlit    → port 8501
```

### Ephemeral storage

Since HF Spaces has no persistent disk, the app uses:
- **ChromaDB** `EphemeralClient` (in-memory vectors)
- **mongomock-motor** `AsyncMongoMockClient` (in-memory MongoDB)
- `/tmp/uploads/` for uploaded files

> All data is lost on restart — expected behaviour for the free tier.

### Deploy your own

1. Create a new Space at [huggingface.co](https://huggingface.co) → **Docker** SDK
2. Push this repo to the Space's git remote
3. Space Settings → **Secrets**: add `GROQ_API_KEY`
4. Space Settings → **Variables**: add `APP_PUBLIC_URL` = `https://<your-username>-<your-space-name>.hf.space`
5. First startup takes ~5 min (downloads the ~450 MB embedding model)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | **Required.** Groq API key |
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE_NAME` | `academic_research_rag` | Database name |
| `CHROMA_PERSIST_PATH` | `./data/chroma_db` | ChromaDB storage path |
| `CHROMA_COLLECTION_NAME` | `research_papers` | ChromaDB collection |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `EMBED_MODEL_NAME` | `BAAI/bge-base-en-v1.5` | HuggingFace embedding model |
| `UPLOAD_DIR` | `uploads/documents` | PDF upload directory |
| `APP_PUBLIC_URL` | `` | Public base URL (required for HF Spaces) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Groq API (LLaMA-3.3-70B) |
| Orchestration | LangGraph |
| Backend | FastAPI, Python 3.11 |
| Frontend | Streamlit |
| Vector Store | ChromaDB |
| Embeddings | BAAI/bge-base-en-v1.5 (HuggingFace) |
| Database | MongoDB (Motor async) |
| PDF Parsing | PyMuPDF, Unstructured |
| Deployment | Docker, nginx, supervisord, Hugging Face Spaces |
| Paper Sources | arXiv API |

