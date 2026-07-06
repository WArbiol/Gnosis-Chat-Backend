import asyncio
import time
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class SimpleSchema(BaseModel):
    decision: str = Field(..., description="A simple decision")
    reason: str = Field(..., description="Reason for decision")

async def test_model(model_name: str):
    print(f"\nBenchmarking model: {model_name}...")
    client = genai.Client()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SimpleSchema,
        temperature=0.1,
    )
    
    start = time.time()
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents="Decida se devemos ir para a praia sabendo que está chovendo.",
            config=config
        )
        elapsed = time.time() - start
        print(f"[{model_name}] Response: {response.text.strip()}")
        print(f"[{model_name}] Time taken: {elapsed:.2f}s")
    except Exception as e:
        print(f"[{model_name}] Failed: {e}")

async def main():
    models = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    for model in models:
        await test_model(model)

if __name__ == "__main__":
    asyncio.run(main())
