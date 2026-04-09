import os
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from dotenv import load_dotenv

# Import models to initialize Beanie
from app.models.user import User
from app.models.subject import Subject
from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.models.knowledge_card import KnowledgeCard
from app.models.chat_log import ChatLog
from app.models.subject_analytics import SubjectAnalytics

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "lecture_brain")

client: AsyncIOMotorClient = None

async def init_db():
    """Initialize database connection and ODM (Beanie)"""
    global client
    client = AsyncIOMotorClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=False,
        serverSelectionTimeoutMS=10000,  # 10 second timeout
    )
    database = client[DB_NAME]
    
    await init_beanie(
        database=database,
        document_models=[
            User,
            Subject,
            Lecture,
            KnowledgeChunk,
            KnowledgeCard,
            ChatLog,
            SubjectAnalytics
        ]
    )

async def close_db():
    if client:
        client.close()

async def vector_search(query_embedding: list[float], limit: int = 5, lecture_id: str = None) -> list[dict]:
    """
    Perform a MongoDB Atlas Vector Search using the $vectorSearch aggregation stage.
    Assumes an Atlas Search Index named `vector_index` is configured with 1536 dimensions (OpenAI).
    """
    if not client:
        raise Exception("Database client not initialized")
        
    db = client[DB_NAME]
    collection = db["knowledge_chunks"] # Using raw collection for aggregation
    
    # Base pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": limit * 10,
                "limit": limit
            }
        }
    ]
    
    # If we want to filter by a specific lecture
    if lecture_id:
        pipeline[0]["$vectorSearch"]["filter"] = {
            "lecture_id": { "$eq": lecture_id } # Assuming str conversion, or ObjectId depending on schema
        }
        
    # Project the score alongside document fields
    pipeline.append({
        "$project": {
            "_id": 1,
            "text": 1,
            "lecture_id": 1,
            "page_number": 1,
            "score": { "$meta": "vectorSearchScore" }
        }
    })

    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=limit)
    return results
