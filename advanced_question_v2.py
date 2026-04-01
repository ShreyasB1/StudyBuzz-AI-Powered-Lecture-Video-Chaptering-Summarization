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

TOP_K_PER_QUERY = 3  # results per sub-query (kept small to avoid flooding)
MAX_SUB_QUERIES = 5  # cap on sub-queries the planner can emit
MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.25"))
VERBOSE_TRACE = os.getenv("RAG_VERBOSE_TRACE", "1").lower() not in {"0", "false", "no"}


def _trace(message: str) -> None:
    if VERBOSE_TRACE:
        print(message)


def _trace_block(title: str, content: str) -> None:
    if not VERBOSE_TRACE:
        return
    print(title)
    print("-" * len(title))
    print(content)
    print("-" * len(title))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_db_conn_str() -> str:
    return f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"


def _strip_think_tags(text: str) -> str:
    """Remove <think>…</think> wrapper that some models emit."""
    return text.split("</think>")[-1].strip()


def _is_no_relevant_response(text: str) -> bool:
    """Best-effort check for the extraction fallback response."""
    if not text:
        return False
    normalized = " ".join(text.strip().lower().split())
    return "no relevant information in this chapter" in normalized


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

    _trace(f"  [File] chapter_dir={chapter_dir}")

    summary_path = os.path.join(chapter_dir, "summary.json")
    print(f"  Attempting to read summary: {summary_path}")
    if os.path.exists(summary_path):
        try:
            summary_size = os.path.getsize(summary_path)
            print(f"    Summary exists (size={summary_size} bytes)")
        except OSError as e:
            print(f"    Summary stat failed: {e}")
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            print(f"    Summary loaded with {len(summary_data)} entries")
            _trace_block(f"    [File Contents] {summary_path}", json.dumps(summary_data, indent=2, ensure_ascii=False))
            for title, summary_text in summary_data.items():
                parts.append(f"Chapter: {title}\nSummary: {summary_text}")
        except Exception as e:
            print(f"    Failed to parse summary JSON: {e}")
    else:
        print("    Summary file missing")

    transcript_path = os.path.join(chapter_dir, "transcript.vtt")
    print(f"  Attempting to read transcript: {transcript_path}")
    if os.path.exists(transcript_path):
        try:
            transcript_size = os.path.getsize(transcript_path)
            print(f"    Transcript exists (size={transcript_size} bytes)")
        except OSError as e:
            print(f"    Transcript stat failed: {e}")
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                raw = f.read()
            _trace_block(f"    [File Contents] {transcript_path}", raw)
            plain = _extract_plain_text_from_vtt(raw)
            print(f"    Transcript plain-text length: {len(plain)} chars")
            if plain:
                parts.append(f"Transcript:\n{plain}")
        except Exception as e:
            print(f"    Failed to parse transcript: {e}")
    else:
        print("    Transcript file missing")

    if not parts:
        print(f"    No usable content found for chapter: {chapter_path}")
        parts.append(f"[No content found on disk for chapter path: {chapter_path}]")
    else:
        print(f"    Combined chapter context length: {sum(len(p) for p in parts)} chars")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Async LLM / search primitives
# ---------------------------------------------------------------------------
async def ask_llm(messages: list[dict]) -> str:
    """Send a chat-completion request to the local Mistral LLM."""
    _trace("\n[LLM] Sending chat completion request")
    for idx, message in enumerate(messages, 1):
        role = message.get("role", "unknown")
        content = message.get("content", "")
        _trace_block(f"[LLM Request] Message {idx} role={role}", content)
    client = openai.AsyncOpenAI(base_url=LLM_BASE_URL, api_key="empty")
    response = await client.chat.completions.create(model=LLM_MODEL, messages=messages)
    raw = response.choices[0].message.content or ""
    _trace_block("[LLM Response] Raw model output", raw)
    return _strip_think_tags(raw)


