from typing import Optional, List
from datetime import datetime, timedelta
from backend.data.mongodb_client import get_database
from backend.models.request_log import RequestLog
from backend.core.logging import logger


async def create_request_log(
    response_time: float,
    endpoint: Optional[str] = None,
    status_code: Optional[int] = None,
    error_type: Optional[str] = None
) -> RequestLog:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["request_logs"]

    log = RequestLog(
        response_time=response_time,
        endpoint=endpoint,
        status_code=status_code,
        error_type=error_type
    )

    try:
        result = await collection.insert_one(log.to_mongo())
        log.id = result.inserted_id
        return log
    except Exception as e:
        logger.error(f"Error creating request log: {e}")
        raise


async def get_all_logs(
    limit: int = 100,
    offset: int = 0,
    endpoint: Optional[str] = None
) -> List[RequestLog]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["request_logs"]

    filter_dict = {}
    if endpoint:
        filter_dict["endpoint"] = endpoint

    try:
        cursor = collection.find(filter_dict).sort("timestamp", -1).skip(offset).limit(limit)
        logs = []
        async for log in cursor:
            logs.append(RequestLog.from_mongo(log))
        return logs
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        return []


async def get_logs_by_time_range(
    start_time: datetime,
    end_time: datetime,
    limit: int = 1000
) -> List[RequestLog]:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["request_logs"]

    try:
        cursor = collection.find({
            "timestamp": {"$gte": start_time, "$lte": end_time}
        }).sort("timestamp", -1).limit(limit)

        logs = []
        async for log in cursor:
            logs.append(RequestLog.from_mongo(log))
        return logs
    except Exception as e:
        logger.error(f"Error getting logs by time range: {e}")
        return []


async def delete_old_logs(retention_days: int = 30) -> int:
    database = get_database()
    if database is None:
        raise RuntimeError("Database not initialized")

    collection = database["request_logs"]

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    try:
        result = await collection.delete_many({"timestamp": {"$lt": cutoff_date}})
        logger.info(f"Deleted {result.deleted_count} old log entries")
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error deleting old logs: {e}")
        return 0
