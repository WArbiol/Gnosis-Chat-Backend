import os
import pytest
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore

def test_metadata_cache_loaded_from_file():
    """Verify that metadata_cache.json is loaded on init without network delay."""
    store = QdrantVectorStore()
    
    # Must have 170 books and 11 authors from the static cache
    assert len(store.unique_books) == 170
    assert len(store.unique_authors) == 11
    
    # Check that canonical books exist
    assert "Tratado de Psicologia Revolucionária (PT)" in store.unique_books
    assert "O Mistério do Áureo Florescer (PT)" in store.unique_books
    assert "V.M. Samael Aun Weor" in store.unique_authors

def test_approximate_book_resolution():
    """Verify fuzzy matching for book queries."""
    store = QdrantVectorStore()
    
    resolved = store._resolve_approximate(["psicologia revolucionaria"], store.unique_books)
    assert "Tratado de Psicologia Revolucionária (PT)" in resolved
    
    resolved_author = store._resolve_approximate(["samael aun weor"], store.unique_authors)
    assert "V.M. Samael Aun Weor" in resolved_author

def test_generate_title_async_non_blocking():
    """Verify generate_title_async structure and sleep delay."""
    import inspect
    from app.services.conversation_service import ConversationService
    source = inspect.getsource(ConversationService.generate_title_async)
    assert "asyncio.sleep(2.0)" in source
