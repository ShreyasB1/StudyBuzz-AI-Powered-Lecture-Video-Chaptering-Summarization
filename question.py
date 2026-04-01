"""
question.py – Multi-hop RAG question-answering pipeline.

Flow:
  1. Embed the user's question via Nemotron (port 8002).
  2. Retrieve the top-k chapter embeddings from pgvector.
  3. For each result, read the chapter transcript + summary and send it
     to the LLM (Mistral on port 8000) with the question, asking it to
     extract only the relevant information.  (All k requests run concurrently.)
  4. Collect all per-chapter LLM responses and send them as combined
     context in one final LLM request to produce the answer.
"""

import argparse
import asyncio
import json
import os

import openai
import psycopg

from init_db import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EMBED_BASE_URL = "http://localhost:8002/v1"
EMBED_MODEL = "nemotron"

LLM_BASE_URL = "http://localhost:8000/v1"
LLM_MODEL = "mistral-large"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_db_conn_str() -> str:
    return f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"


def _strip_think_tags(text: str) -> str:
    """Remove <think>…</think> wrapper that some models emit."""
    return text.split("</think>")[-1].strip()


def _extract_plain_text_from_vtt(content: str) -> str:
    """Return just the spoken text from a VTT file."""
    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def _load_chapter_content(folder_path: str, chapter_path: str) -> str:
    """Load transcript + summary for a chapter from disk.

    ``chapter_path`` is stored in the DB as ``{video_hash}/{chapter_folder}``.
    The base directory where chapters live is the ``folder_path`` recorded in
    ``lecture_videos``.
    """
    chapter_name = chapter_path.split("/", 1)[-1]
    chapter_dir = os.path.join(folder_path, chapter_name)

    parts: list[str] = []

    # Summary
    summary_path = os.path.join(chapter_dir, "summary.json")
    print(f"  Attempting to read summary: {summary_path}")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            # summary.json is {title: summary_text}
            for title, summary_text in summary_data.items():
                parts.append(f"Chapter: {title}\nSummary: {summary_text}")
        except Exception:
            pass

    # Transcript
    transcript_path = os.path.join(chapter_dir, "transcript.vtt")
    print(f"  Attempting to read transcript: {transcript_path}")
    if os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                raw = f.read()
            plain = _extract_plain_text_from_vtt(raw)
            if plain:
                parts.append(f"Transcript:\n{plain}")
        except Exception:
            pass

    if not parts:
        # Fallback: just mention the path so the LLM knows what result this is
        parts.append(f"[No content found on disk for chapter path: {chapter_path}]")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------
async def search_top_k(query: str, limit: int = 5) -> list[dict]:
    """Return the top-k chapter matches with metadata + on-disk content."""

    # 1. Generate query embedding
    print(f"Generating embedding for: '{query}'...")
    client = openai.AsyncOpenAI(base_url=EMBED_BASE_URL, api_key="empty")
    response = await client.embeddings.create(model=EMBED_MODEL, input=query)
    query_vector = response.data[0].embedding

    # 2. Query pgvector (psycopg is sync; run in a thread to avoid blocking)
    print("Searching database...")
    results: list[dict] = []

    def _db_query():
        rows = []
        with psycopg.connect(_get_db_conn_str()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.video_hash, v.video_name, v.folder_path,
                           c.chapter_path,
                           1 - (c.embedding <=> %s::vector) AS similarity
                    FROM chapter_embeddings c
                    JOIN lecture_videos v ON c.video_hash = v.video_hash
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vector, query_vector, limit),
                )
                rows = cur.fetchall()
        return rows

    rows = await asyncio.to_thread(_db_query)
    for row in rows:
        video_hash, video_name, folder_path, chapter_path, similarity = row
        content = _load_chapter_content(folder_path, chapter_path)
        results.append(
            {
                "video_name": video_name,
                "chapter_path": chapter_path,
                "similarity": similarity,
                "content": content,
            }
        )

    print(f"Found {len(results)} result(s).\n")
    return results


async def ask_llm(messages: list[dict]) -> str:
    """Send a chat-completion request to the local Mistral LLM."""
    client = openai.AsyncOpenAI(base_url=LLM_BASE_URL, api_key="empty")
    response = await client.chat.completions.create(model=LLM_MODEL, messages=messages)
    raw = response.choices[0].message.content or ""
    return _strip_think_tags(raw)


async def answer_question(query: str, top_k: int = 5) -> str:
    """Full multi-hop pipeline: search → per-result extraction → synthesis."""

    # Step 1 – Retrieve
    results = await search_top_k(query, limit=top_k)
    if not results:
        return "No relevant chapters found in the database."

    # Step 2 – Per-result LLM extraction (all k requests run concurrently)
    async def _extract(i: int, result: dict) -> tuple[int, str]:
        """Send one chapter to the LLM and return (index, extraction_text)."""
        print(f"[{i}/{len(results)}] Extracting from: {result['chapter_path']} "
              f"(similarity {result['similarity']:.4f})...")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. The user has a question and you "
                    "are given the content of one lecture chapter. Extract ONLY the "
                    "information from this chapter that is relevant to answering the "
                    "user's question. If nothing is relevant, reply with 'No relevant "
                    "information in this chapter.' Be concise."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {query}\n\n"
                    f"--- Chapter Content (from {result['video_name']}) ---\n"
                    f"{result['content']}"
                ),
            },
        ]

        try:
            extraction = await ask_llm(messages)
            print(f"  ✓ [{i}] Got extraction for {result['chapter_path']}:")
            print(f"--- LLM Response ({result['chapter_path']}) ---")
            print(extraction)
            print("-----------------------------------------\n")
            return (
                i,
                f"Source {i} ({result['video_name']} – {result['chapter_path']}):\n"
                f"{extraction}",
            )
        except Exception as e:
            print(f"  ✗ [{i}] LLM error: {e}")
            return (
                i,
                f"Source {i} ({result['video_name']}): [error retrieving extraction]",
            )

    extraction_results = await asyncio.gather(
        *[_extract(i, result) for i, result in enumerate(results, 1)]
    )

    # Reassemble in original ranking order (gather preserves input order)
    extractions = [text for _, text in extraction_results]

    # Step 3 – Final synthesis
    print("\nSynthesizing final answer...")
    combined_context = "\n\n".join(extractions)

    final_messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. You are given extracted information "
                "from several lecture video chapters that are relevant to the "
                "user's question. Use this information to provide a comprehensive, "
                "well-organized answer. Cite the source number when referencing "
                "specific information (e.g. [Source 1]). If the extracted "
                "information does not answer the question, say so."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {query}\n\n"
                f"--- Extracted Information ---\n{combined_context}"
            ),
        },
    ]

    answer = await ask_llm(final_messages)
    return answer


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ask a question and get an answer from your lecture video database."
    )
    parser.add_argument("query", type=str, help="The question to ask.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of search results to use (default: 5).",
    )
    args = parser.parse_args()

    print("=" * 60)
    answer = asyncio.run(answer_question(args.query, top_k=args.top_k))
    print("=" * 60)
    print("\nFinal Answer:\n")
    print(answer)
