from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

from app.database.mongodb import init_db, close_db
from app.knowledge.video_processor import sweep_orphaned_audio_files
from app.routes.auth_routes import router as auth_router
from app.routes.subject_routes import router as subject_router
from app.routes.lecture_routes import router as lecture_router
from app.routes.knowledge_routes import router as knowledge_router
from app.routes.ai_routes import router as ai_router
from app.routes.admin_routes import router as admin_router
from app.auth.init_admin import create_initial_admin


# ---------------------------------------------------------------------------
# Rate Limiter Setup
# ---------------------------------------------------------------------------
# The Limiter is attached to app.state.limiter so that the @limiter.limit()
# decorators in auth_routes.py can resolve it at request time.
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await create_initial_admin()
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

# ---------------------------------------------------------------------------
# Attach SlowAPI state — MUST happen before routers are included
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
# ALLOWED_ORIGINS is read from the environment so production and development
# use different values without code changes.
#
# Production (Railway):  set ALLOWED_ORIGINS=https://lecture-brain.vercel.app
# Development (.env):    set ALLOWED_ORIGINS=http://localhost:3000
#
# Fallback to localhost for local dev if env var is not set.
# NOTE: allow_origins=["*"] combined with allow_credentials=True is INVALID
# per the CORS spec and will be actively rejected by browsers. We must list
# explicit origins when credentials are in play.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [origin.strip().rstrip("/") for origin in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(subject_router)
app.include_router(lecture_router)
app.include_router(knowledge_router)
app.include_router(ai_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    return {"message": "Welcome to Lecture Brain API"}
