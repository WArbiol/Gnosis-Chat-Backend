from typing import Literal, Any
from pydantic import BaseModel, Field
from app.agents.state import GraphState, SessionCounters
from app.application.interfaces.llm_gateway import LLMGateway

from langchain_core.runnables import RunnableConfig

class OrchestratorDecision(BaseModel):
    """Modelo de decisão estruturado retornado pelo LLM do Orquestrador."""
    thought: str = Field(
        ..., description="Análise lógica detalhada (Chain-of-Thought) passo a passo. Avalie se a pergunta atual é uma continuação do histórico recente ou um novo tópico, identifique os termos-chave esotéricos, mapeie os possíveis livros/autores do acervo e planeje a melhor rota e sub-queries antes de definir os demais campos."
    )
    next_step: Literal["researcher", "writer", "direct_response", "ask_user"] = Field(
        ..., description="Decide se pesquisa no RAG, escreve resposta final, responde diretamente ou pede esclarecimentos."
    )
    sub_queries: list[str] = Field(
        default=[], description="Decomposição da query principal em até 3 sub-queries mais simples focadas em conceitos. IMPORTANTE: Nunca inclua nomes de livros, autores ou sufixos nas sub-queries, pois eles já serão filtrados via metadados e poluiriam os embeddings."
    )
    inferred_books: list[str] | None = Field(
        default=None, description="Títulos de livros inferidos a partir da query do usuário."
    )
    inferred_authors: list[str] | None = Field(
        default=None, description="Nomes de autores inferidos a partir da query."
    )
    inferred_chapters: list[str] | None = Field(
        default=None, description="Capítulos de livros inferidos a partir da query."
    )
    inferred_chamber_levels: list[int] | None = Field(
        default=None, description="Níveis de câmara (1 para Primeira Câmara/Público, 2 para Segunda Câmara) inferidos a partir da query do usuário se ele pedir explicitamente para buscar em uma câmara específica."
    )
    inferred_page_start: int | None = Field(
        default=None, description="Página inicial inferida ou especificada para filtrar a busca (ex: se o feedback pedir páginas específicas)."
    )
    inferred_page_end: int | None = Field(
        default=None, description="Página final inferida ou especificada para filtrar a busca (ex: se o feedback pedir páginas específicas)."
    )
    clarification_question: str | None = Field(
        default=None, description="Pergunta esclarecedora se next_step for 'ask_user'."
    )
    direct_answer: str | None = Field(
        default=None, description="Resposta direta completa se next_step for 'direct_response'."
    )

