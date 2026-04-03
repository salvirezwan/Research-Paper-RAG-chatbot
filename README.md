---
title: Academic Research RAG
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Academic Research RAG

An AI-powered agentic RAG system for students and researchers. Upload research papers or fetch them live from arXiv, then query across them in natural language with cited, context-aware responses streamed in real time.

## Features

- Upload PDF research papers or fetch directly by arXiv ID
- Agentic RAG pipeline: routes queries, retrieves relevant chunks, grades relevance, generates answers
- Streaming responses with citations (paper title, authors, arXiv/DOI links)
- Built with FastAPI, Streamlit, LangGraph, ChromaDB, and Groq LLM

## Usage

1. **Upload a paper** — use the sidebar to upload a PDF or enter an arXiv ID (e.g. `2401.03560`)
2. **Wait for indexing** — the paper is parsed, chunked, embedded, and indexed (~15–60s for arXiv)
3. **Ask questions** — type any question about your papers in the chat

> **Note:** This is a stateless deployment. All uploaded papers and chat history are wiped on restart.

## Stack

| Component | Technology |
|-----------|-----------|
| LLM | Groq (llama-3.3-70b-versatile) |
| Embeddings | BAAI/bge-base-en-v1.5 (local) |
| Vector store | ChromaDB (in-memory) |
| RAG pipeline | LangGraph |
| Backend | FastAPI + uvicorn |
| Frontend | Streamlit |

## Local Development

```bash
# Copy and fill in your API key
cp .env.example .env

# Install dependencies
pip install uv
uv sync

# Start backend + frontend
.\dev.bat   # Windows
```

Requires MongoDB running locally on port 27017.

## API Docs

Available at `/docs` (Swagger UI) or `/redoc`.
