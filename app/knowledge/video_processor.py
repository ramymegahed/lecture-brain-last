import os
import asyncio
import glob
import logging
import io
import math
from beanie import PydanticObjectId

logger = logging.getLogger(__name__)
import yt_dlp

from app.core.clients import openai_client
from app.models.lecture import Lecture, update_job_status
from app.models.knowledge import KnowledgeChunk
from app.knowledge.chunking import chunk_document, clean_text, sample_document_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card

# ---------------------------------------------------------------------------
# Whisper API Configuration
# ---------------------------------------------------------------------------
# We use OpenAI's hosted Whisper API (whisper-1) instead of running the model
# locally. This decision is driven by hard resource constraints:
#
#   Railway Free Tier RAM:         0.5 GB
#   whisper 'small' model RAM:     ~2 GB  → 4× over limit → guaranteed OOM kill
#   whisper 'tiny' model RAM:      ~1 GB  → 2× over limit → OOM kill
#   OpenAI Whisper API RAM usage:  0 MB   → audio is processed on OpenAI servers
#
# Cost: $0.006/min. A 60-min lecture ≈ $0.36. Acceptable for a live demo.
# The API has a 25 MB per-request limit; audio is chunked automatically below.

WHISPER_CHUNK_SIZE_MB = 24          # Stay safely under the 25 MB API hard limit
WHISPER_CHUNK_SIZE_BYTES = WHISPER_CHUNK_SIZE_MB * 1024 * 1024


def sweep_orphaned_audio_files(upload_dir: str = "uploads") -> None:
    """
    Delete any leftover *_audio.mp3 files from a previous crashed process.
    Call this once during application startup via the lifespan hook in main.py.
    """
    pattern = os.path.join(upload_dir, "*_audio.mp3")
    for orphan in glob.glob(pattern):
        try:
            os.remove(orphan)
            logger.info(f"Cleaned up orphaned audio file: {orphan}")
        except OSError:
            pass  # Already gone — ignore


def fetch_subtitles(video_url: str) -> str | None:
    """Try to get auto or manual subtitles via yt-dlp (zero RAM, zero API cost)."""
    ydl_opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "outtmpl": "uploads/%(id)s",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id", "")
            sub_file = f"uploads/{video_id}.en.vtt"
            if os.path.exists(sub_file):
                with open(sub_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                os.remove(sub_file)
                return _parse_vtt(raw)
    except Exception:
        pass
    return None


def _parse_vtt(vtt_content: str) -> str:
    """Extract plain text from VTT subtitle file."""
    import re
    lines = vtt_content.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        text_lines.append(line)
    return " ".join(text_lines)


async def _transcribe_audio_via_api(mp3_file: str) -> str:
    """
    Transcribe a local MP3 file using the OpenAI Whisper API (whisper-1).

    If the file exceeds WHISPER_CHUNK_SIZE_BYTES (~24 MB), it is split into
    chunks using raw byte boundaries. This is a simple byte-split, not
    silence-detection, so there may be a split mid-word at chunk boundaries —
    but the transcript is concatenated and downstream chunking handles it.
    """
    file_size = os.path.getsize(mp3_file)

    if file_size <= WHISPER_CHUNK_SIZE_BYTES:
        # Single-request path (most lecture audio files)
        with open(mp3_file, "rb") as f:
            response = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text"
            )
        return response if isinstance(response, str) else response.text

    # Chunked path for large files (> 24 MB)
    logger.info(f"Audio file {file_size / 1024 / 1024:.1f} MB exceeds limit, chunking...")
    num_chunks = math.ceil(file_size / WHISPER_CHUNK_SIZE_BYTES)
    full_transcript = []

    with open(mp3_file, "rb") as f:
        for i in range(num_chunks):
            chunk_bytes = f.read(WHISPER_CHUNK_SIZE_BYTES)
            if not chunk_bytes:
                break

            # Wrap chunk bytes in a named BytesIO so the API receives a filename
            chunk_buffer = io.BytesIO(chunk_bytes)
            chunk_buffer.name = f"chunk_{i}.mp3"

            logger.info(f"Transcribing chunk {i + 1}/{num_chunks}...")
            response = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=chunk_buffer,
                response_format="text"
            )
            transcript = response if isinstance(response, str) else response.text
            full_transcript.append(transcript)

    return " ".join(full_transcript)


