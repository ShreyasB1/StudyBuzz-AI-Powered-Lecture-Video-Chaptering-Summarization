import argparse
import psycopg
import openai
from init_db import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT


def search_chapters(query_text: str, limit: int = 5):
    """
    Search for chapters matching the query_text.
    Returns a list of dicts:
    [{"video_hash": ..., "video_name": ..., "chapter_path": ..., "similarity": ...}]
    """
    db_conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    results_list = []

    # 1. Generate the query embedding
    print(f"Generating embedding for query: '{query_text}'...")
    try:
        client = openai.OpenAI(base_url="http://localhost:8002/v1", api_key="empty")
        response = client.embeddings.create(model="nemotron", input=query_text)
        query_vector = response.data[0].embedding
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        print("Make sure the Nemotron embedder container is running on port 8002.")
        return results_list

    # 2. Query Postgres for closest semantic matches
    print("Searching database for semantic matches...")
    try:
        with psycopg.connect(db_conn_str) as conn:
            with conn.cursor() as cur:
                # Use cosine distance (<=>) for pgvector. We invert it (1 - dist) to show similarity score.
                cur.execute(
                    """
                    SELECT c.video_hash, v.video_name, c.chapter_path, 
                           1 - (c.embedding <=> %s::vector) AS similarity
                    FROM chapter_embeddings c
                    JOIN lecture_videos v ON c.video_hash = v.video_hash
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vector, query_vector, limit),
                )
                results = cur.fetchall()

                if not results:
                    print("No chapters found in the database.")
                    return results_list

                print("\n--- Top Search Results ---")
                for i, row in enumerate(results, 1):
                    video_hash, video_name, chapter_path, similarity = row
                    results_list.append({
                        "video_hash": video_hash,
                        "video_name": video_name,
                        "chapter_path": chapter_path,
                        "similarity": similarity
                    })
                    print(f"{i}. Video: {video_name} (Score: {similarity:.4f})")
                    print(f"   Chapter Path: {chapter_path}")
                    print(f"   Video Hash:   {video_hash}")
                    print()
                
                return results_list

    except Exception as e:
        print(f"Database error during search: {e}")
        return results_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Semantically search for video chapters using Nemotron embeddings."
    )
    parser.add_argument("query", type=str, help="The text query to search for.")
    parser.add_argument(
        "--limit", type=int, default=5, help="Maximum number of results to return."
    )
    args = parser.parse_args()

    search_chapters(args.query, args.limit)
