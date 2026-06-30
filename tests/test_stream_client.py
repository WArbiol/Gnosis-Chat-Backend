import asyncio
import json
import httpx

# Códigos ANSI para colorir o terminal
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

async def test_stream_chat():
    url = "http://localhost:8000/api/v1/chat/ask"
    
    # Simula o payload que o Flutter enviará
    payload = {
        "query": "Quem é o demiurgo na visão gnóstica e como nos libertamos dele?",
        "conversation_id": None,
        "ui_filters": {
            "books": [],
            "authors": [],
            "chamber_levels": [1],
            "chapters": []
        }
    }
    
    # Simula cabeçalho de autenticação (usuário de teste mockado)
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-token-123"  # O middleware mocka o user com qualquer token em dev
    }

    print(f"\n{BOLD}{CYAN}=== Iniciando Teste de Stream RAG Agêntico ==={RESET}")
    print(f"{BOLD}Endpoint:{RESET} {url}")
    print(f"{BOLD}Pergunta:{RESET} {payload['query']}\n")
    print(f"{BOLD}Aguardando resposta do servidor...{RESET}\n")

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    timeout = httpx.Timeout(60.0, connect=10.0)

    try:
        async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    print(f"{RED}Erro do Servidor (Status {response.status_code}):{RESET}")
                    error_content = await response.aread()
                    print(error_content.decode())
                    return

                # Ler o stream SSE linha por linha
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_block, buffer = buffer.split("\n\n", 1)
                        
                        # Processar o bloco de evento do SSE
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
                            
                        # Mapear e printar os eventos conforme o tipo
                        if event_type == "status":
                            try:
                                data_json = json.loads(data_content)
                                agent = data_json.get("agent", "unknown")
                                msg = data_json.get("message", "")
                                print(f"\n{BOLD}{BLUE}[Agente: {agent.upper()}]{RESET} {msg}")
                            except Exception:
                                print(f"\n{BOLD}{BLUE}[Agente: {event_type.upper()}]{RESET} {data_content}")
                                
                        elif event_type == "token":
                            # Tokens da resposta fluindo em tempo real
                            print(f"{GREEN}{data_content}{RESET}", end="", flush=True)
                            
                        elif event_type == "final":
                            print("\n")
                            print(f"{BOLD}{CYAN}=== Payload Final Recebido ==={RESET}")
                            try:
                                final_json = json.loads(data_content)
                                print(f"{BOLD}Conversa ID:{RESET} {final_json.get('conversation_id')}")
                                print(f"{BOLD}Mensagem ID:{RESET} {final_json.get('message_id')}")
                                print(f"{BOLD}Rota Decidida:{RESET} {final_json.get('route')}")
                                
                                recap = final_json.get('recap')
                                if recap:
                                    print(f"{BOLD}Resumo (Recap):{RESET} {YELLOW}{recap}{RESET}")
                                    
                                citations = final_json.get('citations', [])
                                if citations:
                                    print(f"\n{BOLD}Fontes Citadas ({len(citations)}):{RESET}")
                                    for idx, cit in enumerate(citations, 1):
                                        print(f"  {idx}. {BOLD}{cit.get('book_name')}{RESET} (pág. {cit.get('page')}) - Autor: {cit.get('author')}")
                                        snippet = cit.get('snippet', '')
                                        # Truncar snippet para visualização limpa
                                        if len(snippet) > 100:
                                            snippet = snippet[:100] + "..."
                                        print(f"     {YELLOW}\"{snippet}\"{RESET}")
                            except Exception as e:
                                print(f"{RED}Erro ao parsear payload final: {e}{RESET}")
                                print(data_content)
                                
                        elif event_type == "error":
                            print(f"\n{RED}{BOLD}[ERRO] {data_content}{RESET}")

    except httpx.ConnectError:
        print(f"{RED}Erro de Conexão: O servidor FastAPI está rodando na porta 8000? Certifique-se de iniciar o uvicorn.{RESET}")
    except Exception as e:
        print(f"\n{RED}Ocorreu um erro durante a requisição de teste: {e}{RESET}")

if __name__ == "__main__":
    asyncio.run(test_stream_chat())
