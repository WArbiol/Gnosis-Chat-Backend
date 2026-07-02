import asyncio
import os
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Carregar variáveis do .env do backend
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, ".env"))

sys.path.append(backend_dir)
from app.core.config import settings

def inspect():
    url_or_path = settings.qdrant_url
    print(f"Conectando ao Qdrant em: {url_or_path}")
    if url_or_path and not url_or_path.startswith("http"):
        client = QdrantClient(path=url_or_path)
    else:
        client = QdrantClient(url=url_or_path)
        
    collection = settings.qdrant_collection_books
    print(f"Coleção: {collection}")
    
    # Obter contagem de pontos
    info = client.get_collection(collection_name=collection)
    print(f"Contagem de pontos: {info.points_count}")
    
    # Buscar 2 pontos sem filtros
    res = client.scroll(
        collection_name=collection,
        limit=2,
        with_payload=True,
        with_vectors=False
    )
    
    points = res[0]
    print(f"\nRetornados {len(points)} pontos.")
    for idx, p in enumerate(points):
        print(f"\nPonto #{idx+1} (ID: {p.id}):")
        print("Payload:", p.payload)

if __name__ == "__main__":
    inspect()
