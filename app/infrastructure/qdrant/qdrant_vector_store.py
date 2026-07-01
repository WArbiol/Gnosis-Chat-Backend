import asyncio
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny
from app.application.interfaces.vector_store_gateway import VectorStoreGateway, ChunkResult
from app.core.config import settings

class QdrantVectorStore(VectorStoreGateway):
    """Implementação concreta do VectorStoreGateway utilizando o Qdrant."""

    def __init__(self) -> None:
        # Se houver API key, conecta no Cloud, senão local
        if settings.qdrant_api_key and settings.qdrant_cloud_url:
            self.client = QdrantClient(
                url=settings.qdrant_cloud_url,
                api_key=settings.qdrant_api_key
            )
        else:
            url_or_path = settings.qdrant_url
            if url_or_path and not url_or_path.startswith("http"):
                self.client = QdrantClient(path=url_or_path)
            else:
                self.client = QdrantClient(url=url_or_path)
            
        self.books_collection = settings.qdrant_collection_books
        self.interests_collection = settings.qdrant_collection_interests

    async def search_books(
        self,
        query_vector: list[float],
        limit: int = 30,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None
    ) -> list[ChunkResult]:
        # Rodar chamada síncrona do SDK do Qdrant no executor assíncrono
        loop = asyncio.get_running_loop()
        
        # 1. Construir filtros booleanos (payload)
        must_conditions = []
        
        if books:
            must_conditions.append(FieldCondition(key="metadata.book_name", match=MatchAny(any=books)))
        if authors:
            must_conditions.append(FieldCondition(key="metadata.author", match=MatchAny(any=authors)))
        if chamber_levels:
            must_conditions.append(FieldCondition(key="metadata.chamber", match=MatchAny(any=chamber_levels)))
        if chapters:
            must_conditions.append(FieldCondition(key="metadata.chapter", match=MatchAny(any=chapters)))

        qdrant_filter = Filter(must=must_conditions) if must_conditions else None

        # 2. Executar busca vetorial
        response = await loop.run_in_executor(
            None,
            lambda: self.client.search(
                collection_name=self.books_collection,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=limit
            )
        )

        # 3. Converter resultados para formato comum do domínio
        results: list[ChunkResult] = []
        for hit in response:
            meta = hit.payload.get("metadata") or {}
            # Fallback para o payload direto se não estiver aninhado
            book_name = meta.get("book_name") or hit.payload.get("book_name") or "Desconhecido"
            author = meta.get("author") or hit.payload.get("author") or "Desconhecido"
            page = meta.get("page") or hit.payload.get("page") or 1
            chamber = meta.get("chamber") or hit.payload.get("chamber") or 1
            chapter = meta.get("chapter") or hit.payload.get("chapter")
            text = hit.payload.get("text") or ""

            results.append({
                "text": text,
                "book_name": book_name,
                "author": author,
                "page": int(page),
                "chamber": int(chamber),
                "chapter": chapter,
                "score": float(hit.score)
            })
            
        return results

    async def search_user_interests(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int = 5
    ) -> list[ChunkResult]:
        loop = asyncio.get_running_loop()
        
        qdrant_filter = Filter(
            must=[
                FieldCondition(key="user_id", match=MatchAny(any=[user_id]))
            ]
        )
        
        response = await loop.run_in_executor(
            None,
            lambda: self.client.search(
                collection_name=self.interests_collection,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=limit
            )
        )
        
        results: list[ChunkResult] = []
        for hit in response:
            results.append({
                "text": hit.payload.get("interest_text", ""),
                "book_name": "Interesse do Usuário",
                "author": "N/A",
                "page": 1,
                "chamber": 1,
                "chapter": None,
                "score": float(hit.score)
            })
        return results

    async def upsert_user_interest(
        self,
        user_id: str,
        interest_text: str,
        vector: list[float]
    ) -> None:
        import uuid
        from qdrant_client.models import PointStruct
        
        loop = asyncio.get_running_loop()
        
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "user_id": user_id,
                "interest_text": interest_text
            }
        )
        
        await loop.run_in_executor(
            None,
            lambda: self.client.upsert(
                collection_name=self.interests_collection,
                points=[point]
            )
        )
