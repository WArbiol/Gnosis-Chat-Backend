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

# Adiciona o diretório pai ao sys.path para importar configurações e dependências
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.dependencies import get_supabase_client

PDFS_DIR = Path("/home/walter/Documents/AI projects/Mobile/gnosis-chat-backend/data/pdfs")
BUCKET_NAME = "pdfs"

# Os 4 PDFs que ultrapassaram o limite de 50MB do plano gratuito do Supabase
TARGET_BOOKS = [
    "Los Misterios Ocultos del Divino Daimon - Juan Capasso.pdf",
    "Os Sacramentos da Câmara Nupcial - V.M. Aron.pdf",
    "Orientação Conjugal - V.M. Desoto.pdf",
    "Ele é Ele... Divino Daimon - Ana Judith Gasca.pdf"
]

def main():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("Erro: Credenciais do Supabase não configuradas no arquivo .env!")
        return

    supabase = get_supabase_client()

    print("=== Iniciando Upload de PDFs Grandes (Outliers) ===")
    
    # Localizar os arquivos específicos
    pdf_files = []
    for target in TARGET_BOOKS:
        normalized_target = unicodedata.normalize('NFKD', target)
        found = False
        for p in PDFS_DIR.rglob("*.pdf"):
            norm_p_name = unicodedata.normalize('NFKD', p.name)
            if p.name == target or norm_p_name == normalized_target:
                pdf_files.append(p)
                found = True
                break
        if not found:
            print(f"Aviso: Arquivo '{target}' não foi encontrado em {PDFS_DIR}")

    if not pdf_files:
        print("Nenhum dos PDFs grandes foi encontrado para upload.")
        return

    print(f"Encontrados {len(pdf_files)} PDFs grandes para upload.")

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
            
        file_size = os.path.getsize(file_path)
        try:
            reader = PdfReader(file_path)
            page_count = len(reader.pages)
        except Exception as e:
            print(f"Erro ao ler páginas de {filename}: {e}")
            page_count = 0

        storage_path = sanitize_storage_path(str(relative_path))

        print(f"\n[{i}/{len(pdf_files)}] Processando: {book_name} ({page_count} pág, {file_size / (1024*1024):.2f} MB)")

        # 1. Upload para o Supabase Storage
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            print(f"  -> Fazendo upload para storage (isso pode levar algum tempo devido ao tamanho)...")
            supabase.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=file_data,
                file_options={"x-upsert": "true", "content-type": "application/pdf"}
            )
            print(f"  -> Upload concluído com sucesso: {storage_path}")
        except Exception as e:
            print(f"  -> Erro no upload de {filename}: {e}")
            print("  -> (Dica: Se o erro for 413, certifique-se de que fez o upgrade para o plano Pro e alterou o limite de upload no dashboard do Supabase)")
            continue

        # 2. Registrar/Atualizar no pdf_catalog do banco de dados
        try:
            record = {
                "book_name": book_name,
                "file_path": storage_path,
                "chamber": chamber,
                "author": author,
                "file_size_bytes": file_size,
                "page_count": page_count
            }
            supabase.table("pdf_catalog").upsert(record, on_conflict="book_name").execute()
            print(f"  -> Registro no pdf_catalog atualizado para '{book_name}'.")
        except Exception as e:
            print(f"  -> Erro ao salvar no banco: {e}")

    print("\nProcesso de upload dos arquivos grandes concluído!")

if __name__ == "__main__":
    main()
