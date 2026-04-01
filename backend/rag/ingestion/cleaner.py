import re
from typing import List

from backend.core.logging import logger


def clean_pages(pages: List[str]) -> List[str]:
    """
    Clean raw PDF-extracted text pages for research papers.

    No LLM needed — research papers are English text that only needs
    lightweight normalization after PyMuPDF/Unstructured extraction.

    Fails immediately on error to allow precise resumption (mirrors old project pattern).

    Args:
        pages: Raw text per page from the parser.

    Returns:
        List of cleaned text pages.

    Raises:
        RuntimeError: On any page-level error, with the page index for resumption.
    """
    cleaned = []
    for i, page_text in enumerate(pages):
        if not page_text.strip():
            cleaned.append("")
            continue
        try:
            cleaned.append(_clean_page(page_text))
        except Exception as e:
            error_msg = f"Text cleaning failed at page {i + 1}/{len(pages)}: {e}"
            logger.error(f"[CHECKPOINT] {error_msg}")
            logger.error(f"[CHECKPOINT] Will resume from page {i + 1} ({i} pages already cleaned)")
            raise RuntimeError(error_msg) from e

    logger.info(f"[CHECKPOINT] Text cleaning completed: {len(cleaned)} pages cleaned")
    return cleaned


def _clean_page(text: str) -> str:
    # Remove null bytes and form-feed characters
    text = text.replace("\x00", "").replace("\x0c", "\n")

    # Join hyphenated line breaks (common in PDF extraction): "hyphen-\nated" → "hyphenated"
    text = re.sub(r"-\n(\w)", r"\1", text)

    # Collapse multiple blank lines to a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are just page numbers or headers/footers (short lines with only digits)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip bare page-number lines (1-4 digit numbers on their own)
        if re.fullmatch(r"\d{1,4}", stripped):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Normalize whitespace within lines (collapse multiple spaces/tabs)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()
