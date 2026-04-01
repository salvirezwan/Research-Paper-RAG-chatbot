from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from backend.core.config import settings
from backend.core.logging import logger

# Global MongoDB client and database instances
_client: AsyncIOMotorClient | None = None
_database = None


async def connect_to_mongodb() -> bool:
    """
    Initialize MongoDB connection.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global _client, _database

    try:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
            serverSelectionTimeoutMS=5000
        )

        await _client.admin.command('ping')

        _database = _client[settings.MONGODB_DATABASE_NAME]

        logger.info(f"Connected to MongoDB: {settings.MONGODB_DATABASE_NAME}")
        return True

    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error connecting to MongoDB: {e}")
        return False


async def close_mongodb_connection():
    global _client

    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_database():
    return _database


async def check_mongodb_health() -> bool:
    try:
        if _client is None:
            return False
        await _client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return False
