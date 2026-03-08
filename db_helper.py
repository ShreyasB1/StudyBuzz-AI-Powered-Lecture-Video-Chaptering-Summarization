"""Database helper functions for StudyBuzz.

Uses SQLite + sqlite-vec for vector search.
SQLite runs in-process inside the Flask container — no separate DB container
needed, which avoids all PACE filesystem/permission restrictions.
"""
import os
import sqlite3
import hashlib
import struct
from datetime import datetime
from typing import Optional, List, Dict

# SQLite database file path (inside the Flask container's mounted output volume)
DB_PATH = os.getenv("SQLITE_DB_PATH", "/app/output/studybuzz.db")


def _load_vec_extension(conn: sqlite3.Connection):
    """Load the sqlite-vec extension for vector search."""
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as e:
        print(f"Warning: sqlite-vec not available: {e}")


def get_connection() -> sqlite3.Connection:
    """Get a SQLite database connection with vec extension loaded."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _load_vec_extension(conn)
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lecture_videos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            video_hash  TEXT NOT NULL UNIQUE,
            done_processing INTEGER NOT NULL DEFAULT 0,
            note        TEXT,
            folder_path TEXT NOT NULL,
            video_name  TEXT NOT NULL,
            video_date  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chapter_embeddings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            video_hash   TEXT NOT NULL REFERENCES lecture_videos(video_hash) ON DELETE CASCADE,
            chapter_path TEXT NOT NULL,
            model_name   TEXT NOT NULL,
            embedding    BLOB NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (video_hash, chapter_path, model_name)
        );
    """)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chapter_embeddings_vec
            USING vec0(embedding float[1536]);
        """)
    except Exception:
        pass  # sqlite-vec not available, vector search disabled
    conn.commit()


def _serialize_embedding(embedding: List[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def _row_to_dict(row) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


def compute_video_hash(video_path: str) -> str:
    """Compute SHA256 hash of a video file."""
    sha256 = hashlib.sha256()
    with open(video_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def insert_video(video_hash: str, folder_path: str, video_name: str, note: Optional[str] = None) -> int:
    """Insert or update a video record. Returns the video ID."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO lecture_videos (video_hash, folder_path, video_name, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_hash) DO UPDATE
            SET folder_path = excluded.folder_path,
                video_name  = excluded.video_name,
                note        = excluded.note
            RETURNING id;
            """,
            (video_hash, folder_path, video_name, note)
        )
        row = cur.fetchone()
        conn.commit()
        return row[0]


def mark_video_processed(video_hash: str, note: Optional[str] = None):
    """Mark a video as fully processed."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE lecture_videos SET done_processing = 1, note = COALESCE(?, note) WHERE video_hash = ?;",
            (note, video_hash)
        )
        conn.commit()


def get_video_by_hash(video_hash: str) -> Optional[Dict]:
    """Retrieve a video record by hash."""
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM lecture_videos WHERE video_hash = ?;", (video_hash,))
        return _row_to_dict(cur.fetchone())


def list_all_videos() -> List[Dict]:
    """List all videos ordered by date descending."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, video_hash, video_name, folder_path, done_processing, video_date, note FROM lecture_videos ORDER BY video_date DESC;"
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def insert_chapter_embedding(video_hash: str, chapter_path: str, model_name: str, embedding: List[float]) -> int:
    """Insert or update a chapter embedding. Returns the embedding ID."""
    blob = _serialize_embedding(embedding)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO chapter_embeddings (video_hash, chapter_path, model_name, embedding)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_hash, chapter_path, model_name)
            DO UPDATE SET embedding = excluded.embedding
            RETURNING id;
            """,
            (video_hash, chapter_path, model_name, blob)
        )
        row = cur.fetchone()
        embedding_id = row[0]
        try:
            conn.execute(
                "INSERT OR REPLACE INTO chapter_embeddings_vec(rowid, embedding) VALUES (?, ?);",
                (embedding_id, blob)
            )
        except Exception:
            pass
        conn.commit()
        return embedding_id


def search_similar_chapters(query_embedding: List[float], model_name: str, limit: int = 5) -> List[Dict]:
    """Search for similar chapters using sqlite-vec."""
    blob = _serialize_embedding(query_embedding)
    with get_connection() as conn:
        try:
            cur = conn.execute(
                """
                SELECT ce.id, ce.video_hash, ce.chapter_path, ce.model_name,
                       lv.video_name, lv.folder_path, v.distance
                FROM chapter_embeddings_vec v
                JOIN chapter_embeddings ce ON ce.id = v.rowid
                JOIN lecture_videos lv ON lv.video_hash = ce.video_hash
                WHERE v.embedding MATCH ? AND ce.model_name = ? AND k = ?
                ORDER BY v.distance;
                """,
                (blob, model_name, limit)
            )
            return [_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"Vector search not available: {e}")
            return []