async def orchestrator_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó principal do Orquestrador que decide o fluxo do RAG, extrai filtros e decompõe queries."""
    from app.agents.nodes.utils import get_configurable_llm, get_configurable_database
    llm: LLMGateway = get_configurable_llm(config)
    database = get_configurable_database(config)

    # 1. Recuperar ou inicializar contadores da sessão
    counters: SessionCounters = state.get("session_counters") or {
        "researcher_calls": 0,
        "critique_loops": 0,
        "judge_loops": 0,
        "ask_user_calls": 0
    }

    # Se o Critique já avaliou e marcou as fontes como suficientes, prosseguir diretamente para o Writer
    critique_verdict = state.get("critique_verdict")
    if critique_verdict == "sufficient":
        return {
            "next_step": "writer",
            "session_counters": counters
        }

    # Se for uma retoma de Human-in-the-Loop, ler a resposta do usuário
    user_clarification = state.get("user_clarification")
    query = state.get("query", "")
    
    # Se houver resposta de esclarecimento, anexar à query original
    contextual_query = query
    if user_clarification:
        contextual_query = f"{query} (Nota de esclarecimento do usuário: {user_clarification})"

    # 2. Construir o Prompt de Decisão
    critique_feedback = state.get("critique_feedback")
    previous_research = ""
    if critique_feedback:
        previous_research = (
            "--- TENTATIVAS DE PESQUISA ANTERIORES E FEEDBACK ---\n"
            f"O avaliador (Critique) classificou os resultados da pesquisa anterior como insuficientes.\n"
            f"Feedback detalhado do Critique: {critique_feedback}\n"
            "Trechos e fontes que já conseguimos recuperar até agora:\n"
        )
        research_results = state.get("research_results") or []
        for r_res in research_results:
            sub_q = r_res.get("sub_query", "")
            previous_research += f"- Sub-query: '{sub_q}':\n"
            for chunk, citation in zip(r_res.get("chunks", []), r_res.get("citations", [])):
                # citation is CitationDraft object or dict
                b_name = getattr(citation, "book_name", citation.get("book_name") if isinstance(citation, dict) else "Desconhecido")
                pg = getattr(citation, "page", citation.get("page") if isinstance(citation, dict) else 1)
                previous_research += f"  * [{b_name}, pág. {pg}]: {chunk[:120]}...\n"
        previous_research += (
            "Analise cuidadosamente o feedback acima. Se o Critique disser que falta algo específico "
            "e mencionar nomes de livros/capítulos ou páginas específicas, você deve usar esse feedback para refinar sua busca.\n"
            "Você pode gerar novas sub-queries focando no que falta, e/ou usar 'inferred_page_start' e 'inferred_page_end' "
            "para focar a busca vetorial em páginas específicas se o Critique tiver sugerido ou se fizer sentido no contexto.\n"
            "---------------------------------------------------\n\n"
        )

    system_instruction = (
        "Você é o Orchestrator do sistema Gnosis Chat, um RAG sobre obras gnósticas.\n"
        "Sua função é analisar a query do usuário e as premissas e decidir a rota:\n"
        "1. 'direct_response': Para saudações, perguntas simples sobre a aplicação ou fora do escopo do corpus literário gnóstico.\n"
        "2. 'ask_user': Se a pergunta for excessivamente vaga ou ambígua e necessitar de detalhamento do usuário.\n"
        "3. 'researcher': Se necessitar de informações específicas contidas nos livros gnósticos.\n"
        "Você também deve extrair filtros de metadados inferidos a partir do texto da pergunta (livros, autores, capítulos) "
        "e decompor a query em até 3 sub-queries focadas se a pergunta contiver múltiplos tópicos (ex: 'fale sobre o Absoluto e a Caridade').\n"
        "IMPORTANTE: As sub-queries devem conter APENAS termos e conceitos teológicos e esotéricos. NUNCA inclua os nomes dos livros, autores ou capítulos nas sub-queries (ex: em vez de 'Ego no Tratado de Psicologia', use apenas 'Ego').\n"
        "PÁGINAS: O banco de dados suporta filtros por páginas específicas ou intervalos de páginas (`page` nos metadados). Se o feedback do Critique sugerir que a resposta ou detalhes adicionais podem ser encontrados em páginas ou faixas de páginas específicas de um livro, você deve preencher 'inferred_page_start' e 'inferred_page_end' para focar a nova busca vetorial exatamente nesse intervalo. Caso contrário, deixe-os como null.\n"
        "IDIOMA E GRAFIA: Se a pergunta for em português, gere a resposta direta (direct_answer) ou pergunta esclarecedora (clarification_question) obrigatoriamente em português do Brasil (pt-BR). Use grafias brasileiras legítimas (ex: 'exata' e não 'exacta', 'fato' e não 'facto') e termos adaptados à tradução gnóstica brasileira padrão."
    )

    prompt = (
        f"Query do Usuário: {contextual_query}\n\n"
        f"Histórico Recente:\n{state.get('conversation_history', [])}\n\n"
        f"{previous_research}"
        "Analise a query e tome a decisão estruturada correspondente."
    )

    # 3. Chamar a LLM via Gateway para retornar o JSON estruturado
    decision: OrchestratorDecision = await llm.generate_json(
        prompt=prompt,
        response_schema=OrchestratorDecision,
        system_instruction=system_instruction,
        temperature=0.1,
        use_premium_model=False # 3.0 Flash Lite
    )

    # 4. Consolidar os Filtros (UI + Inferidos)
    ui_filters = state.get("ui_filters") or {}
    
    # Resolver listas combinando UI com o que a LLM inferiu
    books = list(set((ui_filters.get("books") or []) + (decision.inferred_books or [])))
    authors = list(set((ui_filters.get("authors") or []) + (decision.inferred_authors or [])))
    chapters = list(set((ui_filters.get("chapters") or []) + (decision.inferred_chapters or [])))
    # Combinar níveis de câmara da UI com os inferidos pelo orquestrador
    chamber_levels = list(set((ui_filters.get("chamber_levels") or []) + (decision.inferred_chamber_levels or [])))

    user_profile = state.get("user")
    if isinstance(user_profile, dict):
        max_chamber = user_profile.get("chamber_level", 1)
    else:
        max_chamber = user_profile.chamber_level if user_profile else 1
    # Se o filtro pedir nível acima do do usuário, reduzimos para o permitido
    if chamber_levels:
        chamber_levels = [c for c in chamber_levels if c <= max_chamber]
    else:
        chamber_levels = [c for c in range(1, max_chamber + 1)]

    page_start = ui_filters.get("page_start") or decision.inferred_page_start
    page_end = ui_filters.get("page_end") or decision.inferred_page_end

    metadata_filters = {}
    if books: metadata_filters["books"] = books
    if authors: metadata_filters["authors"] = authors
    if chamber_levels: metadata_filters["chamber_levels"] = chamber_levels
    if chapters: metadata_filters["chapters"] = chapters
    if page_start is not None: metadata_filters["page_start"] = page_start
    if page_end is not None: metadata_filters["page_end"] = page_end

    # 5. Aplicar limites de loops na rota de decisão
    next_step = decision.next_step
    if next_step == "researcher" and counters["researcher_calls"] >= 7:
        # Se exceder o limite de pesquisas, força rota para o Writer finalizar com o que tem
        next_step = "writer"
    elif next_step == "ask_user" and counters["ask_user_calls"] >= 2:
        # Se exceder limite de esclarecimentos, tenta pesquisa direta
        next_step = "researcher"

    # Se a decisão for fazer pesquisa, inicializar a sub-query se a lista vier vazia
    sub_queries = decision.sub_queries
    if next_step == "researcher" and not sub_queries:
        sub_queries = [query]

    # 5.5. Detectar se o usuário pediu por conteúdo da Segunda Câmara que lhe é restrito
    chamber_warning = None
    if max_chamber < 2 and database:
        try:
            second_chamber_catalog = await database.get_second_chamber_catalog()
            
            import unicodedata
            def normalize(t: str) -> str:
                nfkd = unicodedata.normalize('NFKD', t)
                return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()
            
            norm_query = normalize(query)
            restricted_books = []
            restricted_authors = []
            
            for item in second_chamber_catalog:
                b_name = item.get("book_name", "")
                b_author = item.get("author", "")
                
                norm_book = normalize(b_name)
                norm_author = normalize(b_author)
                
                inferred_b_match = decision.inferred_books and any(normalize(ib) in norm_book or norm_book in normalize(ib) for ib in decision.inferred_books)
                inferred_a_match = decision.inferred_authors and any(normalize(ia) in norm_author or norm_author in normalize(ia) for ia in decision.inferred_authors)
                
                query_b_match = len(norm_book) > 5 and norm_book in norm_query
                query_a_match = len(norm_author) > 5 and norm_author in norm_query
                
                if (inferred_b_match or query_b_match) and b_name not in restricted_books:
                    restricted_books.append(b_name)
                if (inferred_a_match or query_a_match) and b_author not in restricted_authors:
                    restricted_authors.append(b_author)
            
            if restricted_books or restricted_authors:
                warnings = []
                if restricted_books:
                    warnings.append(f"obras da Segunda Câmara (ex: *{', '.join(restricted_books)}*)")
                if restricted_authors:
                    warnings.append(f"autores restritos à Segunda Câmara (ex: *{', '.join(restricted_authors)}*)")
                
                joined_warnings = " e ".join(warnings)
                chamber_warning = (
                    f"⚠️ **Nota de Acesso à Câmara**: Identificamos que a sua pergunta faz referência a {joined_warnings}. "
                    "Como a sua conta atual possui acesso apenas à **Primeira Câmara (Público)**, buscamos as informações e "
                    "correspondências disponíveis nas obras públicas da Primeira Câmara. Caso queira acessar o conteúdo restrito da Segunda Câmara, "
                    "verifique com a administração a liberação correspondente."
                )
        except Exception as e:
            print(f"Erro ao verificar catálogo de restrições da Segunda Câmara: {e}")

    # Retornar alterações no estado
    updates: dict[str, Any] = {
        "next_step": next_step,
        "metadata_filters": metadata_filters,
        "session_counters": counters
    }
    if chamber_warning:
        updates["chamber_warning"] = chamber_warning

    if next_step == "researcher":
        updates["sub_queries"] = sub_queries
    elif next_step == "direct_response":
        updates["direct_answer"] = decision.direct_answer or "Como posso te ajudar hoje?"
    elif next_step == "ask_user":
        updates["clarification_question"] = decision.clarification_question or "Poderia esclarecer melhor a sua pergunta?"
        counters["ask_user_calls"] += 1

    return updates
