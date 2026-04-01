from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # App
    APP_ENV: str = Field(default="development")
    APP_NAME: str = Field(default="Academic_Research_RAG")
    APP_DEBUG: bool = Field(default=True)

    # Server
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    API_VERSION: str = Field(default="v1")

    # Groq LLM
    GROQ_API_KEY: str = Field(default="")
    GROQ_MODEL: str = Field(default="llama-3.1-70b-versatile")
    LLM_TEMPERATURE: float = Field(default=0.0)

    # Embeddings (local, sentence-transformers)
    EMBED_MODEL_NAME: str = Field(default="BAAI/bge-base-en-v1.5")
    EMBED_DIMENSIONS: int = Field(default=768)

    # ChromaDB
    CHROMA_PERSIST_PATH: str = Field(default="./data/chroma_db")
    CHROMA_COLLECTION_NAME: str = Field(default="research_papers")

    # MongoDB
    MONGODB_URL: str = Field(default="mongodb://localhost:27017")
    MONGODB_DATABASE_NAME: str = Field(default="academic_research_rag")
    MONGODB_MAX_POOL_SIZE: int = Field(default=100)

    # External APIs
    SEMANTIC_SCHOLAR_API_KEY: str = Field(default="")
    ARXIV_MAX_RESULTS: int = Field(default=5)

    # Upload
    SECRET_KEY: str = Field(default="mock_secret_key")
    UPLOAD_DIR: str = Field(default="uploads/documents")
    MAX_FILE_SIZE: int = Field(default=50 * 1024 * 1024)
    ALLOWED_FILE_TYPES: list[str] = Field(default=["application/pdf"])

    # Chunking
    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=200)

    # Streamlit
    STREAMLIT_PORT: int = Field(default=8501)


settings = Settings()
