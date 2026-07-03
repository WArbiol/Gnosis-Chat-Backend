import asyncio
import unicodedata
from typing import Any
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
        
        # Carregar acervo de livros e autores únicos para resolução dinâmica de filtros
        self.unique_books: list[str] = []
        self.unique_authors: list[str] = []
        try:
            self._load_metadata_cache()
        except Exception:
            # Fallback silencioso se o banco estiver vazio ou indisponível na inicialização
            pass

    def _normalize_text(self, text: str) -> str:
        """Remove acentos, converte para minúsculas e remove espaços extras para correspondência difusa."""
        nfkd_form = unicodedata.normalize('NFKD', text)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower().strip()

    def _load_metadata_cache(self) -> None:
        """Carrega em cache todos os livros e autores únicos da base para resolução aproximada."""
        unique_books = set()
        unique_authors = set()
        offset = None
        
        while True:
            response = self.client.scroll(
                collection_name=self.books_collection,
                limit=2000,
                offset=offset,
                with_payload=["book_name", "author"],
                with_vectors=False
            )
            points, next_offset = response
            for p in points:
                b = p.payload.get("book_name")
                a = p.payload.get("author")
                if b:
                    unique_books.add(b)
                if a:
                    unique_authors.add(a)
            if not next_offset:
                break
            offset = next_offset
            
        self.unique_books = list(unique_books)
        self.unique_authors = list(unique_authors)

    def _resolve_books(self, inferred_books: list[str]) -> list[str]:
        if not self.unique_books:
            return inferred_books
        resolved = []
        for ib in inferred_books:
            norm_ib = self._normalize_text(ib)
            for ub in self.unique_books:
                norm_ub = self._normalize_text(ub)
                # Verifica se o termo inferido é substring do livro do DB ou vice-versa
                if norm_ib in norm_ub or norm_ub in norm_ib:
                    resolved.append(ub)
        return list(set(resolved)) if resolved else inferred_books

    def _resolve_authors(self, inferred_authors: list[str]) -> list[str]:
        if not self.unique_authors:
            return inferred_authors
        resolved = []
        for ia in inferred_authors:
            norm_ia = self._normalize_text(ia)
            for ua in self.unique_authors:
                norm_ua = self._normalize_text(ua)
                if norm_ia in norm_ua or norm_ua in norm_ia:
                    resolved.append(ua)
        return list(set(resolved)) if resolved else inferred_authors

    def _build_qdrant_filter(
        self,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None
    ) -> Filter | None:
        must_conditions = []
        if books:
            must_conditions.append(FieldCondition(key="book_name", match=MatchAny(any=books)))
        if authors:
            must_conditions.append(FieldCondition(key="author", match=MatchAny(any=authors)))
        if chamber_levels:
            must_conditions.append(FieldCondition(key="chamber", match=MatchAny(any=chamber_levels)))
        if chapters:
            must_conditions.append(FieldCondition(key="chapter", match=MatchAny(any=chapters)))
        return Filter(must=must_conditions) if must_conditions else None

    async def search_books(
        self,
        query_vector: list[float],
        limit: int = 30,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None
    ) -> list[ChunkResult]:
        loop = asyncio.get_running_loop()
        
        # 1. Resolver nomes de livros e autores aproximados para os valores exatos do banco
        resolved_books = self._resolve_books(books) if books else None
        resolved_authors = self._resolve_authors(authors) if authors else None

        async def _query_with_filter(q_filter: Filter | None) -> list[Any]:
            return await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    collection_name=self.books_collection,
                    query_vector=query_vector,
                    query_filter=q_filter,
                    limit=limit
                )
            )

        # 2. Primeira tentativa: Busca estrita (todos os filtros aplicados)
        q_filter = self._build_qdrant_filter(resolved_books, resolved_authors, chamber_levels, chapters)
        response = await _query_with_filter(q_filter)

        # 3. Fallback 1: Se deu vazio e havia filtro de capítulo, relaxa removendo capítulo
        if not response and chapters:
            q_filter = self._build_qdrant_filter(resolved_books, resolved_authors, chamber_levels, None)
            response = await _query_with_filter(q_filter)

        # 4. Fallback 2: Se ainda deu vazio, relaxa removendo filtros de livros/autores (mantém apenas chamber_levels para segurança)
        if not response and (resolved_books or resolved_authors):
            q_filter = self._build_qdrant_filter(None, None, chamber_levels, None)
            response = await _query_with_filter(q_filter)

        # 5. Converter resultados para formato comum do domínio
        results: list[ChunkResult] = []
        for hit in response:
            meta = hit.payload.get("metadata") or {}
            book_name = meta.get("book_name") or hit.payload.get("book_name") or "Desconhecido"
            author = meta.get("author") or hit.payload.get("author") or "Desconhecido"
            page = meta.get("page") or hit.payload.get("page") or 1
            chamber = meta.get("chamber") or hit.payload.get("chamber") or 1
            chapter = meta.get("chapter") or hit.payload.get("chapter")
            
            # Recuperar texto do payload ou do _node_content (LlamaIndex)
            text = hit.payload.get("text")
            if not text and "_node_content" in hit.payload:
                try:
                    import json
                    node_data = json.loads(hit.payload["_node_content"])
                    text = node_data.get("text")
                except Exception:
                    pass
            if not text:
                text = ""

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
