import os
import hashlib
import tempfile
from pathlib import Path

from backend.core.config import settings
from backend.core.logging import logger


def ensure_upload_directory(source: str = "upload") -> Path:
    base_dir = Path(settings.UPLOAD_DIR)
    dir_path = base_dir / source
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def save_uploaded_file(
    file_content: bytes,
    filename: str,
    source: str = "upload",
) -> str:
    dir_path = ensure_upload_directory(source)
    safe_filename = sanitize_filename(filename)
    file_path = dir_path / safe_filename

    with open(file_path, "wb") as f:
        f.write(file_content)

    logger.info(f"Saved uploaded file: {file_path}")
    return str(file_path)


def get_file_hash_from_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def get_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            sha256.update(block)
    return sha256.hexdigest()


def delete_uploaded_file(file_path: str) -> bool:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def sanitize_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        filename = filename.replace(char, '_')
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    return filename


def save_temp_file(content: bytes, suffix: str = ".pdf") -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        return tmp.name
