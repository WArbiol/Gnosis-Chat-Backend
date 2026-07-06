import os
import sys
import time
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from qdrant_client import QdrantClient

def run_test():
    client = QdrantClient(path="data/qdrant_db")
    collection_name = "gnosis_books"
    
    try:
        start_time = time.time()
        print("Scrolling points fetching book_name and author payloads...")
        unique_books = set()
        unique_authors = set()
        offset = None
        limit = 2000
        
        while True:
            response = client.scroll(
                collection_name=collection_name,
                limit=limit,
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
            
        end_time = time.time()
        print(f"Loaded {len(unique_books)} unique books and {len(unique_authors)} unique authors in {end_time - start_time:.4f} seconds!")
        print("Unique authors:", list(unique_authors))
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
