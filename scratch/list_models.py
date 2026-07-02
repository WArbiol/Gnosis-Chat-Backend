import os
import sys
from google import genai
from dotenv import load_dotenv

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, ".env"))

def main():
    api_key = os.getenv("GOOGLE_API_KEY")
    print(f"Usando chave de API terminada em FfPY: {api_key[-4:] if api_key else 'None'}")
    
    client = genai.Client(api_key=api_key)
    print("\nModelos disponíveis:")
    try:
        for model in client.models.list():
            if "gemini" in model.name:
                print(f"- {model.name}")
    except Exception as e:
        print(f"Erro ao listar modelos: {e}")

if __name__ == "__main__":
    main()
