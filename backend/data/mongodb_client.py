from mongomock_motor import AsyncMongoMockClient
from backend.core.config import settings
from backend.core.logging import logger

_client = None
_database = None


async def connect_to_mongodb() -> bool:
    global _client, _database
    try:
        _client = AsyncMongoMockClient()
        _database = _client[settings.MONGODB_DATABASE_NAME]
        logger.info(f"In-memory MongoDB ready: {settings.MONGODB_DATABASE_NAME}")
        return True
    except Exception as e:
        logger.error(f"In-memory DB init error: {e}")
        return False


async def close_mongodb_connection():
    global _client
    _client = None


def get_database():
    return _database


async def check_mongodb_health() -> bool:
    return _database is not None
