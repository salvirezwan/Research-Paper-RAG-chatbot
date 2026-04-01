from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from backend.core.config import settings
from backend.core.logging import logger


def get_groq_chat_model(
    model_name: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set. Please add it to your .env file.")

    if model_name is None:
        model_name = settings.GROQ_MODEL
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE

    logger.debug(f"Creating Groq chat model: {model_name} (temp={temperature})")
    return ChatGroq(
        model=model_name,
        temperature=temperature,
        api_key=settings.GROQ_API_KEY,
        max_retries=3,
    )


def get_chat_model(
    model_name: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """
    Return a Groq-backed LangChain chat model.
    Single provider for this project; signature kept compatible with old project.
    """
    return get_groq_chat_model(model_name=model_name, temperature=temperature)