async def search_top_k(query: str, limit: int = 5) -> list[dict]:
    """Return the top-k chapter matches with metadata + on-disk content."""
    print(f"  [Search] Embedding query: '{query[:120]}'")
    _trace_block("  [Search Query] Full query", query)
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
    print(f"  [Search] DB returned {len(rows)} rows for query '{query[:80]}'")
    results: list[dict] = []
    for idx, row in enumerate(rows, 1):
        video_hash, video_name, folder_path, chapter_path, similarity = row
        print(
            f"    [Search:{idx}] video='{video_name}' chapter='{chapter_path}' sim={similarity:.4f}"
        )
        content = _load_chapter_content(folder_path, chapter_path)
        _trace_block(
            f"    [Search Result Content] {video_name} :: {chapter_path}",
            content,
        )
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
    _trace_block("[Planner] User question", question)
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
                "- Stay in-domain with the user's wording. Do NOT introduce new "
                "academic domains, analogies, or contexts unless the user explicitly "
                "asks for them.\n"
                "- Prefer narrower, lexical variants of the user's terms over "
                "broad conceptual expansions.\n"
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
    _trace_block("[Planner] Raw planner response before JSON parse", raw)

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
            _trace_block("[Planner] Parsed sub-queries", json.dumps(queries, indent=2, ensure_ascii=False))
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
    _trace_block("[Search] Planned sub-queries", json.dumps(queries, indent=2, ensure_ascii=False))

    search_results = await asyncio.gather(
        *[search_top_k(q, limit=top_k) for q in queries]
    )

    for idx, batch in enumerate(search_results, 1):
        sims = ", ".join(f"{r['similarity']:.4f}" for r in batch)
        print(f"   Sub-query {idx} returned {len(batch)} rows (sims: [{sims}])")
        for row in batch:
            _trace_block(
                f"   [Search Row] {row['video_name']} :: {row['chapter_path']}",
                json.dumps(
                    {
                        "video_name": row.get("video_name"),
                        "chapter_path": row.get("chapter_path"),
                        "similarity": row.get("similarity"),
                        "matched_queries": row.get("matched_queries", []),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
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
    filtered = [r for r in deduped if r["similarity"] >= MIN_SIMILARITY]
    print(
        f"   Found {sum(len(b) for b in search_results)} results total, "
        f"{len(deduped)} unique chapters after dedup, "
        f"{len(filtered)} after similarity filter (min={MIN_SIMILARITY:.2f}).\n"
    )

    # If the threshold filtered everything, keep best candidates so we can still answer.
    if filtered:
        _trace_block(
            "[Search] Filtered deduped results",
            json.dumps(
                [
                    {
                        "video_name": r.get("video_name"),
                        "chapter_path": r.get("chapter_path"),
                        "similarity": r.get("similarity"),
                        "matched_queries": r.get("matched_queries", []),
                    }
                    for r in filtered
                ],
                indent=2,
                ensure_ascii=False,
            ),
        )
        return filtered

    print("   Similarity filter removed all chapters; falling back to top deduped results.")
    _trace_block(
        "[Search] Deduped fallback results",
        json.dumps(
            [
                {
                    "video_name": r.get("video_name"),
                    "chapter_path": r.get("chapter_path"),
                    "similarity": r.get("similarity"),
                    "matched_queries": r.get("matched_queries", []),
                }
                for r in deduped
            ],
            indent=2,
            ensure_ascii=False,
        ),
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
        print(f"  ↳ Context length for source {i}: {len(result['content'])} chars")
        _trace_block(
            f"[Extract] Source {i} metadata",
            json.dumps(
                {
                    "video_name": result.get("video_name"),
                    "chapter_path": result.get("chapter_path"),
                    "similarity": result.get("similarity"),
                    "matched_queries": result.get("matched_queries", []),
                    "content_length": len(result.get("content", "")),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
        _trace_block(f"[Extract] Source {i} content", result.get("content", ""))

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precision research extraction engine. Your task is to extract information "
                    "from the provided source text that explicitly answers the SPECIFIC FOCUS queries. "
                    "Use the GLOBAL CONTEXT to understand the overarching goal, but ONLY extract "
                    "information relevant to the SPECIFIC FOCUS. Treat this as ANY-match, not ALL-match: "
                    "if the chapter helps with at least one focus query, return those useful parts. "
                    "If the text does not contain relevant information for any focus query, reply exactly "
                    "with: 'No relevant information in this chapter.' "
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
            if _is_no_relevant_response(extraction):
                print(f"  ! [{i}] Model returned fallback no-relevance response")
            else:
                preview = extraction.replace("\n", " ")[:180]
                print(f"  ↳ [{i}] Extraction preview: {preview}")
            _trace_block(f"[Extract] Source {i} final extraction", extraction)
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
    fallback_count = sum(1 for text in extractions if _is_no_relevant_response(text))
    print(
        f"   Synthesis input stats: total_sources={len(extractions)}, "
        f"fallback_sources={fallback_count}, useful_sources={len(extractions) - fallback_count}"
    )
    combined_context = "\n\n".join(extractions)
    _trace_block("[Synthesis] Combined extraction context", combined_context)

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

    final_answer = await ask_llm(messages)
    _trace_block("[Synthesis] Final answer", final_answer)
    return final_answer


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


async def agentic_answer_stream(question: str, top_k: int = TOP_K_PER_QUERY):
    """
    Streaming version of the agentic RAG pipeline.
    Yields SSE-compatible JSON strings for real-time UI updates.
    """
    
    # Step 1: Plan
    yield json.dumps({"type": "status", "message": "Planning search queries..."})
    sub_queries = await plan_queries(question)
    print(f"[Stream] Planned queries count: {len(sub_queries)}")
    yield json.dumps({"type": "queries", "data": sub_queries})
    
    # Step 2: Search
    yield json.dumps({"type": "status", "message": "Searching database..."})
    results = await multi_search(sub_queries, top_k=top_k)
    print(f"[Stream] Search produced {len(results)} deduped sources")
    
    if not results:
        yield json.dumps({"type": "final_answer", "data": "No relevant chapters found in the database."})
        return

    # Yield sources so UI can display them while extracting
    sources_data = [
        {"id": i, "video": r["video_name"], "chapter": r["chapter_path"]} 
        for i, r in enumerate(results, 1)
    ]
    yield json.dumps({"type": "sources", "data": sources_data})

    # Step 3: Extract (Streaming results as they complete)
    async def _extract_local(i: int, result: dict) -> tuple[int, str]:
        focus_list = "\n".join([f"- {q}" for q in result["matched_queries"]])
        log_queries = " | ".join(result["matched_queries"])
        print(
            f"[Stream][{i}/{len(results)}] Extracting chapter='{result['chapter_path']}' "
            f"sim={result['similarity']:.4f} triggers=[{log_queries}] content_len={len(result['content'])}"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precision research extraction engine. Your task is to extract information "
                    "from the provided source text that explicitly answers the SPECIFIC FOCUS queries. "
                    "Use the GLOBAL CONTEXT to understand the overarching goal, but ONLY extract "
                    "information relevant to the SPECIFIC FOCUS. Treat this as ANY-match, not ALL-match: "
                    "if the chapter helps with at least one focus query, return those useful parts. "
                    "If the text does not contain relevant information for any focus query, reply exactly "
                    "with: 'No relevant information in this chapter.' "
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
            if _is_no_relevant_response(extraction):
                print(f"[Stream][{i}] Fallback no-relevance extraction")
            else:
                preview = extraction.replace("\n", " ")[:180]
                print(f"[Stream][{i}] Extraction preview: {preview}")
            return (
                i,
                f"Source {i} ({result['video_name']} – {result['chapter_path']}):\n{extraction}",
            )
        except Exception as e:
            print(f"[Stream][{i}] Extraction error: {e}")
            return (
                i,
                f"Source {i} ({result['video_name']}): [error retrieving extraction]",
            )

    tasks = [asyncio.create_task(_extract_local(i, r)) for i, r in enumerate(results, 1)]
    extractions_map = {}
    
    # Yield extraction updates as each sub-task completes
    for completed_task in asyncio.as_completed(tasks):
        idx, text = await completed_task
        extractions_map[idx] = text
        print(f"[Stream] Emitting extraction for source {idx} (len={len(text)})")
        yield json.dumps({"type": "extraction", "id": idx, "content": text})

    # Gather extractions in original order for the synthesize step
    extractions = [extractions_map[i] for i in range(1, len(results) + 1)]

    # Step 4: Synthesize
    yield json.dumps({"type": "status", "message": "Synthesizing final answer..."})
    fallback_count = sum(1 for text in extractions if _is_no_relevant_response(text))
    print(
        f"[Stream] Synthesis input stats: total={len(extractions)}, "
        f"fallback={fallback_count}, useful={len(extractions) - fallback_count}"
    )
    final_answer = await synthesize(question, extractions)
    yield json.dumps({"type": "final_answer", "data": final_answer})


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
    print(f"Verbose trace enabled: {VERBOSE_TRACE}")
    answer = asyncio.run(agentic_answer(args.query, top_k=args.top_k))
    print("=" * 60)
    print("\nFinal Answer:\n")
    print(answer)
