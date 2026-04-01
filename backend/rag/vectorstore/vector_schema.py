from typing import TypedDict, Optional


class VectorMetadata(TypedDict, total=False):
    source_document: str       # filename or arxiv_id
    paper_title: Optional[str]
    authors: Optional[str]     # comma-joined list
    source: str                # upload | arxiv | semantic_scholar | openalex
    publication_year: Optional[str]
    arxiv_id: Optional[str]
    doi: Optional[str]
    subject_areas: Optional[str]   # comma-joined list
    section_id: Optional[str]
    paragraph_ref: Optional[str]
    page_number: Optional[int]
    chunk_index: int
    upload_id: Optional[str]
    content: Optional[str]     # stored text for retrieval
