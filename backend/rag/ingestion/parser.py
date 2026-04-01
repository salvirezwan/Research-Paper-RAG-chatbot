from pathlib import Path
from typing import List

from backend.core.logging import logger


def parse_pdf(pdf_path: str) -> List[str]:
    """
    Extract text from a PDF file, one string per page.

    Tries PyMuPDF (fitz) first for fast extraction.
    Falls back to Unstructured if PyMuPDF yields no text.

    Args:
        pdf_path: Absolute path to the PDF file.

    Returns:
        List of page texts (empty string for blank pages).

    Raises:
        FileNotFoundError: If the PDF does not exist.
        RuntimeError: If both parsers fail.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = _parse_with_pymupdf(pdf_path)

    if _has_content(pages):
        logger.info(f"Parsed PDF with PyMuPDF: {len(pages)} pages from '{path.name}'")
        return pages

    logger.warning(f"PyMuPDF yielded no text for '{path.name}', trying Unstructured...")
    pages = _parse_with_unstructured(pdf_path)

    if _has_content(pages):
        logger.info(f"Parsed PDF with Unstructured: {len(pages)} pages from '{path.name}'")
        return pages

    raise RuntimeError(f"Both parsers failed to extract text from '{path.name}'")


def _has_content(pages: List[str]) -> bool:
    return bool(pages) and any(p.strip() for p in pages)


def _parse_with_pymupdf(pdf_path: str) -> List[str]:
    try:
        import fitz  # PyMuPDF

        pages = []
        doc = fitz.open(pdf_path)
        for page in doc:
            text = page.get_text("text")
            pages.append(text or "")
        doc.close()
        return pages

    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed, skipping.")
        return []
    except Exception as e:
        logger.warning(f"PyMuPDF parsing error: {e}")
        return []


def _parse_with_unstructured(pdf_path: str) -> List[str]:
    try:
        from unstructured.partition.pdf import partition_pdf

        elements = partition_pdf(filename=pdf_path, strategy="fast")

        # Group elements by page number
        pages_dict: dict[int, list[str]] = {}
        for el in elements:
            page_num = el.metadata.page_number if el.metadata.page_number else 1
            pages_dict.setdefault(page_num, []).append(str(el))

        if not pages_dict:
            return []

        max_page = max(pages_dict.keys())
        return ["\n".join(pages_dict.get(i, [])) for i in range(1, max_page + 1)]

    except ImportError:
        logger.warning("Unstructured not installed, skipping.")
        return []
    except Exception as e:
        logger.warning(f"Unstructured parsing error: {e}")
        return []
