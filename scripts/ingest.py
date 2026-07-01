"""PDF Ingestion Script — gnosis_books collection.

Loads chunked JSONs from backend/data/chunks, generates embeddings 
via Google gemini-embedding-2-preview, and upserts into Qdrant "gnosis_books"
with persistent checkpoints.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "chunks"
CHECKPOINT_FILE = BASE_DIR / "data" / "ingest_checkpoint.json"

QDRANT_CLOUD_URL = os.getenv("QDRANT_CLOUD_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_LOCAL_URL = os.getenv("QDRANT_LOCAL_URL", "http://localhost:6333")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
COLLECTION_NAME = "gnosis_books"

# Resolve a URL do Qdrant baseada no cenário (Cloud vs Local)
if QDRANT_CLOUD_URL and QDRANT_API_KEY:
    QDRANT_URL = QDRANT_CLOUD_URL
else:
    QDRANT_URL = QDRANT_LOCAL_URL

def load_checkpoint() -> List[str]:
    """Retorna os nomes dos arquivos JSON de chunks que já foram processados."""
    if not CHECKPOINT_FILE.exists():
        return []
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("processed_files", [])
    except Exception as e:
        print(f"Aviso ao carregar checkpoint: {e}. Iniciando do zero.")
        return []

def save_checkpoint(processed_files: List[str]):
    """Salva a lista de arquivos processados no disco."""
    try:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed_files": processed_files}, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar checkpoint: {e}")

async def ingest_chunks(chunk_files: List[Path]):
    """Embed and upsert chunks from JSON files to Qdrant with checkpoints."""
    
    # 1. Initialize Qdrant Client
    if QDRANT_URL and not QDRANT_URL.startswith("http"):
        client = QdrantClient(path=QDRANT_URL)
    else:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    # 2. Initialize Vector Store
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # 3. Initialize Embedding Model (gemini-embedding-2-preview)
    from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
    embed_model = GoogleGenAIEmbedding(
        model_name="models/gemini-embedding-2-preview",
        api_key=GOOGLE_API_KEY
    )
    
    # Carregar checkpoint
    processed_files = load_checkpoint()
    print(f"-> Checkpoint carregado: {len(processed_files)} arquivos já processados anteriormente.")
    
    # Filtrar arquivos pendentes
    pending_files = sorted(
        [f for f in chunk_files if f.name not in processed_files],
        key=lambda x: x.name
    )
    
    if not pending_files:
        print("-> Todos os arquivos já foram ingeridos com sucesso!")
        return
        
    print(f"-> Total de arquivos pendentes para ingestão: {len(pending_files)}")
    
    for idx, chunk_file in enumerate(pending_files, 1):
        print(f"\n[{idx}/{len(pending_files)}] Processando: {chunk_file.name} ...")
        
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                chunks_data = json.load(f)
                
            file_documents = []
            for item in chunks_data:
                doc = Document(
                    text=item["text"],
                    metadata=item["metadata"]
                )
                file_documents.append(doc)
                
            if not file_documents:
                print(f"   Aviso: {chunk_file.name} está vazio. Pulando.")
                processed_files.append(chunk_file.name)
                save_checkpoint(processed_files)
                continue
                
            # Ingerir este arquivo específico no Qdrant
            VectorStoreIndex.from_documents(
                file_documents,
                storage_context=storage_context,
                embed_model=embed_model,
                show_progress=True
            )
            
            # Registrar no checkpoint
            processed_files.append(chunk_file.name)
            save_checkpoint(processed_files)
            print(f"   Sucesso! {len(file_documents)} chunks salvos no Qdrant.")
            
            # Delay curto para respeitar limites de quota gratuita
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"   Erro ao processar o arquivo {chunk_file.name}: {e}")
            print("   Interrompendo a ingestão. Execute o script novamente para continuar do checkpoint.")
            return
            
    print(f"\n-> Sucesso! Todos os dados pendentes foram ingeridos na coleção '{COLLECTION_NAME}'.")

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
