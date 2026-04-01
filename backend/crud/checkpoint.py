from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone
from backend.data.mongodb_client import get_database
from backend.core.logging import logger


async def _get_latest_checkpoint(upload_id: str, step: str) -> Optional[Dict[str, Any]]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    try:
        cursor = collection.find({
            "upload_id": upload_id,
            "step": step,
            "status": {"$ne": "archived"}
        }).sort("version", -1).limit(1)

        doc = await cursor.to_list(length=1)
        if doc and len(doc) > 0:
            doc[0]["_id"] = str(doc[0]["_id"])
            return doc[0]
        return None
    except Exception as e:
        logger.error(f"Error getting latest checkpoint: {e}")
        return None


async def create_checkpoint(
    upload_id: str,
    step: str,
    initial_data: Dict[str, Any],
    status: str = "in_progress",
    version: int = 1
) -> ObjectId:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    checkpoint_doc = {
        "upload_id": upload_id,
        "step": step,
        "status": status,
        "version": version,
        "progress": {
            "total_items": 0,
            "processed_items": 0,
            "failed_items": 0,
            "last_processed_index": -1
        },
        "data": initial_data,
        "metadata": {
            "started_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc),
            "completed_at": None,
            "error_message": None,
            "retention_policy": "keep_forever",
            "expires_at": None
        },
        "dependencies": {
            "requires_steps": [],
            "depends_on_checkpoint_ids": []
        },
        "resume_info": {
            "can_resume": False,
            "resume_from_index": 0,
            "missing_items": []
        }
    }

    try:
        result = await collection.insert_one(checkpoint_doc)
        logger.info(
            f"[CHECKPOINT] Created checkpoint for upload_id={upload_id}, "
            f"step={step}, status={status}, version={version}"
        )
        return result.inserted_id
    except Exception as e:
        logger.error(
            f"[CHECKPOINT] Error creating checkpoint for upload_id={upload_id}, step={step}: {e}"
        )
        raise


async def get_checkpoint(upload_id: str, step: str) -> Optional[Dict[str, Any]]:
    return await _get_latest_checkpoint(upload_id, step)


async def get_all_checkpoints(upload_id: str, step: Optional[str] = None) -> List[Dict[str, Any]]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    filter_dict = {
        "upload_id": upload_id,
        "status": {"$ne": "archived"}
    }

    if step:
        filter_dict["step"] = step

    try:
        cursor = collection.find(filter_dict).sort([("step", 1), ("version", -1)])
        checkpoints = []
        seen_steps = set()

        async for doc in cursor:
            if doc["step"] not in seen_steps:
                doc["_id"] = str(doc["_id"])
                checkpoints.append(doc)
                seen_steps.add(doc["step"])

        return checkpoints
    except Exception as e:
        logger.error(f"Error getting all checkpoints: {e}")
        return []


async def update_checkpoint_progress(
    upload_id: str,
    step: str,
    progress_data: Dict[str, Any]
) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    update_data = {
        "progress": progress_data,
        "metadata.last_updated": datetime.now(timezone.utc)
    }

    try:
        latest = await _get_latest_checkpoint(upload_id, step)
        if not latest:
            logger.warning(
                f"[CHECKPOINT] Cannot update progress: checkpoint not found "
                f"for upload_id={upload_id}, step={step}"
            )
            return False

        result = await collection.update_one(
            {"_id": ObjectId(latest["_id"])},
            {"$set": update_data}
        )

        processed = progress_data.get("processed_items", 0)
        total = progress_data.get("total_items", 0)
        percentage = (processed / total * 100) if total > 0 else 0

        if result.modified_count > 0:
            logger.info(
                f"[CHECKPOINT] Updated progress for upload_id={upload_id}, step={step}: "
                f"{processed}/{total} ({percentage:.1f}%)"
            )

        return result.modified_count > 0
    except Exception as e:
        logger.error(
            f"[CHECKPOINT] Error updating checkpoint progress for upload_id={upload_id}, step={step}: {e}"
        )
        return False


