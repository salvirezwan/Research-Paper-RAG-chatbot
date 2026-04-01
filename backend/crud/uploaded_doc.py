from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from backend.data.mongodb_client import get_database
from backend.models.uploaded_doc import ResearchPaper, PaperStatus, PaperSource
from backend.core.logging import logger


async def create_paper_record(
    filename: str,
    stored_path: str,
    file_hash: str,
    source: PaperSource,
    status: PaperStatus = PaperStatus.UPLOADED,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    abstract: Optional[str] = None,
    publication_year: Optional[str] = None,
    doi: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    semantic_scholar_id: Optional[str] = None,
    subject_areas: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> ResearchPaper:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    paper = ResearchPaper(
        filename=filename,
        stored_path=stored_path,
        file_hash=file_hash,
        source=source,
        status=status,
        title=title,
        authors=authors,
        abstract=abstract,
        publication_year=publication_year,
        doi=doi,
        arxiv_id=arxiv_id,
        semantic_scholar_id=semantic_scholar_id,
        subject_areas=subject_areas,
        metadata=metadata
    )

    try:
        result = await collection.insert_one(paper.to_mongo())
        paper.id = result.inserted_id
        logger.info(f"Created paper record: {filename} (ID: {result.inserted_id})")
        return paper
    except DuplicateKeyError:
        logger.warning(f"Duplicate paper detected: {file_hash}")
        raise


async def get_paper_by_id(paper_id: str) -> Optional[ResearchPaper]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    try:
        doc = await collection.find_one({"_id": ObjectId(paper_id)})
        if doc:
            return ResearchPaper.from_mongo(doc)
        return None
    except Exception as e:
        logger.error(f"Error getting paper by ID {paper_id}: {e}")
        return None


async def get_paper_by_hash(file_hash: str) -> Optional[ResearchPaper]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    doc = await collection.find_one({"file_hash": file_hash})
    if doc:
        return ResearchPaper.from_mongo(doc)
    return None


async def get_paper_by_arxiv_id(arxiv_id: str) -> Optional[ResearchPaper]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    doc = await collection.find_one({"arxiv_id": arxiv_id})
    if doc:
        return ResearchPaper.from_mongo(doc)
    return None


async def update_paper_status(
    paper_id: str,
    status: PaperStatus,
    chunk_count: Optional[int] = None,
    error_message: Optional[str] = None
) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    update_data = {"status": status.value}

    if status == PaperStatus.INDEXED:
        update_data["processed_at"] = datetime.now(timezone.utc)

    if chunk_count is not None:
        update_data["chunk_count"] = chunk_count

    if error_message is not None:
        update_data["error_message"] = error_message

    try:
        result = await collection.update_one(
            {"_id": ObjectId(paper_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating paper status {paper_id}: {e}")
        return False


async def update_paper_metadata(
    paper_id: str,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    abstract: Optional[str] = None,
    publication_year: Optional[str] = None,
    doi: Optional[str] = None,
    subject_areas: Optional[List[str]] = None
) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    update_data = {}
    if title is not None:
        update_data["title"] = title
    if authors is not None:
        update_data["authors"] = authors
    if abstract is not None:
        update_data["abstract"] = abstract
    if publication_year is not None:
        update_data["publication_year"] = publication_year
    if doi is not None:
        update_data["doi"] = doi
    if subject_areas is not None:
        update_data["subject_areas"] = subject_areas

    if not update_data:
        return True

    try:
        result = await collection.update_one(
            {"_id": ObjectId(paper_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating paper metadata {paper_id}: {e}")
        return False


async def list_papers(
    source: Optional[PaperSource] = None,
    status: Optional[PaperStatus] = None,
    publication_year: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[ResearchPaper]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    filter_dict = {}
    if source:
        filter_dict["source"] = source.value
    if status:
        filter_dict["status"] = status.value
    if publication_year:
        filter_dict["publication_year"] = publication_year

    try:
        cursor = collection.find(filter_dict).sort("uploaded_at", -1).skip(offset).limit(limit)
        papers = []
        async for doc in cursor:
            papers.append(ResearchPaper.from_mongo(doc))
        return papers
    except Exception as e:
        logger.error(f"Error listing papers: {e}")
        return []


async def delete_paper(paper_id: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    try:
        result = await collection.delete_one({"_id": ObjectId(paper_id)})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting paper {paper_id}: {e}")
        return False


async def count_papers(
    source: Optional[PaperSource] = None,
    status: Optional[PaperStatus] = None
) -> int:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["research_papers"]

    filter_dict = {}
    if source:
        filter_dict["source"] = source.value
    if status:
        filter_dict["status"] = status.value

    try:
        return await collection.count_documents(filter_dict)
    except Exception as e:
        logger.error(f"Error counting papers: {e}")
        return 0
