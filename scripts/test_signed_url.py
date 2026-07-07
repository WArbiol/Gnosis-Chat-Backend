import sys
from pathlib import Path
import urllib.request

# Add parent directory to sys.path to allow importing app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.dependencies import get_supabase_client

def main():
    supabase = get_supabase_client()
    
    # 1. Consultar a tabela pdf_catalog para pegar um registro
    response = (
        supabase.table("pdf_catalog")
        .select("book_name, file_path")
        .limit(1)
        .execute()
    )
    
    if not response.data:
        print("Nenhum registro encontrado no pdf_catalog.")
        return
        
    record = response.data[0]
    book_name = record["book_name"]
    file_path = record["file_path"]
    print(f"Livro: {book_name}")
    print(f"Path no storage: {file_path}")
    
    # 2. Gerar URL assinada
    signed_url_res = supabase.storage.from_("pdfs").create_signed_url(
        path=file_path,
        expires_in=3600
    )
    print(f"Retorno do create_signed_url: {signed_url_res}")
    
    signed_url = None
    if isinstance(signed_url_res, dict):
        signed_url = signed_url_res.get("signedURL") or signed_url_res.get("signedUrl")
    elif isinstance(signed_url_res, str):
        signed_url = signed_url_res
        
    print(f"URL assinada extraída: {signed_url}")
    
    if not signed_url:
        print("Falha ao extrair URL assinada.")
        return
        
    # 3. Testar download via HTTP GET
    try:
        req = urllib.request.Request(
            signed_url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req) as res:
            content_type = res.headers.get('Content-Type')
            content_length = res.headers.get('Content-Length')
            code = res.getcode()
            print(f"Status HTTP: {code}")
            print(f"Content-Type: {content_type}")
            print(f"Content-Length: {content_length}")
            if code == 200:
                print("Download de teste funcionou com sucesso!")
            else:
                print("Download falhou ou retornou status diferente de 200.")
    except Exception as e:
        print(f"Erro ao baixar arquivo usando a URL assinada: {e}")

if __name__ == "__main__":
    main()
