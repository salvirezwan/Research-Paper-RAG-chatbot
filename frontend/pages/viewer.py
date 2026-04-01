"""
PDF Viewer page — opened via link from chat citations.

URL query params:
  ?doc=<paper_id>   — required, the MongoDB paper_id
  ?page=<int>       — optional, scroll to this 1-based page number
"""
import json
import traceback
from urllib.parse import unquote

import requests
import streamlit as st
import streamlit.components.v1 as components

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Document Viewer", layout="wide")

# ── Query params ───────────────────────────────────────────────────────────────
query_params = st.query_params

def _qp(key: str, default=None):
    val = query_params.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val else default

paper_id   = _qp("doc")
page_raw   = _qp("page")
section_raw = _qp("section")

page_number = None
if page_raw:
    try:
        page_number = int(page_raw)
        if page_number < 1:
            page_number = None
    except (ValueError, TypeError):
        page_number = None

section_id = unquote(section_raw) if section_raw else None

# ── UI ─────────────────────────────────────────────────────────────────────────
st.title("📄 Document Viewer")

if not paper_id:
    # ── Paper browser: let users pick a paper to view ──────────────────────────
    st.info("Select a paper below to view its PDF, or use a citation link from the chat.")

    try:
        papers_resp = requests.get(f"{BACKEND_URL}/api/v1/papers", timeout=10)
        if papers_resp.status_code == 200:
            papers = papers_resp.json().get("papers", [])
        else:
            papers = []
    except Exception:
        papers = []
        st.warning("⚠️ Could not connect to the backend. Is it running?")

    if not papers:
        st.write("No papers in the library yet. Upload a PDF or fetch from arXiv on the main page.")
        st.stop()

    # Show papers as cards
    for paper in papers:
        pid = paper.get("paper_id", "")
        title = paper.get("title") or paper.get("filename", "Untitled")
        authors = paper.get("authors") or []
        status = paper.get("status", "unknown")
        source = paper.get("source", "")
        year = paper.get("publication_year", "")
        arxiv_id = paper.get("arxiv_id", "")
        chunk_count = paper.get("chunk_count", 0)

        with st.container():
            col_info, col_btn = st.columns([4, 1])

            with col_info:
                st.markdown(f"**{title}**")
                meta_parts = []
                if authors:
                    auth_str = ", ".join(authors) if isinstance(authors, list) else str(authors)
                    meta_parts.append(auth_str)
                if year:
                    meta_parts.append(f"({year})")
                if meta_parts:
                    st.caption(" ".join(meta_parts))
                tags = []
                if source:
                    tags.append(f"`{source}`")
                if status:
                    tags.append(f"`{status}`")
                if chunk_count:
                    tags.append(f"{chunk_count} chunks")
                if arxiv_id:
                    tags.append(f"arXiv: {arxiv_id}")
                if tags:
                    st.caption(" · ".join(tags))

            with col_btn:
                if status == "indexed":
                    if st.button("📄 View", key=f"view_{pid}", use_container_width=True):
                        st.query_params["doc"] = pid
                        st.rerun()
                else:
                    st.button(
                        "📄 View",
                        key=f"view_{pid}",
                        use_container_width=True,
                        disabled=True,
                        help=f"Paper status: {status} — not viewable yet",
                    )

            st.divider()

    st.stop()

pdf_url = f"{BACKEND_URL}/api/v1/uploads/{paper_id}/view"

# Build JS search terms from section_id if no explicit page given
search_terms_js = "[]"
if not page_number and section_id:
    import re
    clean = re.sub(r"\s+", " ", str(section_id).strip())
    words = [w for w in clean.split() if len(w) > 2][:5]
    escaped = [w.replace("\\", "\\\\").replace('"', '\\"') for w in words]
    search_terms_js = json.dumps(escaped)

target_page_js = json.dumps(page_number)

