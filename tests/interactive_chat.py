import asyncio
import json
import sys
import httpx

# Cores ANSI
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

BASE_URL = "http://localhost:8000/api/v1/chat"

async def read_stream(response, current_conversation_id):
    """Lê o stream de eventos SSE e retorna se o fluxo pausou em HIL, a resposta e o ID da conversa."""
    buffer = ""
    is_hil = False
    clarification_question = ""
    ans = ""
    conv_id = current_conversation_id

    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            event_block, buffer = buffer.split("\n\n", 1)
            lines = event_block.strip().split("\n")
            event_type = None
            data_content = ""
            
            for line in lines:
                if line.startswith("event:"):
                    event_type = line.replace("event:", "").strip()
                elif line.startswith("data:"):
                    data_content = line.replace("data:", "").strip()
            
            if not event_type or not data_content:
                continue
                
            if event_type == "status":
                try:
                    data_json = json.loads(data_content)
                    agent = data_json.get("agent", "unknown")
                    msg = data_json.get("message", "")
                    print(f"\n{BOLD}{BLUE}[{agent.upper()}]{RESET} {msg}")
                except Exception:
                    print(f"\n{BOLD}{BLUE}[{event_type.upper()}]{RESET} {data_content}")
                    
            elif event_type == "token":
                print(f"{GREEN}{data_content}{RESET}", end="", flush=True)
                ans += data_content
                
            elif event_type == "final":
                print("\n")
                try:
                    final_json = json.loads(data_content)
                    conv_id = final_json.get("conversation_id")
                    is_hil = final_json.get("is_hil", False)
                    
                    if is_hil:
                        clarification_question = final_json.get("answer", "")
                    else:
                        # Se não recebemos tokens de streaming (ex: resposta direta do orquestrador),
                        # exibimos a resposta final completa que veio no payload.
                        if not ans.strip():
                            print(f"{GREEN}{final_json.get('answer', '')}{RESET}\n")
                        
                        citations = final_json.get("citations", [])
                        if citations:
                            print(f"{BOLD}Citações das Obras:{RESET}")
                            for idx, cit in enumerate(citations, 1):
                                print(f"  [{idx}] {BOLD}{cit.get('book_name')}{RESET} (pág. {cit.get('page')}) - {cit.get('author')}")
                except Exception as e:
                    print(f"{RED}Erro ao parsear dados finais: {e}{RESET}")
                    
            elif event_type == "error":
                print(f"\n{RED}{BOLD}[ERRO] {data_content}{RESET}")
                
    return is_hil, clarification_question, conv_id

async def run_interactive_chat():
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-user-token"
    }
    
    conversation_id = None
    print(f"{BOLD}{CYAN}=================================================={RESET}")
    print(f"{BOLD}{CYAN}    Gnosis Chat - CLI Interativa do Agente        {RESET}")
    print(f"{BOLD}{CYAN}=================================================={RESET}")
    print("Digite 'sair' para encerrar a sessão.\n")

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    timeout = httpx.Timeout(120.0, connect=10.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        while True:
            try:
                # Entrada do usuário
                query = input(f"\n{BOLD}{YELLOW}Você:{RESET} ")
                if query.strip().lower() == "sair":
                    print(f"\n{BOLD}{CYAN}Sessão encerrada. Até logo!{RESET}")
                    break
                if not query.strip():
                    continue

                # Rota padrão para fazer pergunta ao RAG
                url = f"{BASE_URL}/ask"
                payload = {
                    "query": query,
                    "conversation_id": conversation_id,
                    "ui_filters": {
                        "books": [],
                        "authors": [],
                        "chamber_levels": [1],
                        "chapters": []
                    }
                }

                # Disparar request e ler stream
                print(f"{BOLD}{CYAN}Enviando pergunta...{RESET}")
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        print(f"{RED}Erro {response.status_code}:{RESET}")
                        print((await response.aread()).decode())
                        continue

                    is_hil, clarification_question, conversation_id = await read_stream(response, conversation_id)

                # Loop de Intervenção Humana (HIL)
                while is_hil:
                    print(f"\n{BOLD}{CYAN}=== Pausa de Clarificação do Agente (HIL) ==={RESET}")
                    print(f"{BOLD}Pergunta do Agente:{RESET} {CYAN}{clarification_question}{RESET}")
                    
                    clarification_response = input(f"\n{BOLD}{YELLOW}Sua Resposta:{RESET} ")
                    if clarification_response.strip().lower() == "sair":
                        sys.exit(0)

                    # Endpoint de clarificação
                    clarify_url = f"{BASE_URL}/clarify"
                    clarify_payload = {
                        "conversation_id": conversation_id,
                        "user_response": clarification_response
                    }

                    print(f"{BOLD}{CYAN}Enviando esclarecimento...{RESET}")
                    async with client.stream("POST", clarify_url, json=clarify_payload, headers=headers) as response:
                        if response.status_code != 200:
                            print(f"{RED}Erro {response.status_code}:{RESET}")
                            print((await response.aread()).decode())
                            break

                        is_hil, clarification_question, conversation_id = await read_stream(response, conversation_id)

            except httpx.ConnectError:
                print(f"{RED}Erro de Conexão: O servidor FastAPI está rodando na porta 8000? Inicie o uvicorn.{RESET}")
            except KeyboardInterrupt:
                print(f"\n{BOLD}{CYAN}Sessão encerrada pelo usuário.{RESET}")
                break
            except Exception as e:
                print(f"{RED}Erro: {e}{RESET}")

if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_chat())
    except KeyboardInterrupt:
        pass
