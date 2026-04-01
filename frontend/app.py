import json
import time

import requests
import sseclient
import streamlit as st

BACKEND_URL = "http://localhost:8000"

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Academic Research RAG",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .fixed-disclaimer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 8px 20px;
        text-align: center;
        font-size: 12px;
        color: #6e6e80;
        z-index: 997;
        pointer-events: none;
    }
    section[data-testid="stChatInputContainer"] { bottom: 50px !important; }
    .stChatFloatingInputContainer,
    div[data-testid="stChatInputContainer"] { bottom: 50px !important; }
    .main .block-container { padding-bottom: 120px; }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-indexed   { background: #d4edda; color: #155724; }
    .badge-processing { background: #fff3cd; color: #856404; }
    .badge-uploaded  { background: #cce5ff; color: #004085; }
    .badge-failed    { background: #f8d7da; color: #721c24; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "papers_refresh" not in st.session_state:
    st.session_state.papers_refresh = 0


# ── Backend helpers ────────────────────────────────────────────────────────────

def fetch_papers() -> list:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/papers", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("papers", [])
    except Exception:
        pass
    return []


def upload_paper(
    file_bytes: bytes,
    filename: str,
    title: str,
    authors: str,
    year: str,
    force: bool,
) -> tuple:
    meta = {}
    if title:
        meta["title"] = title
    if authors:
        meta["authors"] = authors
    if year:
        meta["publication_year"] = year

    files = {"file": (filename, file_bytes, "application/pdf")}
    data = {
        "force_reupload": str(force).lower(),
        "metadata": json.dumps(meta) if meta else "",
    }
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/upload", files=files, data=data, timeout=60
    )
    return resp.json(), resp.status_code


def fetch_arxiv_paper(arxiv_id: str) -> tuple:
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/papers/fetch/arxiv/{arxiv_id.strip()}", timeout=30
    )
    return resp.json(), resp.status_code


def delete_paper(paper_id: str) -> bool:
    try:
        resp = requests.delete(
            f"{BACKEND_URL}/api/v1/papers/{paper_id}", timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


def reindex_paper(paper_id: str) -> bool:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/upload/{paper_id}/reindex", timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


def status_badge_html(status: str) -> str:
    cls_map = {
        "indexed": "badge-indexed",
        "processing": "badge-processing",
        "uploaded": "badge-uploaded",
        "failed": "badge-failed",
    }
    cls = cls_map.get(status.lower(), "badge-uploaded")
    return f'<span class="status-badge {cls}">{status.upper()}</span>'


# ── SSE streaming ──────────────────────────────────────────────────────────────

def stream_reply(user_msg: str, status_callback=None):
    """Generator: yields text chunks from the backend SSE chat endpoint."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/chat",
            json={"query": user_msg},
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=120,
        )

        if response.status_code != 200:
            yield f"❌ API Error {response.status_code}: {response.text}"
            return

        client = sseclient.SSEClient(response)
        current_status = ""

        for event in client.events():
            if not event.data or not event.data.strip():
                continue

            try:
                payload = json.loads(event.data)
            except json.JSONDecodeError:
                continue

            event_type = payload.get("type", "status")
            data = payload.get("data", "")

            if event_type == "status":
                if data and data != current_status:
                    current_status = data
                    if status_callback:
                        status_callback(data)

            elif event_type == "final":
                if status_callback:
                    status_callback("")
                # Stream the final answer word by word for a live-typing effect
                words = data.split(" ")
                for i, word in enumerate(words):
                    yield word + (" " if i < len(words) - 1 else "")
                    time.sleep(0.025)
                break

            elif event_type == "error":
                if status_callback:
                    status_callback("")
                yield f"\n\n❌ {data}"
                break

        else:
            # SSE stream ended without a final event
            if status_callback:
                status_callback("")
            yield "⚠️ No response received from the server."

    except requests.exceptions.ConnectionError:
        if status_callback:
            status_callback("")
        yield (
            "❌ Cannot connect to the backend. "
            f"Is it running at `{BACKEND_URL}`?"
        )
    except Exception as exc:
        if status_callback:
            status_callback("")
        yield f"❌ Streaming error: {exc}"


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎓 Research RAG")
    st.caption("Upload papers or fetch from arXiv, then ask questions.")
    st.divider()

    # ── Upload Paper ──────────────────────────────────────────────────────────
    with st.expander("📤 Upload Paper", expanded=False):
        with st.form("upload_form", clear_on_submit=True):
            uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"])
            st.caption("Optional metadata")
            title_input = st.text_input("Title")
            authors_input = st.text_input("Authors (comma-separated)")
            year_input = st.text_input("Publication Year")
            force_input = st.checkbox("Force re-upload if duplicate")
            upload_btn = st.form_submit_button("Upload", use_container_width=True)

        if upload_btn:
            if not uploaded_file:
                st.warning("Please select a PDF file.")
            else:
                with st.spinner("Uploading..."):
                    try:
                        result, code = upload_paper(
                            file_bytes=uploaded_file.getvalue(),
                            filename=uploaded_file.name,
                            title=title_input,
                            authors=authors_input,
                            year=year_input,
                            force=force_input,
                        )
                        if code == 200:
                            st.success(
                                f"✅ Uploaded! Processing in background.\n\n"
                                f"**ID:** `{result.get('paper_id', '')}`"
                            )
                            st.session_state.papers_refresh += 1
                        elif code == 409:
                            st.error(
                                "Duplicate — already indexed. "
                                "Enable **Force re-upload** to replace it."
                            )
                        else:
                            detail = result.get("detail", result)
                            st.error(f"Upload failed ({code}): {detail}")
                    except Exception as exc:
                        st.error(f"Upload error: {exc}")

    st.divider()

    # ── Fetch from arXiv ──────────────────────────────────────────────────────
    with st.expander("🔍 Fetch from arXiv", expanded=False):
        arxiv_input = st.text_input(
            "arXiv ID", placeholder="e.g. 2301.00001", key="arxiv_id_input"
        )
        if st.button("Fetch Paper", use_container_width=True):
            if not arxiv_input.strip():
                st.warning("Enter an arXiv ID.")
            else:
                with st.spinner(f"Fetching {arxiv_input.strip()}..."):
                    try:
                        result, code = fetch_arxiv_paper(arxiv_input.strip())
                        if code == 200:
                            fetched_title = result.get("title") or arxiv_input.strip()
                            st.success(f"✅ Fetched: **{fetched_title}**")
                            st.session_state.papers_refresh += 1
                        else:
                            detail = result.get("detail", result)
                            st.error(f"Failed ({code}): {detail}")
                    except Exception as exc:
                        st.error(f"Fetch error: {exc}")

    st.divider()

    # ── Papers Library ────────────────────────────────────────────────────────
    st.subheader("📚 Papers Library")

    col_refresh, col_count = st.columns([2, 1])
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_papers"):
            st.session_state.papers_refresh += 1

    papers = fetch_papers()

    with col_count:
        st.metric("Papers", len(papers))

    if not papers:
        st.info("No papers yet. Upload a PDF or fetch from arXiv.")
    else:
        for paper in papers:
            pid = paper.get("paper_id", "")
            raw_title = paper.get("title") or paper.get("filename", "Unknown")
            status = paper.get("status", "unknown")
            source = paper.get("source", "")
            arxiv_id = paper.get("arxiv_id")
            chunk_count = paper.get("chunk_count") or 0

            display_title = (raw_title[:38] + "…") if len(raw_title) > 38 else raw_title

            with st.container():
                col_info, col_actions = st.columns([3, 1])

                with col_info:
                    st.markdown(f"**{display_title}**")
                    badge = status_badge_html(status)
                    source_tag = f" · `{source}`" if source else ""
                    st.markdown(f"{badge}{source_tag}", unsafe_allow_html=True)
                    if arxiv_id:
                        st.caption(f"arXiv: {arxiv_id}")
                    if chunk_count:
                        st.caption(f"{chunk_count} chunks")

                with col_actions:
                    if st.button("🗑️", key=f"del_{pid}", help="Delete paper"):
                        if delete_paper(pid):
                            st.toast("Paper deleted")
                            st.session_state.papers_refresh += 1
                            st.rerun()
                        else:
                            st.error("Delete failed")

                    if status in ("failed", "indexed"):
                        if st.button("🔄", key=f"reindex_{pid}", help="Re-index"):
                            if reindex_paper(pid):
                                st.toast("Re-indexing started")
                                st.session_state.papers_refresh += 1
                            else:
                                st.error("Re-index failed")

                st.divider()


# ── Main chat area ─────────────────────────────────────────────────────────────

st.title("🎓 Academic Research RAG")
st.caption(
    "Ask questions about your research papers. "
    "Answers are grounded in indexed literature with full citations."
)

# Render existing chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input (floating at bottom)
user_input = st.chat_input("Ask a question about your research papers…")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        message_placeholder = st.empty()
        full_response = ""

        def update_status(text: str):
            if text:
                status_placeholder.markdown(f"*⚙️ {text}*")
            else:
                status_placeholder.empty()

        for chunk in stream_reply(user_input, status_callback=update_status):
            full_response += chunk
            # Show streaming cursor while building
            message_placeholder.markdown(full_response + "▌")

        # Final render — markdown with arXiv/DOI links from Sources block
        message_placeholder.markdown(full_response)
        status_placeholder.empty()

    st.session_state.messages.append({"role": "assistant", "content": full_response})


# ── Disclaimer ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="fixed-disclaimer">
        ⚠️ <strong>Disclaimer:</strong> AI-generated responses grounded in indexed research papers.
        Always verify claims against original sources before citing in academic work.
    </div>
    """,
    unsafe_allow_html=True,
)
