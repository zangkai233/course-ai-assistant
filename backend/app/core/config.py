from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    app_name: str = "Course AI"
    app_env: str = "development"

    frontend_origin: str = "http://localhost:5173"

    # Database
    database_url: str

    db_pool_size: int = 5
    db_max_overflow: int = 5

    # Redis
    redis_url: str
    redis_max_connections: int = 100
    redis_pool_wait_seconds: float = 15

    # Rate limit
    rate_limit_per_minute: int = 10

    # LLM
    llm_base_url: str
    llm_chat_path: str = "/chat/completions"
    llm_api_key: str
    llm_model: str

    llm_timeout_seconds: int = 90
    llm_max_concurrency: int = 50
    llm_queue_wait_seconds: int = 15
    llm_lease_seconds: int = 120
    llm_max_retries: int = 2

    # RAG
    rag_enabled: bool = False

    embedding_base_url: str = ""
    embedding_path: str = "/embeddings"
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 1536

    rag_top_k: int = 5

    cache_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
