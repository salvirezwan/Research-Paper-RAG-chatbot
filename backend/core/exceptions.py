from fastapi.responses import JSONResponse
from fastapi import Request


class BaseAppException(Exception):
    status_code = 500
    message = "An error occurred"

    def __init__(self, message: str = None):
        self.message = message or self.message
        super().__init__(self.message)


class InvalidFileTypeError(BaseAppException):
    status_code = 415
    message = "Invalid file type. Only PDF files are allowed."


class FileSizeExceededError(BaseAppException):
    status_code = 400
    message = "File size exceeds maximum allowed size."


class DuplicateDocumentError(BaseAppException):
    status_code = 409
    message = "Document with this file hash already exists."


class ProcessingError(BaseAppException):
    status_code = 500
    message = "Document processing failed."


class ParsingError(BaseAppException):
    status_code = 500
    message = "PDF parsing failed."


class IndexingError(BaseAppException):
    status_code = 500
    message = "Indexing to vector database failed."


class EmbeddingError(BaseAppException):
    status_code = 500
    message = "Embedding generation failed."


class DocumentNotFoundError(BaseAppException):
    status_code = 404
    message = "Document not found."


class PaperFetchError(BaseAppException):
    status_code = 502
    message = "Failed to fetch paper from external source."


async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, BaseAppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
            }
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "details": str(exc) if request.app.debug else "An unexpected error occurred",
        }
    )
