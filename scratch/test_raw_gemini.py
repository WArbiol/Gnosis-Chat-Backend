import asyncio
import os
from typing import Literal
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

class OrchestratorDecision(BaseModel):
    thought: str = Field(..., description="Análise lógica")
    next_step: Literal["researcher", "writer", "direct_response", "ask_user"] = Field(..., description="Decisão")
    sub_queries: list[str] = Field(default=[])

async def test_async_json():
    print("Testing async generate_content with gemini-3.5-flash JSON and response_schema...")
    client = genai.Client()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=OrchestratorDecision,
        temperature=0.1,
    )
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash",
            contents="User query: Quem é Lúcifer?",
            config=config
        )
        print(f"Async JSON response: {response.text}")
    except Exception as e:
        print(f"Async JSON failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_async_json())