async def save_step_data(
    upload_id: str,
    step: str,
    data: Dict[str, Any]
) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    update_data = {
        "data": data,
        "metadata.last_updated": datetime.now(timezone.utc)
    }

    try:
        latest = await _get_latest_checkpoint(upload_id, step)
        if not latest:
            return False

        result = await collection.update_one(
            {"_id": ObjectId(latest["_id"])},
            {"$set": update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error saving step data: {e}")
        return False


async def mark_step_completed(upload_id: str, step: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    update_data = {
        "status": "completed",
        "metadata.completed_at": datetime.now(timezone.utc),
        "metadata.last_updated": datetime.now(timezone.utc),
        "resume_info.can_resume": False
    }

    try:
        latest = await _get_latest_checkpoint(upload_id, step)
        if not latest:
            logger.warning(
                f"[CHECKPOINT] Cannot mark completed: checkpoint not found "
                f"for upload_id={upload_id}, step={step}"
            )
            return False

        result = await collection.update_one(
            {"_id": ObjectId(latest["_id"])},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            logger.info(f"[CHECKPOINT] Marked step as completed: upload_id={upload_id}, step={step}")

        return result.modified_count > 0
    except Exception as e:
        logger.error(
            f"[CHECKPOINT] Error marking step completed for upload_id={upload_id}, step={step}: {e}"
        )
        return False


async def mark_step_failed(upload_id: str, step: str, error_message: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    update_data = {
        "status": "failed",
        "metadata.error_message": error_message,
        "metadata.last_updated": datetime.now(timezone.utc),
        "resume_info.can_resume": True
    }

    try:
        latest = await _get_latest_checkpoint(upload_id, step)
        if not latest:
            logger.warning(
                f"[CHECKPOINT] Cannot mark failed: checkpoint not found "
                f"for upload_id={upload_id}, step={step}"
            )
            return False

        result = await collection.update_one(
            {"_id": ObjectId(latest["_id"])},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            logger.error(
                f"[CHECKPOINT] Marked step as failed: upload_id={upload_id}, "
                f"step={step}, error={error_message[:100]}"
            )

        return result.modified_count > 0
    except Exception as e:
        logger.error(
            f"[CHECKPOINT] Error marking step failed for upload_id={upload_id}, step={step}: {e}"
        )
        return False


async def delete_checkpoint(upload_id: str, step: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    try:
        result = await collection.delete_many({
            "upload_id": upload_id,
            "step": step
        })
        if result.deleted_count > 0:
            logger.info(
                f"[CHECKPOINT] Deleted checkpoint: upload_id={upload_id}, "
                f"step={step}, count={result.deleted_count}"
            )
        return result.deleted_count > 0
    except Exception as e:
        logger.error(
            f"[CHECKPOINT] Error deleting checkpoint for upload_id={upload_id}, step={step}: {e}"
        )
        return False


async def delete_checkpoints_by_upload(
    upload_id: str,
    steps: Optional[List[str]] = None
) -> Dict[str, Any]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    filter_dict = {"upload_id": upload_id}

    if steps:
        filter_dict["step"] = {"$in": steps}

    try:
        result = await collection.delete_many(filter_dict)
        return {
            "deleted_count": result.deleted_count,
            "deleted_steps": steps if steps else "all"
        }
    except Exception as e:
        logger.error(f"Error deleting checkpoints: {e}")
        return {"deleted_count": 0, "deleted_steps": []}


async def archive_checkpoint(upload_id: str, step: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    try:
        latest = await _get_latest_checkpoint(upload_id, step)
        if not latest:
            return False

        result = await collection.update_one(
            {"_id": ObjectId(latest["_id"])},
            {"$set": {"status": "archived", "metadata.last_updated": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error archiving checkpoint: {e}")
        return False


async def restore_checkpoint(upload_id: str, step: str) -> bool:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["ingestion_checkpoints"]

    try:
        cursor = collection.find({
            "upload_id": upload_id,
            "step": step,
            "status": "archived"
        }).sort("version", -1).limit(1)

        doc = await cursor.to_list(length=1)
        if not doc or len(doc) == 0:
            return False

        result = await collection.update_one(
            {"_id": doc[0]["_id"]},
            {"$set": {"status": "completed", "metadata.last_updated": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error restoring checkpoint: {e}")
        return False
