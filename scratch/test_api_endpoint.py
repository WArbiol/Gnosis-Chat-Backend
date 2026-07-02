import asyncio
import httpx
import json

async def main():
    url = "http://localhost:8080/api/v1/chat/ask"
    payload = {
        "query": "Quem é Lúcifer?",
        "conversation_id": None,
        "ui_filters": {}
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-user-token"
    }
    
    print(f"Fazendo POST para {url}...")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"Status da resposta: {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    print(f"Erro do servidor (body): {body.decode(errors='ignore')}")
                    return
                
                async for line in response.aiter_lines():
                    if line:
                        print(f"Linha recebida: {line}")
    except Exception as e:
        print(f"Ocorreu um erro na requisição HTTP: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
