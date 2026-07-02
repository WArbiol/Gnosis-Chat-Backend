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

# Eagerly initialized singletons at startup to prevent blockbuster
# from flagging instantiation blocking I/O (like QdrantClient local database lock)
# when run inside the async event loop tasks.
_llm = GeminiLLM()
_vector_store = QdrantVectorStore()
_reranker = VertexRanking()

def get_llm():
    return _llm

def get_vector_store():
    return _vector_store

def get_reranker():
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
