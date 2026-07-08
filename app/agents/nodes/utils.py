import os
import tempfile
from langchain_core.runnables import RunnableConfig

# Pre-set tempfile.tempdir to bypass tempfile calling os.getcwd() under blockbuster
# when importing portalocker (used by qdrant_client).
if tempfile.tempdir is None:
    tempfile.tempdir = "/tmp" if os.name != "nt" else os.environ.get("TEMP", "C:\\Temp")

from app.infrastructure.google.gemini_llm import GeminiLLM
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore
from app.infrastructure.google.vertex_ranking import VertexRanking

_llm = None
_vector_store = None
_reranker = None

def get_llm():
    global _llm
    if _llm is None:
        _llm = GeminiLLM()
    return _llm

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store

def get_reranker():
    global _reranker
    if _reranker is None:
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

def get_configurable_database(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    return configurable.get("database")
