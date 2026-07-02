import os
from langchain_core.runnables import RunnableConfig

# Lazy cached singletons for dev/Studio environments
_llm = None
_vector_store = None
_reranker = None

def get_llm():
    global _llm
    if _llm is None:
        from app.infrastructure.google.gemini_llm import GeminiLLM
        _llm = GeminiLLM()
    return _llm

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore
        _vector_store = QdrantVectorStore()
    return _vector_store

def get_reranker():
    global _reranker
    if _reranker is None:
        from app.infrastructure.google.vertex_ranking import VertexRanking
        _reranker = VertexRanking()
    return _reranker

def get_configurable_llm(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    return configurable.get("llm") or get_llm()

def get_configurable_vector_store(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    return configurable.get("vector_store") or get_vector_store()

def get_configurable_reranker(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    return configurable.get("reranker") or get_reranker()
