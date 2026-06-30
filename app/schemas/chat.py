from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.conversation import CitationResponse

class UIFilters(BaseModel):
    """Filtros selecionados pelo usuário na interface mobile ou inferidos pelo orquestrador."""
    books: list[str] | None = Field(default=None, description="Lista de títulos de livros específicos")
    authors: list[str] | None = Field(default=None, description="Lista de autores")
    chamber_levels: list[int] | None = Field(default=None, description="Níveis de câmara para filtrar (1 ou 2)")
    chapters: list[str] | None = Field(default=None, description="Capítulos específicos dos livros")

class ChatRequest(BaseModel):
    """Payload de entrada para realizar perguntas ao RAG."""
    query: str = Field(..., min_length=1, max_length=2000, description="Pergunta do usuário")
    conversation_id: UUID | None = Field(default=None, description="ID da conversa existente. Se nulo, cria uma nova.")
    ui_filters: UIFilters | None = Field(default=None, description="Filtros opcionais aplicados na UI")

# --- Schemas para Server-Sent Events (SSE) ---

class ChatStreamStatus(BaseModel):
    """Mensagem de status emitida quando o grafo transita entre nós."""
    type: str = "status"
    agent: str = Field(..., description="Nome do agente atual (ex: orchestrator, researcher, critique, writer, judge, recap)")
    message: str = Field(..., description="Descrição amigável do que o agente está fazendo")

class ChatStreamToken(BaseModel):
    """Chunk de texto emitido durante a geração de resposta do Writer."""
    type: str = "token"
    text: str = Field(..., description="Pedaço da string de resposta")

class ChatStreamFinal(BaseModel):
    """Payload final consolidado com todos os dados estruturados."""
    type: str = "final"
    conversation_id: UUID = Field(..., description="ID da conversa em que a mensagem foi salva")
    message_id: UUID = Field(..., description="ID da mensagem gerada")
    answer: str = Field(..., description="Resposta de texto final completa")
    citations: list[CitationResponse] = Field(default=[], description="Lista de fontes citadas")
    recap: str | None = Field(default=None, description="Recap/Resumo de 2 a 3 frases")
    route: str = Field(..., description="Rota tomada pelo orquestrador (ex: RAG_BOOKS, DIRECT, etc.)")
    cost_estimate: float = Field(default=0.0, description="Custo estimado da execução em USD")
