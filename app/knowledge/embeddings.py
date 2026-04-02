import openai
import os
from typing import List

# Ensure OPENAI_API_KEY is loaded in environment
openai.api_key = os.getenv("OPENAI_API_KEY")

async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of text chunks using OpenAI API (async).
    """
    if not texts:
        return []
        
    try:
        # We use the new async client approach or httpx directly depending on openai library version.
        # Assuming modern openai>=1.0.0, we instantiate an async client.
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        
        response = await client.embeddings.create(
            input=texts,
            model="text-embedding-ada-002" # outputs 1536 dim vectors
        )
        
        return [data.embedding for data in response.data]
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        # In production, use appropriate logging and raise specific exceptions
        raise
