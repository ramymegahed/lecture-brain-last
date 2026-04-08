from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.database.mongodb import init_db, close_db
from app.knowledge.video_processor import sweep_orphaned_audio_files
from app.routes.auth_routes import router as auth_router
from app.routes.subject_routes import router as subject_router
from app.routes.lecture_routes import router as lecture_router
from app.routes.knowledge_routes import router as knowledge_router
from app.routes.ai_routes import router as ai_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    sweep_orphaned_audio_files()  # Clean any MP3s left by a previous crash
    yield
    # Shutdown
    await close_db()

app = FastAPI(
    title="Lecture Brain API",
    description="AI-powered Educational SaaS Backend with RAG capabilities.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(subject_router)
app.include_router(lecture_router)
app.include_router(knowledge_router)
app.include_router(ai_router)

@app.get("/")
async def root():
    return {"message": "Welcome to Lecture Brain API"}
