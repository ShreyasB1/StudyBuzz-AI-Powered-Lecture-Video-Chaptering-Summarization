"""Database helper functions for StudyBuzz."""
import os
import hashlib
from datetime import datetime
from typing import Optional, List, Dict
import psycopg
from psycopg.rows import dict_row

# Database configuration
DB_NAME = os.getenv("VIP_DB_NAME", "vip_db")
DB_USER = os.getenv("VIP_DB_USER", "postgres")
DB_PASSWORD = os.getenv("VIP_DB_PASSWORD", "postgres")
DB_HOST = os.getenv("VIP_DB_HOST", "localhost")
DB_PORT = int(os.getenv("VIP_DB_PORT", "5432"))


def get_connection():
    """Get a database connection."""
    conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    return psycopg.connect(conn_str, row_factory=dict_row)


def compute_video_hash(video_path: str) -> str:
    """Compute SHA256 hash of a video file."""
    sha256 = hashlib.sha256()
    with open(video_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def insert_video(
    video_hash: str,
    folder_path: str,
    video_name: str,
    note: Optional[str] = None
) -> int:
    """
    Insert a new video record into the database.
    Returns the video ID.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lecture_videos (video_hash, folder_path, video_name, note)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (video_hash) DO UPDATE
                SET folder_path = EXCLUDED.folder_path,
                    video_name = EXCLUDED.video_name,
                    note = EXCLUDED.note
                RETURNING id;
                """,
                (video_hash, folder_path, video_name, note)
            )
            result = cur.fetchone()
            conn.commit()
            return result["id"]


def mark_video_processed(video_hash: str, note: Optional[str] = None):
    """Mark a video as fully processed."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE lecture_videos
                SET done_processing = TRUE,
                    note = COALESCE(%s, note)
                WHERE video_hash = %s;
                """,
                (note, video_hash)
            )
            conn.commit()


def get_video_by_hash(video_hash: str) -> Optional[Dict]:
    """Retrieve video record by hash."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM lecture_videos
                WHERE video_hash = %s;
                """,
                (video_hash,)
            )
            return cur.fetchone()


def list_all_videos() -> List[Dict]:
    """List all videos in the database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, video_hash, video_name, folder_path, 
                       done_processing, video_date, note
                FROM lecture_videos
                ORDER BY video_date DESC;
                """
            )
            return cur.fetchall()


def insert_chapter_embedding(
    video_hash: str,
    chapter_path: str,
    model_name: str,
    embedding: List[float]
) -> int:
    """
    Insert a chapter embedding into the database.
    Returns the embedding ID.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chapter_embeddings (video_hash, chapter_path, model_name, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (video_hash, chapter_path, model_name) 
                DO UPDATE SET embedding = EXCLUDED.embedding
                RETURNING id;
                """,
                (video_hash, chapter_path, model_name, embedding)
            )
            result = cur.fetchone()
            conn.commit()
            return result["id"]


def search_similar_chapters(
    query_embedding: List[float],
    model_name: str,
    limit: int = 5
) -> List[Dict]:
    """
    Search for similar chapters using cosine similarity.
    Returns list of chapters sorted by similarity.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    ce.id,
                    ce.video_hash,
                    ce.chapter_path,
                    lv.video_name,
                    lv.folder_path,
                    ce.embedding <=> %s::vector AS distance
                FROM chapter_embeddings ce
                JOIN lecture_videos lv ON ce.video_hash = lv.video_hash
                WHERE ce.model_name = %s
                ORDER BY ce.embedding <=> %s::vector
                LIMIT %s;
                """,
                (query_embedding, model_name, query_embedding, limit)
            )
            return cur.fetchall()
