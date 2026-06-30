import asyncio
from typing import Any
from app.agents.state import GraphState, ResearchResult
from app.application.interfaces.llm_gateway import LLMGateway
from app.application.interfaces.vector_store_gateway import VectorStoreGateway
from app.application.interfaces.reranker_gateway import RerankerGateway
from app.schemas.conversation import CitationResponse

async def transform_query(llm: LLMGateway, query: str) -> str:
    """Melhora a query original usando sinônimos e expansão para otimizar busca vetorial."""
    prompt = (
        "Reescreva a seguinte consulta gnóstica para torná-la mais propensa a encontrar correspondências "
        "relevantes em uma busca vetorial de livros. Adicione sinônimos e termos relacionados usados em gnosticismo, "
        "sem alterar o significado original.\n"
        f"Consulta original: {query}\n"
        "Retorne apenas a consulta reformulada final, sem explicações."
    )
    return await llm.generate_text(
        prompt=prompt,
        temperature=0.3,
        use_premium_model=False # Lite (Flash 3.0 Lite)
    )

async def process_single_query(
    sub_query: str,
    metadata_filters: dict[str, Any],
    llm: LLMGateway,
    vector_store: VectorStoreGateway,
    reranker: RerankerGateway
) -> ResearchResult:
    """Processa uma única sub-query: transform, embed, retrieval e re-rank."""
    # 1. Query Transformation
    transformed = await transform_query(llm, sub_query)

    # 2. Embedding Generation
    vector = await llm.generate_embeddings(transformed)

    # 3. Vector Database Retrieval (busca até 30 chunks)
    raw_chunks = await vector_store.search_books(
        query_vector=vector,
        limit=30,
        books=metadata_filters.get("books"),
        authors=metadata_filters.get("authors"),
        chamber_levels=metadata_filters.get("chamber_levels"),
        chapters=metadata_filters.get("chapters")
    )

    if not raw_chunks:
        return {
            "sub_query": sub_query,
            "chunks": [],
            "citations": [],
            "relevance_scores": []
        }

    # 4. Cross-Encoder Re-Ranking (Vertex AI) -> seleciona top 10
    ranked_chunks = await reranker.rerank(
        query=sub_query,
        documents=raw_chunks,
        top_n=10
    )

    # Mapear chunks reordenados
    chunks: list[str] = []
    citations: list[CitationResponse] = []
    scores: list[float] = []

    for item in ranked_chunks:
        chunks.append(item["text"])
        citations.append(
            CitationResponse(
                book_name=item["book_name"],
                author=item["author"],
                page=item["page"],
                chamber=item["chamber"],
                chapter=item["chapter"]
            )
        )
        scores.append(item["score"])

    return {
        "sub_query": sub_query,
        "chunks": chunks,
        "citations": citations,
        "relevance_scores": scores
    }

from langchain_core.runnables import RunnableConfig

async def researcher_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Researcher executando buscas paralelas em lote para todas as sub-queries."""
    llm: LLMGateway = config["configurable"]["llm"]
    vector_store: VectorStoreGateway = config["configurable"]["vector_store"]
    reranker: RerankerGateway = config["configurable"]["reranker"]

    sub_queries = state.get("sub_queries") or [state.get("query", "")]
    metadata_filters = state.get("metadata_filters") or {}
    counters = state.get("session_counters")

    # 1. Executar todas as pesquisas de forma assíncrona concorrente (máx. 6)
    tasks = [
        process_single_query(sq, metadata_filters, llm, vector_store, reranker)
        for sq in sub_queries[:6] # Limite de segurança de 6 sub-queries paralelas
    ]
    
    results = await asyncio.gather(*tasks)

    # 2. Incrementar contador de chamadas
    if counters:
        counters["researcher_calls"] += 1

    return {
        "research_results": results,
        "session_counters": counters
    }
