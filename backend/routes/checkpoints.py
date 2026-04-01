from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from backend.core.exceptions import DocumentNotFoundError
from backend.core.logging import logger
from backend.crud.checkpoint import (
    delete_checkpoint,
    delete_checkpoints_by_upload,
    get_all_checkpoints,
    get_checkpoint,
)
from backend.crud.uploaded_doc import get_paper_by_id
from backend.schemas.checkpoint_schema import CheckpointListResponse, CheckpointResponse

router = APIRouter(prefix="/api/v1/checkpoint", tags=["Checkpoints"])


@router.get("/upload/{paper_id}", response_model=CheckpointListResponse)
async def list_checkpoints(
    paper_id: str = Path(...),
    step: Optional[str] = Query(None, description="Filter by step name"),
):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    raw = await get_all_checkpoints(paper_id, step=step)

    checkpoints = [
        CheckpointResponse(
            checkpoint_id=cp["_id"],
            upload_id=cp["upload_id"],
            step=cp["step"],
            status=cp["status"],
            version=cp.get("version", 1),
            progress=cp.get("progress", {}),
            metadata=cp.get("metadata", {}),
            created_at=cp.get("metadata", {}).get("started_at"),
            last_updated=cp.get("metadata", {}).get("last_updated"),
        )
        for cp in raw
    ]

    logger.info(f"[CHECKPOINT API] {len(checkpoints)} checkpoints for paper_id={paper_id}")
    return CheckpointListResponse(
        upload_id=paper_id,
        checkpoints=checkpoints,
        total=len(checkpoints),
    )


@router.get("/upload/{paper_id}/step/{step}", response_model=CheckpointResponse)
async def get_checkpoint_by_step(
    paper_id: str = Path(...),
    step: str = Path(...),
):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    cp = await get_checkpoint(paper_id, step)
    if not cp:
        raise HTTPException(status_code=404, detail=f"No checkpoint found for step: {step}")

    return CheckpointResponse(
        checkpoint_id=cp["_id"],
        upload_id=cp["upload_id"],
        step=cp["step"],
        status=cp["status"],
        version=cp.get("version", 1),
        progress=cp.get("progress", {}),
        metadata=cp.get("metadata", {}),
        created_at=cp.get("metadata", {}).get("started_at"),
        last_updated=cp.get("metadata", {}).get("last_updated"),
    )


@router.delete("/upload/{paper_id}/step/{step}")
async def delete_specific_checkpoint(
    paper_id: str = Path(...),
    step: str = Path(...),
):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    success = await delete_checkpoint(paper_id, step)
    if not success:
        raise HTTPException(status_code=404, detail=f"No checkpoint found for step: {step}")

    return {"message": "Checkpoint deleted", "paper_id": paper_id, "step": step}


@router.delete("/upload/{paper_id}")
async def delete_all_checkpoints(
    paper_id: str = Path(...),
    steps: Optional[str] = Query(None, description="Comma-separated step names; omit for all"),
):
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise DocumentNotFoundError()

    step_list = [s.strip() for s in steps.split(",")] if steps else None
    result = await delete_checkpoints_by_upload(paper_id, steps=step_list)

    return {
        "message": "Checkpoints deleted",
        "paper_id": paper_id,
        "deleted_count": result["deleted_count"],
        "deleted_steps": result["deleted_steps"],
    }
