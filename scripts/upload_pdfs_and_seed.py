# %% 1+1
import os
import sys
import unicodedata
from pathlib import Path
from pypdf import PdfReader

def sanitize_storage_path(path_str: str) -> str:
    # Normaliza e remove acentos
    normalized = unicodedata.normalize('NFKD', path_str)
    ascii_bytes = normalized.encode('ascii', 'ignore')
    sanitized = ascii_bytes.decode('ascii')
    # Substitui dois pontos (:) por hifens para evitar problemas com S3/Storage
    sanitized = sanitized.replace(":", "-")
    return sanitized


# Add parent directory to sys.path to allow importing app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.dependencies import get_supabase_client

# Directory where PDFs are stored
PDFS_DIR = Path("/home/walter/Documents/AI projects/Mobile/gnosis-chat-backend/data/pdfs")
BUCKET_NAME = "pdfs"

def main():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("Erro: Credenciais do Supabase não configuradas no arquivo .env!")
        return

    supabase = get_supabase_client()
    
    # 1. Verificar se o bucket existe, se não, tentar criar
    print(f"Verificando bucket '{BUCKET_NAME}'...")
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        if BUCKET_NAME not in bucket_names:
            print(f"Bucket '{BUCKET_NAME}' não encontrado. Criando bucket privado...")
            supabase.storage.create_bucket(BUCKET_NAME, options={"public": False})
            print("Bucket criado com sucesso!")
        else:
            print(f"Bucket '{BUCKET_NAME}' já existe.")
    except Exception as e:
        print(f"Nota: Não foi possível listar/criar bucket automaticamente ({e}).")
        print("Certifique-se de que o bucket privado 'pdfs' foi criado no painel do Supabase.")

    # 2. Localizar PDFs
    if not PDFS_DIR.exists():
        print(f"Erro: Diretório de PDFs não encontrado em: {PDFS_DIR}")
        return

    pdf_files = list(PDFS_DIR.rglob("*.pdf"))
    print(f"Encontrados {len(pdf_files)} arquivos PDF para processar.")
    authors=set()
    for i, file_path in enumerate(pdf_files, 1):
        filename = file_path.name
        pdf_no_ext = file_path.stem
        relative_path = file_path.relative_to(PDFS_DIR)
        
        # Determinar a câmara
        chamber = 2 if "2a_camara" in str(relative_path) else 1
        
        # Determinar livro e autor
        if " - " in pdf_no_ext:
            parts = pdf_no_ext.rsplit(" - ", 1)
            book_name = parts[0].strip()
            author = parts[1].strip()
        else:
            book_name = pdf_no_ext.strip()
            author = "Desconhecido"
        authors.add(author)
        print(book_name, '\n    ', author)

        # Obter tamanho e páginas
        file_size = os.path.getsize(file_path)
        try:
            reader = PdfReader(file_path)
            page_count = len(reader.pages)
        except Exception as e:
            print(f"[{i}/{len(pdf_files)}] Erro ao ler páginas de {filename}: {e}")
            page_count = 0

        # Caminho final no storage (ex: "1a_camara/Livro.pdf")
        storage_path = sanitize_storage_path(str(relative_path))

        print(f"[{i}/{len(pdf_files)}] Processando: {book_name} ({page_count} pág, {file_size / (1024*1024):.2f} MB)")

        # 3. Upload para o Supabase Storage
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Tenta fazer upload (com upsert=True se já existir)
            supabase.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=file_data,
                file_options={"x-upsert": "true", "content-type": "application/pdf"}
            )
            print(f"  -> Upload concluído para storage: {storage_path}")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  -> Arquivo já existe no storage. Pulando upload.")
            else:
                print(f"  -> Erro no upload de {filename}: {e}")

        # 4. Inserir/Atualizar tabela pdf_catalog
        try:
            record = {
                "book_name": book_name,
                "file_path": storage_path,
                "chamber": chamber,
                "author": author,
                "file_size_bytes": file_size,
                "page_count": page_count
            }
            
            # Supabase upsert
            supabase.table("pdf_catalog").upsert(
                record, 
                on_conflict="book_name"
            ).execute()
            print(f"  -> Registro no pdf_catalog atualizado.")
        except Exception as e:
            print(f"  -> Erro ao salvar no banco: {e}")

    print("\nProcesso concluído com sucesso!")

if __name__ == "__main__":
    main()
