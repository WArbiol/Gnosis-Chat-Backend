import asyncio
from datetime import datetime, timedelta, timezone
from supabase import Client
from app.application.interfaces.database_gateway import DatabaseGateway
from app.schemas.user import UserProfile, PlanEnum
from app.schemas.chat import CitationDraft

class SupabaseDatabase(DatabaseGateway):
    """Implementação do DatabaseGateway utilizando a API / SDK do Supabase com Service Role."""

    def __init__(self, client: Client) -> None:
        self.client = client

    async def get_user_profile(self, user_id: str, email: str | None = None) -> UserProfile:
        from app.core.config import settings
        # Bypass imediato para tokens de teste
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return UserProfile(
                id=user_id,
                email=email or f"{user_id}@gnosis.chat",
                plan=PlanEnum.BASIC,
                chamber_level=1,
                question_count=0
            )

        try:
            loop = asyncio.get_running_loop()
            
            # Chamada síncrona envelopada em executor
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.table("users")
                    .select("id, email, avatar_url, plan, chamber_level, question_count, last_reset_at, created_at")
                    .eq("id", user_id)
                    .execute()
                )
            except Exception as select_err:
                print(f"DEBUG DB: Falha ao carregar last_reset_at ({select_err}). Tentando fallback.")
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.table("users")
                    .select("id, email, avatar_url, plan, chamber_level, question_count, created_at")
                    .eq("id", user_id)
                    .execute()
                )
            
            if not response.data:
                # Tentamos criar o perfil na tabela public.users dinamicamente se não existir
                default_email = email or f"{user_id}@gnosis.chat"
                try:
                    insert_response = await loop.run_in_executor(
                        None,
                        lambda: self.client.table("users")
                        .insert({
                            "id": user_id,
                            "email": default_email,
                            "plan": "free",
                            "chamber_level": 1,
                            "question_count": 0
                        })
                        .execute()
                    )
                    if insert_response.data:
                        # Refetch com os campos default preenchidos
                        try:
                            response = await loop.run_in_executor(
                                None,
                                lambda: self.client.table("users")
                                .select("id, email, avatar_url, plan, chamber_level, question_count, last_reset_at, created_at")
                                .eq("id", user_id)
                                .execute()
                            )
                        except Exception:
                            response = insert_response
                except Exception as insert_err:
                    print(f"DEBUG DB: Falha no auto-provisionamento do usuário {user_id}: {insert_err}")
                    raise ValueError(f"Usuário com ID {user_id} não encontrado no banco.")

            if not response.data:
                raise ValueError(f"Usuário com ID {user_id} não encontrado no banco.")
                
            data = response.data[0]
            plan = PlanEnum(data["plan"])
            question_count = int(data["question_count"])
            
            # --- Controle e Reset de Cotas ---
            last_reset_str = data.get("last_reset_at")
            created_at_str = data.get("created_at")
            now = datetime.now(timezone.utc)
            
            # Parsing de datetime com suporte retrocompatível
            last_reset = now
            if last_reset_str:
                try:
                    last_reset = datetime.fromisoformat(last_reset_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            elif created_at_str:
                try:
                    last_reset = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            
            should_reset = False
            
            if plan == PlanEnum.FREE:
                # FREE reseta todo Domingo às 00:00 UTC (calendar-based)
                last_reset_date = last_reset.date()
                now_date = now.date()
                last_reset_sunday = last_reset_date - timedelta(days=(last_reset_date.weekday() + 1) % 7)
                now_sunday = now_date - timedelta(days=(now_date.weekday() + 1) % 7)
                
                if now_sunday > last_reset_sunday:
                    should_reset = True
            else:
                # BASIC/PREMIUM reseta no dia 1 de cada mês às 00:00 UTC (calendar-based)
                if (now.year > last_reset.year) or (now.month > last_reset.month):
                    should_reset = True
                    
            if should_reset:
                try:
                    print(f"DEBUG DB: Resetando question_count para o usuário {user_id} ({plan.value}).")
                    await loop.run_in_executor(
                        None,
                        lambda: self.client.table("users")
                        .update({"question_count": 0, "last_reset_at": now.isoformat()})
                        .eq("id", user_id)
                        .execute()
                    )
                    question_count = 0
                    last_reset = now
                except Exception as reset_err:
                    print(f"DEBUG DB: Falha ao resetar question_count para {user_id}: {reset_err}")
            
            return UserProfile(
                id=str(data["id"]),
                email=data["email"],
                avatar_url=data.get("avatar_url"),
                plan=plan,
                chamber_level=int(data["chamber_level"]),
                question_count=question_count,
                last_reset_at=last_reset
            )
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase get_user_profile falhou ({e}). Usando perfil mockado.")
                return UserProfile(
                    id=user_id,
                    email=email or f"{user_id}@gnosis.chat",
                    plan=PlanEnum.BASIC,
                    chamber_level=1,
                    question_count=0
                )
            raise e

    async def increment_user_question_count(self, user_id: str) -> None:
        from app.core.config import settings
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return

        try:
            loop = asyncio.get_running_loop()
            
            # Recupera valor atual
            profile = await self.get_user_profile(user_id)
            new_count = profile.question_count + 1
            
            await loop.run_in_executor(
                None,
                lambda: self.client.table("users")
                .update({"question_count": new_count})
                .eq("id", user_id)
                .execute()
            )
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase increment_user_question_count falhou ({e}). Ignorando em dev.")
                return
            raise e

    async def count_user_messages_in_last_7_days(self, user_id: str) -> int:
        from app.core.config import settings
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return 0

        try:
            loop = asyncio.get_running_loop()
            
            # ISO format do timestamp de 7 dias atrás
            seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            
            # Query: Conta mensagens do usuário feitas nas conversas dele
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .select("id, created_at, role, conversations!inner(user_id)")
                .eq("role", "user")
                .eq("conversations.user_id", user_id)
                .gte("created_at", seven_days_ago)
                .execute()
            )
            
            return len(response.data)
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase count_user_messages_in_last_7_days falhou ({e}). Retornando 0 em dev.")
                return 0
            raise e

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        route: str | None = None,
        token_count: int | None = None
    ) -> str:
        loop = asyncio.get_running_loop()
        
        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content
        }
        if route is not None:
            payload["route"] = route
        if token_count is not None:
            payload["token_count"] = token_count
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .insert(payload)
                .execute()
            )
            
            if not response.data:
                raise RuntimeError("Falha ao salvar mensagem no Supabase.")
                
            return str(response.data[0]["id"])
        except Exception as e:
            from app.core.config import settings
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase messages table not reachable ({e}). Mocking message ID.")
                return "msg-mock-123"
            raise

    async def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> list[dict[str, str]]:
        from app.core.config import settings

        try:
            loop = asyncio.get_running_loop()

            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            if not response.data:
                return []

            # Inverte para ordem cronológica (mais antiga → mais recente)
            messages = [
                {"role": row["role"], "content": row["content"]}
                for row in reversed(response.data)
            ]
            return messages

        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: get_recent_messages falhou ({e}). Retornando lista vazia.")
                return []
            raise

    async def save_citations(
        self,
        message_id: str,
        citations: list[CitationDraft]
    ) -> None:
        if not citations:
            return
            
        loop = asyncio.get_running_loop()
        
        # Formata o payload de inserção em lote
        payload = []
        for idx, cit in enumerate(citations):
            # No Supabase o campo é pdf_name. Salvamos o nome do livro
            payload.append({
                "message_id": message_id,
                "pdf_name": cit.book_name,
                "page": cit.page,
                "snippet": cit.snippet,
                "sort_order": idx
            })
        try:
            await loop.run_in_executor(
                None,
                lambda: self.client.table("citations")
                .insert(payload)
                .execute()
            )
        except Exception as e:
            from app.core.config import settings
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase citations table not reachable ({e}). Mocking citation save.")
                return
            raise e

    async def get_second_chamber_catalog(self) -> list[dict]:
        from app.core.config import settings
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("pdf_catalog")
                .select("book_name, author, chamber")
                .eq("chamber", 2)
                .execute()
            )
            return response.data or []
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: get_second_chamber_catalog falhou ({e}). Retornando mock em dev.")
                return [
                    {"book_name": "Los Misterios Ocultos del Divino Daimon", "author": "Juan Capasso", "chamber": 2},
                    {"book_name": "As Joias do Dragão Amarelo - Tomo I", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "Os Sacramentos da Câmara Nupcial", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "LA LEY DEL DESTINO (Conv. diciembre 2002 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "CIENCIA Y RELIGION - EL ULTIMATUM (Convivencia Semana Santa 2003 - ML", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL AMOR Y LA PAZ (Convivencia agosto 2003 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "MENSAJE DE AÑO NUEVO 1994", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "CONFERENCIAS INEDITAS (Recopilación 27 Cátedras)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "ALMA BLANCA (Convivencia Semana Santa 2002 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "MENSAJE DE NAVIDAD 1997", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "PSICOANALISIS I (Conf. Entre Febrero Y Abril 1984 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "ANALES Y FUNDAMENTOS CONGRESO GNOSTICO INTERNACIONAL 1995", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "DIALOGOS ESOTERICOS", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "LA MUERTE Y EL DESPERTAR (Conv. Bogotá junio 2004)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL ORIGEN DEL MONASTERIO LUMEN DE LUMINE 11 DE SEPTIEMBRE 2003", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "PSICOANALISIS II (Conf. entre febrero y abril 1984 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL REGRESO DE MOISES (Conv. Semana Santa 2004 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL HOMBRE HUMANO, DIVINO Y ESPIRITUAL (Conv. Nov 1994 - Sto Grial)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "MENSAJE DE AÑO NUEVO 1993  ( Libro En Donde Enseña Aspectos De Las Iniciaciones )", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL BARCO HACIA EL TRIUNFO (Conv. fevereiro 2004 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "LA IGLESIA RESTAURADA", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "LOS MISTERIOS DE ELEUSIS (Conf. en abril 2000 - MLL", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "DIALOGOS", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "LA MUJER EN SU CRISTIFICACION", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "EL EVANGELIO DE MOISES (Conv. agosto 2004 - MLL)", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "As Joias do Dragão Amarelo - Tomo III", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "HABLANDO CON EL MAESTRO (Recopilacion Llamados Telefonicos) Ampliado", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "PROVERBIOS DE LA PSICOLOGIA I, II Y III", "author": "V.M. Lakhsmi Daimon", "chamber": 2},
                    {"book_name": "As Joias do Dragão Amarelo - Tomo II", "author": "V.M. Lakhsmi Daimon", "chamber": 2}
                ]
            raise e
