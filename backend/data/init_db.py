from backend.data.mongodb_client import connect_to_mongodb, get_database, check_mongodb_health
from backend.core.logging import logger


async def init_database() -> bool:
    if not await connect_to_mongodb():
        logger.error("Failed to connect to MongoDB")
        return False

    database = get_database()
    if database is None:
        logger.error("Database instance not available")
        return False

    try:
        # research_papers collection indexes
        papers = database["research_papers"]

        await papers.create_index("file_hash", unique=True)
        await papers.create_index("source")
        await papers.create_index("status")
        await papers.create_index("arxiv_id", sparse=True)
        await papers.create_index("doi", sparse=True)
        await papers.create_index("publication_year")
        await papers.create_index([("uploaded_at", -1)])

        logger.info("Created indexes for research_papers collection")

        # request_logs collection indexes
        request_logs = database["request_logs"]

        await request_logs.create_index([("timestamp", -1)])
        await request_logs.create_index("response_time")
        await request_logs.create_index("endpoint")

        logger.info("Created indexes for request_logs collection")

        # ingestion_checkpoints collection indexes
        checkpoints = database["ingestion_checkpoints"]

        await checkpoints.create_index([("upload_id", 1), ("step", 1)])
        await checkpoints.create_index("status")
        await checkpoints.create_index([("metadata.started_at", -1)])

        logger.info("Created indexes for ingestion_checkpoints collection")

        if await check_mongodb_health():
            logger.info("Database initialized successfully")
            return True
        else:
            logger.error("Database health check failed after init")
            return False

    except Exception as e:
        logger.error(f"Error initializing database indexes: {e}")
        return False
