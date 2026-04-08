import os
import asyncio
import glob
from beanie import PydanticObjectId
import yt_dlp
import whisper

from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.knowledge.chunking import chunk_document, clean_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card

# ---------------------------------------------------------------------------
# Whisper model cache — loaded once on first use, reused for all subsequent
# video processing tasks. Using "small" for better transcription accuracy.
# ---------------------------------------------------------------------------
_whisper_model = None


def get_whisper_model() -> whisper.Whisper:
    """
    Lazy singleton for the Whisper model.
    Loads from disk on first call (~250 MB for 'small'), then returns the
    cached instance for every subsequent call — no repeated disk I/O.
    """
    global _whisper_model
    if _whisper_model is None:
        print("Loading Whisper 'small' model (first video upload)...")
        _whisper_model = whisper.load_model("small")
        print("Whisper model ready.")
    return _whisper_model


def sweep_orphaned_audio_files(upload_dir: str = "uploads") -> None:
    """
    Delete any leftover *_audio.mp3 files from a previous crashed process.
    Call this once during application startup via the lifespan hook in main.py.
    """
    pattern = os.path.join(upload_dir, "*_audio.mp3")
    for orphan in glob.glob(pattern):
        try:
            os.remove(orphan)
            print(f"Cleaned up orphaned audio file: {orphan}")
        except OSError:
            pass  # Already gone — ignore


def fetch_subtitles(video_url: str) -> str | None:
    """Try to get auto or manual subtitles via yt-dlp."""
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


def _download_and_transcribe(url: str, lecture_id: str) -> str:
    """
    Synchronous function to download audio and transcribe via Whisper.
    Audio is written to a temporary MP3 file and deleted in a try/finally
    block, guaranteeing cleanup even if transcription raises an exception.
    """
    # Fast path: use existing subtitles if available
    transcript = fetch_subtitles(url)
    if transcript:
        return transcript

    # Slow path: download audio → transcribe → delete
    audio_path = f"uploads/{lecture_id}_audio"
    mp3_file = audio_path + ".mp3"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_path + ".%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        model = get_whisper_model()  # cached — no re-loading
        result = model.transcribe(mp3_file)
        return result.get("text", "")
    finally:
        # Guaranteed cleanup — runs on both success AND exception
        if os.path.exists(mp3_file):
            os.remove(mp3_file)


async def process_video_background(lecture_id: str, url: str, extract_frames: bool = False):
    """
    Background task to process a video (YouTube etc.):
    1. Attempt subtitle extraction via yt-dlp
    2. Fallback: download audio → Whisper transcription (temp MP3, always cleaned up)
    3. Chunk text → embed → save KnowledgeChunks to MongoDB
    4. Generate KnowledgeCard (global context)
    5. Update Lecture status
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        print(f"Lecture {lecture_id} not found during video processing.")
        return

    try:
        # 1 & 2: Download and transcribe in a thread (blocking operation)
        text = await asyncio.to_thread(_download_and_transcribe, url, lecture_id)

        if not text.strip():
            raise ValueError("Transcription returned empty text.")

        # 3. Chunk & Embed
        cleaned_text = clean_text(text)
        pages = [{"page_number": 1, "text": cleaned_text}]
        chunks = chunk_document(pages)

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

        # 4. Generate Knowledge Card
        sample_text = text[:15000]
        await generate_and_save_knowledge_card(lecture_id, sample_text)

        # 5. Update status
        for source in lecture.sources:
            if source.url == url:
                source.status = "completed"
        lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
        await lecture.save()

    except Exception as e:
        print(f"Error processing video {url}: {e}")
        for source in lecture.sources:
            if source.url == url:
                source.status = "failed"
                source.error = str(e)
        lecture.status = "failed"
        await lecture.save()
