import uuid
import re
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.rag.vectorstore.vector_schema import VectorMetadata
from backend.core.config import settings
from backend.core.logging import logger


class ChromaClient:
    def __init__(self):
        self.client = chromadb.EphemeralClient(
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection_name = settings.CHROMA_COLLECTION_NAME
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        try:
            collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection ready: {self.collection_name}")
            return collection
        except Exception as e:
            logger.error(f"Error getting/creating ChromaDB collection: {e}")
            raise

    def _sanitize_id_component(self, value: Any) -> str:
        if value is None:
            return ""
        sanitized = re.sub(r"[^\w\-_.]", "_", str(value).strip())
        return sanitized[:100]

    def _generate_point_id(self, metadata: Dict[str, Any], index: int) -> str:
        source_doc = self._sanitize_id_component(metadata.get("source_document", ""))
        chunk_idx = metadata.get("chunk_index", index)
        section_id = self._sanitize_id_component(metadata.get("section_id", ""))
        upload_id = self._sanitize_id_component(metadata.get("upload_id", ""))

        if upload_id:
            id_string = f"{source_doc}_{upload_id}_{chunk_idx}_{section_id}"
        else:
            id_string = f"{source_doc}_{chunk_idx}_{section_id}"

        try:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, id_string))
        except Exception as e:
            logger.warning(f"UUID5 generation failed for '{id_string}': {e}. Using UUID4.")
            return str(uuid.uuid4())

    def _build_chroma_metadata(self, metadata: Dict[str, Any]) -> dict:
        """Build a flat metadata dict with only scalar values (ChromaDB requirement)."""
        payload = {
            "source_document": str(metadata.get("source_document", "")),
            "source": str(metadata.get("source", "upload")),
            "chunk_index": int(metadata.get("chunk_index", 0)),
        }

        optional_str_fields = [
            "paper_title", "authors", "publication_year",
            "arxiv_id", "doi", "subject_areas",
            "section_id", "paragraph_ref", "upload_id",
        ]
        for field in optional_str_fields:
            if metadata.get(field):
                payload[field] = str(metadata[field])

        if metadata.get("page_number") is not None:
            payload["page_number"] = int(metadata["page_number"])

        if metadata.get("content"):
            payload["text"] = str(metadata["content"])

        return payload

    def insert(
        self,
        vector: List[float],
        metadata: VectorMetadata,
        point_id: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            if point_id is None:
                point_id = self._generate_point_id(metadata, 0)

            payload = self._build_chroma_metadata(metadata)
            document = payload.get("text", "")

            self.collection.upsert(
                ids=[point_id],
                embeddings=[vector],
                metadatas=[payload],
                documents=[document]
            )
            logger.debug(f"Inserted vector id={point_id}")
            return {"status": "ok", "id": point_id}

        except Exception as e:
            logger.error(f"Error inserting vector to ChromaDB: {e}", exc_info=True)
            raise

    def insert_batch(
        self,
        vectors: List[List[float]],
        metadata_list: List[VectorMetadata],
        point_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        try:
            if len(vectors) != len(metadata_list):
                raise ValueError(
                    f"Mismatch: {len(vectors)} vectors but {len(metadata_list)} metadata entries"
                )

            ids = []
            embeddings = []
            metadatas = []
            documents = []

            for i, (vector, metadata) in enumerate(zip(vectors, metadata_list)):
                try:
                    if point_ids and i < len(point_ids) and point_ids[i]:
                        point_id = point_ids[i]
                    else:
                        point_id = self._generate_point_id(metadata, i)

                    payload = self._build_chroma_metadata(metadata)
                    document = payload.get("text", "")

                    ids.append(point_id)
                    embeddings.append(vector)
                    metadatas.append(payload)
                    documents.append(document)

                except Exception as e:
                    logger.error(f"Error preparing chunk {i} for batch insert: {e}", exc_info=True)
                    continue

            if not ids:
                raise ValueError("No valid points to insert after processing metadata")

            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )

            logger.info(f"Successfully inserted {len(ids)} vectors to ChromaDB")
            return {"status": "ok", "points_count": len(ids)}

        except Exception as e:
            logger.error(f"Error batch inserting to ChromaDB: {e}", exc_info=True)
            raise

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        source: Optional[str] = None,
        publication_year: Optional[str] = None,
        upload_id: Optional[str] = None,
        upload_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            where = {}
            if source:
                where["source"] = {"$eq": source}
            if publication_year:
                where["publication_year"] = {"$eq": publication_year}
            if upload_ids and len(upload_ids) == 1:
                where["upload_id"] = {"$eq": upload_ids[0]}
            elif upload_ids:
                where["upload_id"] = {"$in": upload_ids}
            elif upload_id:
                where["upload_id"] = {"$eq": upload_id}

            query_kwargs: dict = {
                "query_embeddings": [query_vector],
                "n_results": top_k,
                "include": ["metadatas", "documents", "distances"],
            }
            if where:
                query_kwargs["where"] = where

            results = self.collection.query(**query_kwargs)

            formatted = []
            ids = results.get("ids", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for i, (doc_id, meta, dist) in enumerate(zip(ids, metadatas, distances)):
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # Convert to similarity score in [0, 1]
                score = 1.0 - (dist / 2.0)
                formatted.append({
                    "id": doc_id,
                    "score": score,
                    "text": meta.get("text", ""),
                    "source_document": meta.get("source_document", ""),
                    "paper_title": meta.get("paper_title"),
                    "authors": meta.get("authors"),
                    "source": meta.get("source", ""),
                    "publication_year": meta.get("publication_year"),
                    "arxiv_id": meta.get("arxiv_id"),
                    "doi": meta.get("doi"),
                    "section_id": meta.get("section_id"),
                    "page_number": meta.get("page_number"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "upload_id": meta.get("upload_id"),
                })

            return formatted

        except Exception as e:
            logger.error(f"Error searching ChromaDB: {e}", exc_info=True)
            return []

    def delete_by_document(self, source_document: str) -> Dict[str, Any]:
        try:
            self.collection.delete(where={"source_document": {"$eq": source_document}})
            logger.info(f"Deleted vectors for document: {source_document}")
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error deleting vectors for '{source_document}': {e}")
            raise

    def clear_collection(self) -> Dict[str, Any]:
        try:
            all_ids = self.collection.get(include=[])["ids"]
            if not all_ids:
                logger.info("ChromaDB collection is already empty")
                return {"status": "ok", "deleted_count": 0}

            batch_size = 1000
            total_deleted = 0
            for i in range(0, len(all_ids), batch_size):
                batch = all_ids[i : i + batch_size]
                self.collection.delete(ids=batch)
                total_deleted += len(batch)

            logger.info(f"Cleared {total_deleted} vectors from ChromaDB collection")
            return {"status": "ok", "deleted_count": total_deleted}

        except Exception as e:
            logger.error(f"Error clearing ChromaDB collection: {e}")
            raise


chroma_client = ChromaClient()
