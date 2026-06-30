"""PDF Ingestion Script — gnosis_books collection.

Loads chunked JSONs from backend/data/chunks, generates embeddings 
via Google gemini-embedding-001, and upserts into Qdrant "gnosis_books".
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.google import GooglePaLMEmbedding
from qdrant_client import QdrantClient
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "chunks"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
COLLECTION_NAME = "gnosis_books"

async def ingest_chunks(chunk_files: List[Path]):
    """Embed and upsert chunks from JSON files to Qdrant."""
    
    # 1. Initialize Qdrant Client
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    # 2. Initialize Vector Store
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # 3. Initialize Embedding Model (gemini-embedding-001 via GooglePaLMEmbedding/Gemini)
    # LlamaIndex now uses GoogleGeminiEmbedding for newer models, but let's stick to what's stable
    # The ADR says gemini-embedding-001. 
    from llama_index.embeddings.google import GeminiEmbedding
    embed_model = GeminiEmbedding(model_name="models/embedding-001", api_key=GOOGLE_API_KEY)
    
    documents = []
    
    print(f"-> Carregando {len(chunk_files)} arquivos de chunks...")
    
    for chunk_file in chunk_files:
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)
            
        for item in chunks_data:
            doc = Document(
                text=item["text"],
                metadata=item["metadata"]
            )
            # Ensure metadata values are string/float/int/bool for Qdrant
            documents.append(doc)
            
    print(f"-> Criando índice e enviando {len(documents)} vetores para o Qdrant...")
    
    # 4. Create Index (this will trigger embedding and upsert)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True
    )
    
    print(f"-> Sucesso! Dados ingeridos na coleção '{COLLECTION_NAME}'.")

async def main():
    if not GOOGLE_API_KEY:
        print("Erro: GOOGLE_API_KEY não encontrada no .env")
        return

    chunk_files = list(CHUNKS_DIR.glob("*_chunks.json"))
    
    if not chunk_files:
        print(f"Nenhum arquivo de chunks encontrado em {CHUNKS_DIR}")
        return
        
    await ingest_chunks(chunk_files)

if __name__ == "__main__":
    asyncio.run(main())
