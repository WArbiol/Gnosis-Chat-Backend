from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    import logging
    from app.agents.nodes.utils import get_llm, get_vector_store, get_reranker
    from app.agents.graph import compiled_graph
    
    logger = logging.getLogger("startup")
    logger.info("Iniciando o aquecimento (warm-up) das conexões...")
    
    # Isso forçará a inicialização do QdrantClient, Gemini e Vertex
    get_llm()
    get_vector_store()
    get_reranker()
    
    logger.info("Conexões aquecidas. LangGraph compilado e pronto para requisições.")
    yield
    logger.info("Encerrando recursos e conexões...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="gnosis-chat API",
        version="0.1.0",
        description="RAG-powered chat API over 90 gnostic PDFs",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