def _download_audio(url: str, lecture_id: str) -> str:
    """
    Synchronous: downloads audio from a URL to a local MP3 file.
    Returns the path to the MP3 file. Caller is responsible for cleanup.
    """
    audio_path = f"uploads/{lecture_id}_audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_path + ".%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",   # Reduced from 192 — saves ~33% file size
        }],                               # with negligible transcription accuracy impact
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return audio_path + ".mp3"


async def process_video_background(lecture_id: str, url: str):
    """
    Background task to process a video (YouTube etc.):
    1. Attempt subtitle extraction via yt-dlp (free, zero API cost)
    2. Fallback: download audio → OpenAI Whisper API transcription
    3. Chunk text → embed → save KnowledgeChunks to MongoDB
    4. Generate KnowledgeCard (global context)
    5. Update Lecture status
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        logger.error(f"Lecture {lecture_id} not found during video processing.")
        return

    mp3_file = None
    try:
        await update_job_status(lecture_id, "upload_status", "completed")
        await update_job_status(lecture_id, "extraction_status", "processing")

        # 1. Fast path: use existing subtitles if available (YouTube auto-captions)
        text = await asyncio.to_thread(fetch_subtitles, url)

        if not text:
            # 2. Slow path: download audio → Whisper API transcription
            logger.info(f"No subtitles found for {url}, downloading audio for API transcription...")
            mp3_file = await asyncio.to_thread(_download_audio, url, lecture_id)
            text = await _transcribe_audio_via_api(mp3_file)

        if not text or not text.strip():
            raise ValueError("Transcription returned empty text.")

        await update_job_status(lecture_id, "extraction_status", "completed")

        # 3. Chunk & Embed
        # clean_text (regex) and chunk_document (while-loop) are CPU-bound.
        # Running them in a thread pool keeps the event loop free for other
        # uploads and HTTP requests during this stage.
        await update_job_status(lecture_id, "chunking_status", "processing")
        cleaned_text = await asyncio.to_thread(clean_text, text)
        del text  # release the raw transcription — could be MBs for a 1-hour lecture
        pages = [{"page_number": 1, "text": cleaned_text}]
        del cleaned_text  # chunker is about to consume pages; release the standalone copy
        chunks = await asyncio.to_thread(chunk_document, pages)
        del pages  # chunker has consumed pages; free before the embedding loop
        await update_job_status(lecture_id, "chunking_status", "completed")

        await update_job_status(lecture_id, "embedding_status", "processing")
        BATCH_SIZE = 100
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts_to_embed = [item["text"] for item in batch]
            embeddings = await get_embeddings(texts_to_embed)

            knowledge_chunks = [
                KnowledgeChunk(
                    lecture=lecture,
                    lecture_id=lecture_id,
                    text=item["text"],
                    page_number=item["page_number"],
                    embedding=embeddings[j],
                )
                for j, item in enumerate(batch)
            ]
            if knowledge_chunks:
                await KnowledgeChunk.insert_many(knowledge_chunks)
        await update_job_status(lecture_id, "embedding_status", "completed")

        # 4. Generate Knowledge Card
        # Re-derive the sample from already-processed chunks instead of the original
        # `text` variable (which has been freed). This avoids holding the full transcription
        # alongside all chunk objects simultaneously.
        await update_job_status(lecture_id, "card_generation_status", "processing")
        sample_text = sample_document_text(" ".join(c["text"] for c in chunks))
        await generate_and_save_knowledge_card(lecture_id, sample_text)
        await update_job_status(lecture_id, "card_generation_status", "completed")

        # 5. Update status
        for source in lecture.sources:
            if source.url == url:
                source.status = "completed"
        lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
        await lecture.save()

    except Exception as e:
        logger.error(f"Error processing video {url}: {e}", exc_info=True)
        await update_job_status(lecture_id, "extraction_status", "failed", error=str(e))
        for source in lecture.sources:
            if source.url == url:
                source.status = "failed"
                source.error = str(e)
        lecture.status = "failed"
        await lecture.save()

    finally:
        # Guaranteed cleanup — runs on both success AND exception
        if mp3_file and os.path.exists(mp3_file):
            os.remove(mp3_file)
            logger.info(f"Cleaned up audio file: {mp3_file}")
