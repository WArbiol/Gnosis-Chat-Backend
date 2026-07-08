from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.dependencies import get_supabase_client
from app.core.security import get_current_user
from app.schemas.user import UserProfile

router = APIRouter()

@router.get("/url")
def get_pdf_signed_url(
    book_name: str = Query(..., description="Nome exato do livro a buscar no catálogo"),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Busca o registro do livro na tabela pdf_catalog e gera uma URL assinada
    expirando em 1 hora (3600 segundos) para leitura no app.
    """
    supabase = get_supabase_client()
    
    # 1. Consultar a tabela pdf_catalog
    try:
        response = (
            supabase.table("pdf_catalog")
            .select("file_path, file_size_bytes, page_count")
            .eq("book_name", book_name)
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao consultar o banco de dados: {str(e)}"
        )
        
    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="PDF ainda não disponível para este livro."
        )
        
    record = response.data[0]
    file_path = record["file_path"]
    file_size_bytes = record.get("file_size_bytes", 0)
    page_count = record.get("page_count", 0)
    
    # 2. Gerar URL assinada no Supabase Storage
    try:
        # Expira em 1 hora (3600 segundos)
        signed_url_res = supabase.storage.from_("pdfs").create_signed_url(
            path=file_path,
            expires_in=3600
        )
        # O retorno da lib do Supabase Python pode ter chaves diferentes dependendo da versão
        signed_url = signed_url_res.get("signedURL") or signed_url_res.get("signedUrl")
        if not signed_url:
            # Caso a lib retorne como string diretamente ou outro formato
            if isinstance(signed_url_res, str):
                signed_url = signed_url_res
            else:
                raise Exception("URL assinada não pôde ser obtida da resposta.")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar URL assinada no Storage: {str(e)}"
        )
        
    return {
        "url": signed_url,
        "book_name": book_name,
        "file_path": file_path,
        "file_size_bytes": file_size_bytes,
        "page_count": page_count
    }

@router.get("/catalog")
def get_pdf_catalog(
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Lista todas as obras e autores no pdf_catalog (respeitando o nível da câmara do usuário).
    """
    supabase = get_supabase_client()
    try:
        query = supabase.table("pdf_catalog").select("book_name, author, chamber")
        if current_user.chamber_level < 2:
            query = query.eq("chamber", 1)
        response = query.execute()
        return response.data or []
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao consultar catálogo de PDFs: {str(e)}"
        )
