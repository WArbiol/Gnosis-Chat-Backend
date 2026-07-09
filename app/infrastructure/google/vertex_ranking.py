import httpx
import logging
from app.application.interfaces.vector_store_gateway import ChunkResult
from app.application.interfaces.reranker_gateway import RerankerGateway
from app.core.config import settings

logger = logging.getLogger(__name__)

class VertexRanking(RerankerGateway):
    """Implementação do RerankerGateway usando a Vertex AI Ranking API.
    
    Possui fallback automático para ordenação pelo score do Qdrant caso as credenciais 
    do GCP não estejam configuradas ou ocorra algum erro na requisição.
    """

    def __init__(self) -> None:
        self.project_id = None
        self.location = "global"
        self.has_auth = False
        
        import os
        # Tenta carregar credenciais do gcp para obter tokens OAuth2
        try:
            import google.auth
            from google.auth.transport.requests import Request
            
            self.credentials, default_project = google.auth.default()
            self.project_id = (
                settings.google_cloud_project or 
                os.environ.get("GOOGLE_CLOUD_PROJECT") or 
                os.environ.get("GCP_PROJECT") or 
                default_project
            )
            if self.project_id:
                self.project_id = self.project_id.strip('"').strip("'")
            
            if self.credentials and self.project_id:
                self.has_auth = True
                logger.info(f"Vertex Ranking inicializado com o projeto GCP: {self.project_id}")
            else:
                self.has_auth = False
                logger.debug("Vertex Ranking: Credenciais ou ID de projeto GCP não encontrados. Usando fallback do Qdrant.")
        except Exception as e:
            self.has_auth = False
            logger.debug(
                f"Não foi possível inicializar credenciais padrão do Google. "
                f"Reranker usará fallback baseado no score do Qdrant. Erro: {e}"
            )

    async def _get_access_token(self) -> str | None:
        """Obtém um token de acesso válido usando as credenciais do GCP."""
        if not self.has_auth or not self.credentials:
            return None
            
        try:
            import asyncio
            from google.auth.transport.requests import Request
            
            loop = asyncio.get_running_loop()
            # Refrescar credenciais de forma síncrona dentro do executor
            await loop.run_in_executor(None, lambda: self.credentials.refresh(Request()))
            return self.credentials.token
        except Exception as e:
            logger.error(f"Erro ao atualizar token de acesso GCP: {e}")
            return None

    async def rerank(
        self,
        query: str,
        documents: list[ChunkResult],
        top_n: int = 10
    ) -> list[ChunkResult]:
        # Se não houver documentos, retorna vazio
        if not documents:
            return []

        # 1. Fallback se não houver autenticação GCP ativa ou ID do projeto
        if not self.has_auth or not self.project_id:
            logger.debug("Usando fallback de ordenação do Qdrant (sem GCP credentials).")
            # Ordena pelo score original decrescente e pega os top_n
            sorted_docs = sorted(documents, key=lambda x: x["score"], reverse=True)
            return sorted_docs[:top_n]

        token = await self._get_access_token()
        if not token:
            logger.warning("Falha na geração do token GCP. Usando fallback de ordenação do Qdrant.")
            sorted_docs = sorted(documents, key=lambda x: x["score"], reverse=True)
            return sorted_docs[:top_n]

        # 2. Chamar a Vertex AI Ranking API
        # Documentação: https://cloud.google.com/generative-ai-app-builder/docs/ranking
        url = (
            f"https://{self.location}-discoveryengine.googleapis.com/v1alpha/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"rankingConfigs/default_ranking_config:rank"
        )
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Mapeia os registros para o formato da API
        records = [
            {
                "id": str(idx),
                "content": doc["text"]
            }
            for idx, doc in enumerate(documents)
        ]
        
        payload = {
            "query": query,
            "records": records
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    logger.error(
                        f"Vertex Ranking API retornou status {response.status_code}. "
                        f"Resposta: {response.text}"
                    )
                    if response.status_code in [403, 404]:
                        logger.warning("Vertex Ranking API retornou 403/404. Desativando cliente para evitar chamadas lentas subsequentes.")
                        self.has_auth = False
                    # Fallback em caso de erro da API
                    sorted_docs = sorted(documents, key=lambda x: x["score"], reverse=True)
                    return sorted_docs[:top_n]
                
                data = response.json()
                results = data.get("results", [])
                
                # Mapeia as posições originais ordenadas
                reranked_docs = []
                for item in results:
                    record_id = int(item["id"])
                    score = float(item.get("score", 0.0))
                    
                    doc = documents[record_id].copy()
                    doc["score"] = score  # Sobrescreve o score com o do Reranker
                    reranked_docs.append(doc)
                
                return reranked_docs[:top_n]
                
        except Exception as e:
            logger.exception(f"Exceção durante chamada à Vertex Ranking API: {e}. Usando fallback.")
            sorted_docs = sorted(documents, key=lambda x: x["score"], reverse=True)
            return sorted_docs[:top_n]
