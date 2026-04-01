import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings
from backend.core.exceptions import global_exception_handler
from backend.core.logging import logger
from backend.crud.request_log import create_request_log
from backend.data.init_db import init_database
from backend.data.mongodb_client import close_mongodb_connection
from backend.routes.chat import router as chat_router
from backend.routes.checkpoints import router as checkpoints_router
from backend.routes.health import router as health_router
from backend.routes.papers import router as papers_router
from backend.routes.upload import router as upload_router


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        endpoint = request.url.path
        status_code = 200
        error_type = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            status_code = 500
            error_type = type(exc).__name__
            raise
        finally:
            response_time = time.time() - start_time
            if endpoint.startswith("/api/"):
                try:
                    await create_request_log(
                        response_time=response_time,
                        endpoint=endpoint,
                        status_code=status_code,
                        error_type=error_type,
                    )
                except Exception as exc:
                    logger.error(f"Failed to log request to MongoDB: {exc}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    debug=settings.APP_DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(papers_router)
app.include_router(checkpoints_router)

app.add_exception_handler(Exception, global_exception_handler)


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.APP_NAME}...")
    success = await init_database()
    if not success:
        logger.error("Database initialisation failed — continuing without MongoDB")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down...")
    await close_mongodb_connection()


@app.get("/")
async def root():
    return {"message": f"{settings.APP_NAME} is running!"}
