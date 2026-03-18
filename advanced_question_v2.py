"""
advanced_question_v2.py – Agentic RAG question-answering pipeline.

Flow:
  1. User question arrives.
  2. Ask the LLM to decompose the question into targeted search sub-queries.
  3. Run all sub-queries against the pgvector database concurrently.
  4. Deduplicate results and extract relevant context from each chapter
     (all extractions run concurrently).
  5. Send the combined context to the LLM for a final, comprehensive answer.

This differs from question.py in that the LLM *plans* its own research
before searching, enabling better recall on complex or multi-faceted questions.
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

TOP_K_PER_QUERY = 4  # results per sub-query (kept small to avoid flooding)
MAX_SUB_QUERIES = 10  # cap on sub-queries the planner can emit


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
    """Load transcript + summary for a chapter from disk."""
    chapter_dir = os.path.join(folder_path, "chapters", chapter_path.split("/", 1)[-1])

    parts: list[str] = []

    summary_path = os.path.join(chapter_dir, "summary.json")
    print(f"  Attempting to read summary: {summary_path}")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            for title, summary_text in summary_data.items():
                parts.append(f"Chapter: {title}\nSummary: {summary_text}")
        except Exception:
            pass

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
        parts.append(f"[No content found on disk for chapter path: {chapter_path}]")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Async LLM / search primitives
# ---------------------------------------------------------------------------
async def ask_llm(messages: list[dict]) -> str:
    """Send a chat-completion request to the local Mistral LLM."""
    client = openai.AsyncOpenAI(base_url=LLM_BASE_URL, api_key="empty")
    response = await client.chat.completions.create(model=LLM_MODEL, messages=messages)
    raw = response.choices[0].message.content or ""
    return _strip_think_tags(raw)


async def search_top_k(query: str, limit: int = 5) -> list[dict]:
    """Return the top-k chapter matches with metadata + on-disk content."""
    client = openai.AsyncOpenAI(base_url=EMBED_BASE_URL, api_key="empty")
    response = await client.embeddings.create(model=EMBED_MODEL, input=query)
    query_vector = response.data[0].embedding

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
    results: list[dict] = []
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

    return results


# ---------------------------------------------------------------------------
# Agentic pipeline steps
# ---------------------------------------------------------------------------
async def plan_queries(question: str) -> list[str]:
    """Ask the LLM to decompose the question into search sub-queries.

    Returns a list of search strings (1–MAX_SUB_QUERIES items).
    """
    print("🔍 Planning search queries...")
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research planner. Given a user question, generate a "
                "JSON array of short search queries that, taken together, would "
                "retrieve all the information needed to answer the question "
                "comprehensively. Each query should target a different aspect "
                "or sub-topic.\n\n"
                "Rules:\n"
                f"- Return between 1 and {MAX_SUB_QUERIES} queries.\n"
                "- Always include the original question (or a close paraphrase) "
                "as the first query.\n"
                "- Output ONLY valid JSON — a flat array of strings, no markdown, "
                "no explanation.\n\n"
                'Example output: ["What is gradient descent?", '
                '"learning rate in gradient descent", '
                '"gradient descent vs stochastic gradient descent"]'
            ),
        },
        {
            "role": "user",
            "content": question,
        },
    ]

    raw = await ask_llm(messages)

    # Robust JSON extraction: handle markdown code fences, stray text, etc.
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        queries = json.loads(text)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            queries = queries[:MAX_SUB_QUERIES]
            print(f"   Planned {len(queries)} sub-queries:")
            for i, q in enumerate(queries, 1):
                print(f"   {i}. {q}")
            return queries
    except json.JSONDecodeError:
        pass

    # Fallback: LLM didn't return parseable JSON — use the original question
    print("   (planner output was not valid JSON, falling back to original question)")
    return [question]


async def multi_search(queries: list[str], top_k: int = TOP_K_PER_QUERY) -> list[dict]:
    """Run all sub-queries concurrently, deduplicate by chapter_path, aggregate queries,
    and keep the best similarity score."""
    print(f"\n📚 Searching {len(queries)} sub-queries (top-{top_k} each)...")

    search_results = await asyncio.gather(
        *[search_top_k(q, limit=top_k) for q in queries]
    )

    seen: dict[str, dict] = {}
    for batch_idx, batch in enumerate(search_results):
        current_query = queries[batch_idx]
        for result in batch:
            key = result["chapter_path"]

            if key not in seen:
                # First time seeing this chapter: initialize the list
                result["matched_queries"] = [current_query]
                seen[key] = result
            else:
                # Chapter already seen: append the new query if it's unique
                if current_query not in seen[key]["matched_queries"]:
                    seen[key]["matched_queries"].append(current_query)

                # Update to the highest similarity score if this match was stronger
                if result["similarity"] > seen[key]["similarity"]:
                    seen[key]["similarity"] = result["similarity"]

    deduped = sorted(seen.values(), key=lambda r: r["similarity"], reverse=True)
    print(
        f"   Found {sum(len(b) for b in search_results)} results total, "
        f"{len(deduped)} unique chapters after dedup.\n"
    )
    return deduped


async def extract_all(question: str, results: list[dict]) -> list[str]:
    """For each chapter, ask the LLM to extract relevant info concurrently using hybrid prompting."""

    async def _extract(i: int, result: dict) -> tuple[int, str]:
        # Format the aggregated queries for logging and prompting
        focus_list = "\n".join([f"- {q}" for q in result["matched_queries"]])
        log_queries = " | ".join(result["matched_queries"])

        print(
            f"[{i}/{len(results)}] Extracting from: {result['chapter_path']} "
            f"(sim {result['similarity']:.4f}, triggers: [{log_queries}])"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precision research extraction engine. Your task is to extract information "
                    "from the provided source text that explicitly answers the SPECIFIC FOCUS queries. "
                    "Use the GLOBAL CONTEXT to understand the overarching goal, but ONLY extract "
                    "information relevant to the SPECIFIC FOCUS. If the text does not contain relevant "
                    "information for the focus queries, reply exactly with: 'No relevant information in this chapter.'"
                    "Be concise and do not hallucinate."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"GLOBAL CONTEXT (Master Question):\n{question}\n\n"
                    f"SPECIFIC FOCUS (Extract answers for these):\n{focus_list}\n\n"
                    f"--- Chapter Content (from {result['video_name']}) ---\n"
                    f"{result['content']}"
                ),
            },
        ]

        try:
            extraction = await ask_llm(messages)
            print(f"  ✓ [{i}] Got extraction ({len(extraction)} chars)")
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
        *[_extract(i, r) for i, r in enumerate(results, 1)]
    )

    return [text for _, text in extraction_results]


async def synthesize(question: str, extractions: list[str]) -> str:
    """Send the combined context to the LLM for a final answer."""
    print("\n🧠 Synthesizing final answer...")
    combined_context = "\n\n".join(extractions)

    messages = [
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
                f"Question: {question}\n\n"
                f"--- Extracted Information ---\n{combined_context}"
            ),
        },
    ]

    return await ask_llm(messages)


# ---------------------------------------------------------------------------
# Main agentic pipeline
# ---------------------------------------------------------------------------
async def agentic_answer(question: str, top_k: int = TOP_K_PER_QUERY) -> str:
    """Full agentic RAG pipeline:
    plan queries → multi-search → extract → synthesize."""

    # Step 1 — Plan: ask the LLM what to search for
    sub_queries = await plan_queries(question)

    # Step 2 — Search: run all sub-queries concurrently
    results = await multi_search(sub_queries, top_k=top_k)
    if not results:
        return "No relevant chapters found in the database."

    # Step 3 — Extract: pull relevant info from each chapter concurrently
    extractions = await extract_all(question, results)

    # Step 4 — Synthesize: final LLM call with all context
    answer = await synthesize(question, extractions)
    return answer


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Agentic RAG: the LLM plans its own search queries, retrieves "
            "context across multiple sub-queries, and synthesizes a final answer."
        ),
    )
    parser.add_argument("query", type=str, help="The question to ask.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=TOP_K_PER_QUERY,
        help=f"Results per sub-query (default: {TOP_K_PER_QUERY}).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Agentic RAG Pipeline")
    print("=" * 60)
    answer = asyncio.run(agentic_answer(args.query, top_k=args.top_k))
    print("=" * 60)
    print("\nFinal Answer:\n")
    print(answer)
