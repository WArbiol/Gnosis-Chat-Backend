from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = "" # Required for HS256 verification

    # Qdrant
    qdrant_local_url: str = "http://localhost:6333"
    qdrant_cloud_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection_books: str = "gnosis_books"
    qdrant_collection_interests: str = "user_interests"

    # Google AI
    google_api_key: str = ""
    google_cloud_project: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_basic: str = ""
    stripe_price_premium: str = ""

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "gnosis-chat"

    # App
    app_env: str = "development"
    app_debug: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def qdrant_url(self) -> str:
        """Returns Qdrant Cloud URL in production, local Docker URL otherwise."""
        if self.is_production and self.qdrant_cloud_url:
            return self.qdrant_cloud_url
        return self.qdrant_local_url


settings = Settings()
