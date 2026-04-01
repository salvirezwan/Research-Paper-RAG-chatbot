from sentence_transformers import SentenceTransformer
from backend.core.config import settings
from backend.core.logging import logger


_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.EMBED_MODEL_NAME}")
        _model = SentenceTransformer(settings.EMBED_MODEL_NAME)
        logger.info(f"Embedding model loaded (dim={settings.EMBED_DIMENSIONS})")
    return _model


def get_embedding(text: str) -> list[float]:
    model = _get_model()
    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise


def embed_text(text: str) -> list[float]:
    clean = text.strip()

    if not clean:
        return [0.0] * settings.EMBED_DIMENSIONS

    try:
        return get_embedding(clean)
    except Exception as e:
        logger.warning(f"Embedding failed, returning fallback zero vector: {e}")
        return [0.0] * settings.EMBED_DIMENSIONS
