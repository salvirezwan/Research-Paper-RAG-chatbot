from fastapi import APIRouter

from backend.data.mongodb_client import check_mongodb_health
from backend.core.config import settings

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health")
async def health_check():
    mongo_ok = await check_mongodb_health()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "mongodb": "connected" if mongo_ok else "disconnected",
    }