try:
    with st.spinner("Loading document…"):
        resp = requests.get(pdf_url, stream=True, timeout=15)

    if resp.status_code == 404:
        st.error("❌ Document not found. It may have been deleted.")
        st.stop()

    if resp.status_code != 200:
        st.error(f"❌ Backend returned {resp.status_code}")
        st.stop()

    pdf_bytes = resp.content

    # ── Metadata header ────────────────────────────────────────────────────────
    try:
        meta_resp = requests.get(
            f"{BACKEND_URL}/api/v1/papers/{paper_id}", timeout=10
        )
        if meta_resp.status_code == 200:
            meta = meta_resp.json()
            title   = meta.get("title") or meta.get("filename", "Unknown")
            authors = meta.get("authors") or []
            year    = meta.get("publication_year") or ""
            arxiv   = meta.get("arxiv_id") or ""
            doi     = meta.get("doi") or ""

            st.subheader(title)
            if authors:
                st.caption(", ".join(authors) + (f" ({year})" if year else ""))
            if arxiv:
                st.caption(f"arXiv: {arxiv}")
            elif doi:
                st.caption(f"DOI: {doi}")
    except Exception:
        pass

    st.divider()

    # ── PDF.js viewer ──────────────────────────────────────────────────────────
    pdf_viewer_html = f"""
    <div id="pdf-container"
         style="width:100%;height:800px;border:1px solid #ccc;position:relative;
                background:#525252;overflow-y:auto;overflow-x:hidden;">
      <div id="pdf-loading" style="text-align:center;padding:50px;color:white;">
        <p>Loading PDF…</p>
      </div>
      <div id="pdf-viewer-wrapper" style="display:none;padding:20px;">
        <div id="pdf-pages" style="text-align:center;"></div>
      </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
    <script>
    (function() {{
        const pdfUrl       = {json.dumps(pdf_url)};
        const targetPage   = {target_page_js};
        const searchTerms  = {search_terms_js};
        const scale        = 1.5;

        let pdfDoc     = null;
        let totalPages = 0;

        // ── Wait for PDF.js to be ready ──────────────────────────────────────
        let retries = 0;
        function init() {{
            if (typeof pdfjsLib === 'undefined') {{
                if (++retries < 100) {{ setTimeout(init, 100); return; }}
                showError('PDF.js library failed to load. Check your internet connection.');
                return;
            }}

            pdfjsLib.GlobalWorkerOptions.workerSrc =
                'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

            pdfjsLib.getDocument({{ url: pdfUrl, withCredentials: false }}).promise
                .then(function(pdf) {{
                    pdfDoc     = pdf;
                    totalPages = pdf.numPages;
                    document.getElementById('pdf-loading').style.display      = 'none';
                    document.getElementById('pdf-viewer-wrapper').style.display = 'block';

                    if (targetPage !== null && targetPage > 0 && targetPage <= totalPages) {{
                        renderAll(targetPage);
                    }} else if (searchTerms.length > 0) {{
                        searchAndNavigate(searchTerms).then(function(found) {{
                            renderAll(found || 1);
                        }});
                    }} else {{
                        renderAll(1);
                    }}
                }})
                .catch(function(err) {{
                    let msg = err.message || String(err);
                    if (msg.includes('Failed to fetch'))
                        msg = 'Cannot reach the backend server. Ensure it is running.';
                    showError(msg);
                }});
        }}

        // ── Render all pages, prioritising startPage ─────────────────────────
        function renderAll(startPage) {{
            const container = document.getElementById('pdf-pages');
            container.innerHTML = '';

            for (let i = 1; i <= totalPages; i++) {{
                const div    = document.createElement('div');
                div.id       = 'page-' + i;
                div.style.marginBottom = '20px';
                div.style.textAlign    = 'center';
                div.dataset.rendered   = 'false';

                const canvas = document.createElement('canvas');
                canvas.style.border    = '1px solid #ccc';
                canvas.style.boxShadow = '0 2px 5px rgba(0,0,0,.3)';
                canvas.style.display   = 'block';
                canvas.style.margin    = '0 auto';
                div.appendChild(canvas);
                container.appendChild(div);
            }}

            function renderPage(n) {{
                return pdfDoc.getPage(n).then(function(page) {{
                    const viewport = page.getViewport({{ scale: scale }});
                    const div      = document.getElementById('page-' + n);
                    const canvas   = div.querySelector('canvas');
                    canvas.width   = viewport.width;
                    canvas.height  = viewport.height;
                    return page.render({{ canvasContext: canvas.getContext('2d'), viewport: viewport }}).promise
                        .then(function() {{ div.dataset.rendered = 'true'; }})
                        .catch(function() {{ div.dataset.rendered = 'true'; }});
                }}).catch(function() {{
                    const div = document.getElementById('page-' + n);
                    if (div) div.dataset.rendered = 'true';
                }});
            }}

            // Render start page first, then the rest
            const priority = [startPage];
            for (let i = 1; i <= totalPages; i++) {{ if (i !== startPage) priority.push(i); }}

            renderPage(startPage).then(function() {{
                scrollToPage(startPage);
                const remaining = priority.slice(1).map(renderPage);
                Promise.all(remaining).catch(function() {{}});
            }});
        }}

        // ── Scroll to a specific page div ────────────────────────────────────
        function scrollToPage(n) {{
            const outerContainer = document.getElementById('pdf-container');
            function attempt(retries) {{
                const target = document.getElementById('page-' + n);
                if (!target) return;
                if (target.dataset.rendered !== 'true' && retries > 0) {{
                    setTimeout(function() {{ attempt(retries - 1); }}, 100);
                    return;
                }}
                const top = target.offsetTop - 10;
                outerContainer.scrollTo({{ top: top, behavior: 'smooth' }});

                // Brief highlight
                target.style.outline = '3px solid #4CAF50';
                target.style.borderRadius = '4px';
                setTimeout(function() {{
                    target.style.outline      = '';
                    target.style.borderRadius = '';
                }}, 2500);
            }}
            setTimeout(function() {{ attempt(30); }}, 300);
        }}

        // ── Full-text search across pages ────────────────────────────────────
        function searchAndNavigate(terms) {{
            const promises = [];
            for (let i = 1; i <= totalPages; i++) {{
                (function(pageNum) {{
                    promises.push(
                        pdfDoc.getPage(pageNum).then(function(page) {{
                            return page.getTextContent().then(function(tc) {{
                                const text  = tc.items.map(function(it) {{ return it.str; }}).join(' ').toLowerCase();
                                const hits  = terms.filter(function(t) {{ return t.length > 1 && text.includes(t.toLowerCase()); }}).length;
                                const need  = terms.length <= 2 ? terms.length : 2;
                                return hits >= need ? pageNum : null;
                            }});
                        }})
                    );
                }})(i);
            }}
            return Promise.all(promises).then(function(results) {{
                return results.find(function(r) {{ return r !== null; }}) || null;
            }});
        }}

        // ── Error display ────────────────────────────────────────────────────
        function showError(msg) {{
            const el = document.getElementById('pdf-loading');
            if (el) el.innerHTML =
                '<div style="padding:20px;text-align:center;color:white;">' +
                '<p style="font-size:16px;font-weight:bold;">❌ Error loading PDF</p>' +
                '<p>' + msg + '</p></div>';
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', init);
        }} else {{
            init();
        }}
    }})();
    </script>
    """

    st.markdown(
        """
        <style>
        iframe[title*="streamlit"], iframe[title*="html"],
        div[data-testid="stHtml"] { margin: 0 !important; padding: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    components.html(pdf_viewer_html, height=820, scrolling=True)

    st.download_button(
        label="📥 Download PDF",
        data=pdf_bytes,
        file_name=f"paper_{paper_id}.pdf",
        mime="application/pdf",
    )

    if page_number or section_id:
        nav_desc = f"page {page_number}" if page_number else f"section: {section_id}"
        st.info(f"💡 Opened to {nav_desc}. Scroll to find the relevant passage.")

except requests.exceptions.ConnectionError:
    st.error(
        f"❌ Cannot connect to the backend at `{BACKEND_URL}`. "
        "Make sure it is running."
    )
except Exception as exc:
    st.error(f"❌ Unexpected error: {exc}")
    with st.expander("Details"):
        st.code(traceback.format_exc())
