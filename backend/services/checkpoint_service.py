from typing import Optional, Dict, Any

from backend.crud.checkpoint import get_checkpoint
from backend.core.logging import logger


async def get_resume_info(upload_id: str, step: str) -> Optional[Dict[str, Any]]:
    """
    Return resume metadata for an in-progress ingestion step.

    Returns None if no checkpoint exists for the step.
    """
    checkpoint = await get_checkpoint(upload_id, step)
    if not checkpoint:
        return None

    progress = checkpoint.get("progress", {})
    resume_info = checkpoint.get("resume_info", {})

    last_index = progress.get("last_processed_index", -1)
    can_resume = (
        resume_info.get("can_resume", False)
        and checkpoint.get("status") not in ("completed", "archived")
    )

    logger.debug(
        f"[CHECKPOINT_SERVICE] resume_info for upload_id={upload_id}, step={step}: "
        f"can_resume={can_resume}, resume_from={last_index + 1}"
    )

    return {
        "can_resume": can_resume,
        "resume_from_index": last_index + 1,
        "processed_items": progress.get("processed_items", 0),
        "total_items": progress.get("total_items", 0),
    }


async def get_checkpoint_data(upload_id: str, step: str) -> Optional[Dict[str, Any]]:
    """Return the raw data dict saved for a checkpoint step."""
    checkpoint = await get_checkpoint(upload_id, step)
    if not checkpoint:
        return None
    return checkpoint.get("data")
