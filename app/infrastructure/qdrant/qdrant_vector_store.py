import asyncio
import unicodedata
from typing import Any
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny, Range
from app.application.interfaces.vector_store_gateway import VectorStoreGateway, ChunkResult
from app.core.config import settings

class QdrantVectorStore(VectorStoreGateway):
    """Implementação concreta do VectorStoreGateway utilizando o Qdrant."""

    def __init__(self) -> None:
        import os
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        
        # Se houver API key, conecta no Cloud, senão local
        if settings.qdrant_api_key and settings.qdrant_cloud_url:
            self.client = QdrantClient(
                url=settings.qdrant_cloud_url,
                api_key=settings.qdrant_api_key,
                timeout=20.0
            )
        else:
            url_or_path = settings.qdrant_url
            if url_or_path and not url_or_path.startswith("http"):
                if not os.path.isabs(url_or_path):
                    url_or_path = os.path.join(project_root, url_or_path)
                self.client = QdrantClient(path=url_or_path)
            else:
                self.client = QdrantClient(url=url_or_path)
            
        self.books_collection = settings.qdrant_collection_books
        self.interests_collection = settings.qdrant_collection_interests
        
        # Carregar acervo de livros e autores únicos para resolução dinâmica de filtros de forma preguiçosa (lazy)
        self.unique_books: list[str] = []
        self.unique_authors: list[str] = []
        self._cache_file = os.path.join(project_root, "data/metadata_cache.json")

    def _normalize_text(self, text: str) -> str:
        """Remove acentos, converte para minúsculas e remove espaços extras para correspondência difusa."""
        nfkd_form = unicodedata.normalize('NFKD', text)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower().strip()

    def _load_metadata_cache(self) -> None:
        """Carrega em cache todos os livros e autores únicos da base para resolução aproximada, usando um arquivo JSON como cache local."""
        import json
        import os
        
        # Se o cache em memória já estiver preenchido, evita retrabalho
        if self.unique_books and self.unique_authors:
            return
            
        # Tenta carregar do arquivo JSON local para evitar leitura pesada no Qdrant
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    self.unique_books = cached.get("books", [])
                    self.unique_authors = cached.get("authors", [])
                    if self.unique_books and self.unique_authors:
                        return
            except Exception:
                pass
                
        # Se não houver cache local ou estiver vazio, busca do Qdrant
        unique_books = set()
        unique_authors = set()
        offset = None
        
        try:
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
                    payload = p.payload or {}
                    meta = payload.get("metadata") or {}
                    
                    b = meta.get("book_name") or payload.get("book_name")
                    a = meta.get("author") or payload.get("author")
                    if b:
                        unique_books.add(b)
                    if a:
                        unique_authors.add(a)
                if not next_offset:
                    break
                offset = next_offset
                
            self.unique_books = list(unique_books)
            self.unique_authors = list(unique_authors)
            
            # Salva no arquivo JSON local para as próximas inicializações
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump({"books": self.unique_books, "authors": self.unique_authors}, f, ensure_ascii=False, indent=2)
                
        except Exception:
            # Fallback silencioso se o Qdrant local estiver bloqueado ou não inicializado
            pass

    def _resolve_approximate(self, inferred_items: list[str], unique_items: list[str]) -> list[str]:
        if not unique_items:
            return inferred_items
            
        stop_words = {
            "de", "do", "da", "dos", "das", "o", "a", "os", "as", 
            "um", "uma", "uns", "umas", "em", "no", "na", "nos", "nas", 
            "el", "la", "los", "las", "del", "al", "y", "e", "com", "con", 
            "para", "por", "sobre", "ao", "aos", "como", "libro", "livro"
        }
        
        resolved = []
        for ib in inferred_items:
            norm_ib = self._normalize_text(ib)
            if len(norm_ib) < 3:
                continue
                
            words_ib = set(w for w in norm_ib.split() if w not in stop_words)
            if not words_ib:
                words_ib = set(norm_ib.split())
                
            best_match = None
            best_score = 0.0
            
            # 1. Correspondência exata ou substring direta
            direct_matches = []
            for ub in unique_items:
                norm_ub = self._normalize_text(ub)
                if norm_ib in norm_ub or norm_ub in norm_ib:
                    direct_matches.append(ub)
            
            if direct_matches:
                resolved.extend(direct_matches)
                continue
                
            # 2. Correspondência aproximada por Jaccard e Overlap
            for ub in unique_items:
                norm_ub = self._normalize_text(ub)
                words_ub = set(w for w in norm_ub.split() if w not in stop_words)
                if not words_ub:
                    words_ub = set(norm_ub.split())
                    
                intersection = words_ib.intersection(words_ub)
                if intersection:
                    union = words_ib.union(words_ub)
                    jaccard = len(intersection) / len(union)
                    overlap_inferred = len(intersection) / len(words_ib)
                    overlap_db = len(intersection) / len(words_ub)
                    
                    score = max(jaccard, overlap_inferred * 0.8)
                    if (jaccard >= 0.4 or overlap_inferred >= 0.7 or overlap_db >= 0.7) and score > best_score:
                        best_score = score
                        best_match = ub
                        
            if best_match:
                resolved.append(best_match)
                
        return list(set(resolved)) if resolved else inferred_items

    def _resolve_books(self, inferred_books: list[str]) -> list[str]:
        self._load_metadata_cache()
        return self._resolve_approximate(inferred_books, self.unique_books)

    def _resolve_authors(self, inferred_authors: list[str]) -> list[str]:
        self._load_metadata_cache()
        return self._resolve_approximate(inferred_authors, self.unique_authors)

    def _build_qdrant_filter(
        self,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None,
        page_start: int | None = None,
        page_end: int | None = None
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
        if page_start is not None or page_end is not None:
            must_conditions.append(
                FieldCondition(
                    key="page",
                    range=Range(
                        gte=float(page_start) if page_start is not None else None,
                        lte=float(page_end) if page_end is not None else None
                    )
                )
            )
        return Filter(must=must_conditions) if must_conditions else None

    async def search_books(
        self,
        query_vector: list[float],
        limit: int = 30,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None,
        page_start: int | None = None,
        page_end: int | None = None
    ) -> list[ChunkResult]:
        loop = asyncio.get_running_loop()
        
        # 1. Resolver nomes de livros e autores aproximados para os valores exatos do banco
        resolved_books = self._resolve_books(books) if books else None
        resolved_authors = self._resolve_authors(authors) if authors else None

        async def _query_with_filter(q_filter: Filter | None) -> list[Any]:
            res = await loop.run_in_executor(
                None,
                lambda: self.client.query_points(
                    collection_name=self.books_collection,
                    query=query_vector,
                    query_filter=q_filter,
                    limit=limit
                )
            )
            return res.points

        # 2. Primeira tentativa: Busca estrita (todos os filtros aplicados)
        q_filter = self._build_qdrant_filter(resolved_books, resolved_authors, chamber_levels, chapters, page_start, page_end)
        response = await _query_with_filter(q_filter)

        # 3. Fallback 1: Se deu vazio e havia filtro de capítulo, relaxa removendo capítulo
        if not response and chapters:
            q_filter = self._build_qdrant_filter(resolved_books, resolved_authors, chamber_levels, None, page_start, page_end)
            response = await _query_with_filter(q_filter)

        # 4. Fallback 2: Se deu vazio e havia filtro de página, relaxa removendo página
        if not response and (page_start is not None or page_end is not None):
            q_filter = self._build_qdrant_filter(resolved_books, resolved_authors, chamber_levels, None, None, None)
            response = await _query_with_filter(q_filter)

        # 5. Fallback 3: Se ainda deu vazio, relaxa removendo filtros de livros/autores (mantém apenas chamber_levels para segurança)
        if not response and (resolved_books or resolved_authors):
            q_filter = self._build_qdrant_filter(None, None, chamber_levels, None, None, None)
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
            lambda: self.client.query_points(
                collection_name=self.interests_collection,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=limit
            )
        )
        
        results: list[ChunkResult] = []
        for hit in response.points:
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
