import os
import psycopg

# Basic config (can be overridden via env vars)
DB_NAME = os.getenv("VIP_DB_NAME", "vip_db")
DB_USER = os.getenv("VIP_DB_USER", "postgres")
DB_PASSWORD = os.getenv("VIP_DB_PASSWORD", "postgres")
DB_HOST = os.getenv("VIP_DB_HOST", "localhost")
DB_PORT = int(os.getenv("VIP_DB_PORT", "5432"))


def create_database_if_needed():
    """Create vip_db if it does not already exist."""
    conn_str = f"dbname=postgres user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
                print(f"Created database {DB_NAME!r}")
            else:
                print(f"Database {DB_NAME!r} already exists")


def init_schema():
    """Enable pgvector and create the two tables if missing."""
    conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("Ensured pgvector extension is enabled")

            # lecture_videos table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lecture_videos (
                    id              BIGSERIAL PRIMARY KEY,
                    video_hash      TEXT        NOT NULL UNIQUE,
                    done_processing BOOLEAN     NOT NULL DEFAULT FALSE,
                    note            TEXT,
                    folder_path     TEXT        NOT NULL,
                    video_name      TEXT        NOT NULL,
                    video_date      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            print("Ensured table lecture_videos exists")

            # chapter_embeddings table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chapter_embeddings (
                    id              BIGSERIAL PRIMARY KEY,
                    video_hash      TEXT        NOT NULL
                                    REFERENCES lecture_videos(video_hash)
                                    ON DELETE CASCADE,
                    chapter_path    TEXT        NOT NULL,
                    model_name      TEXT        NOT NULL,
                    embedding       VECTOR(1536) NOT NULL,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (video_hash, chapter_path, model_name)
                );
                """
            )
            print("Ensured table chapter_embeddings exists")

            # Optional ANN index
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS chapter_embeddings_embedding_idx
                    ON chapter_embeddings
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """
            )
            print("Ensured ANN index on chapter_embeddings.embedding exists")


def main():
    create_database_if_needed()
    init_schema()


if __name__ == "__main__":
    main()