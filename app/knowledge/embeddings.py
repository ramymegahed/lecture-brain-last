from typing import List

from app.core.clients import openai_client


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of text chunks using OpenAI API (async).
    Uses the shared openai_client singleton from app.core.clients.
    """
    if not texts:
        return []

    try:
        response = await openai_client.embeddings.create(
            input=texts,
            model="text-embedding-ada-002"  # outputs 1536-dim vectors
        )
        return [data.embedding for data in response.data]
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        raise
