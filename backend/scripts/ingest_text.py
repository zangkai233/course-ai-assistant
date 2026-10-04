"""Ingest a UTF-8 text file into PostgreSQL/pgvector.

Run from backend after completing your own environment setup:
python -m scripts.ingest_text path/to/course.txt --source "Lecture 1"
"""

import argparse
import asyncio
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.redis import close_redis
from app.db.models import CourseChunk
from app.db.session import SessionLocal, close_db, init_db
from app.services.rag import embed_text


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk size must be positive; overlap must be smaller than chunk size.")
    chunks = []
    for start in range(0, len(text), chunk_size - overlap):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks


async def ingest(args: argparse.Namespace) -> None:
    source = args.source or args.path.name
    if len(source) > 500:
        raise ValueError("Source name must be 500 characters or fewer.")
    content = args.path.read_text(encoding="utf-8")
    chunks = chunk_text(content, args.chunk_size, args.overlap)
    try:
        await init_db()
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            async with SessionLocal() as session:
                for index, chunk in enumerate(chunks, start=1):
                    embedding = await embed_text(client, chunk)
                    session.add(CourseChunk(source=source, content=chunk, embedding=embedding))
                    if index % 50 == 0:
                        await session.commit()
                    print(f"Ingested chunk {index}/{len(chunks)}")
                await session.commit()
        print(f"Finished: {len(chunks)} chunks from {source}")
    finally:
        await close_redis()
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest UTF-8 course text into pgvector.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--source", default=None)
    parser.add_argument("--chunk-size", type=int, default=1500)
    parser.add_argument("--overlap", type=int, default=200)
    asyncio.run(ingest(parser.parse_args()))
