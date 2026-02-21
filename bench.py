import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from typing import List, Tuple, Optional

import httpx

# Default configuration
DEFAULT_API_URL = "http://localhost:8000/v1/chat/completions"
DEFAULT_MODEL = "mistral-large"
DEFAULT_REQUESTS = 100
DEFAULT_CONCURRENCY = 10

# Default prompt
DEFAULT_PROMPT = (
    "A dead cat is placed into a box along with a nuclear isotope, a vial of poison and a radiation detector. "
    "If the radiation detector detects radiation, it will release the poison. The box is opened one day later. "
    "What is the probability of the cat being alive?"
)


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    semaphore: asyncio.Semaphore,
) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """
    Sends a single request and returns (latency, total_tokens, status_code).
    Returns (None, None, status_code) on error.
    """
    async with semaphore:
        start_time = time.perf_counter()
        try:
            response = await client.post(url, json=payload, timeout=60.0)
            end_time = time.perf_counter()
            latency = end_time - start_time

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    total_tokens = response_data["usage"]["total_tokens"]
                    return latency, total_tokens, 200
                except (KeyError, json.JSONDecodeError):
                    return latency, 0, 200  # Response ok but format unexpected
            else:
                return None, None, response.status_code

        except httpx.RequestError:
            return None, None, 0  # 0 indicates connection error


async def main():
    parser = argparse.ArgumentParser(description="Benchmark an OpenAI-compatible LLM API.")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="API endpoint URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Number of concurrent requests")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt content to send")
    
    args = parser.parse_args()

    print(f"Starting benchmark:")
    print(f"  URL: {args.url}")
    print(f"  Model: {args.model}")
    print(f"  Requests: {args.requests}")
    print(f"  Concurrency: {args.concurrency}")
    print("-" * 30)

    # Prepare payload
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
    }

    # High concurrency requires disabled limits
    limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
    
    semaphore = asyncio.Semaphore(args.concurrency)
    
    async with httpx.AsyncClient(limits=limits) as client:
        start_time = time.perf_counter()
        tasks = [send_request(client, args.url, payload, semaphore) for _ in range(args.requests)]
        
        # Using as_completed would allow progress bar, but gather is simpler for now
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    # Analyze results
    latencies = [r[0] for r in results if r[0] is not None]
    tokens = [r[1] for r in results if r[1] is not None]
    status_codes = [r[2] for r in results]

    successful_requests = len(latencies)
    failed_requests = args.requests - successful_requests

    print("\n--- Benchmark Results ---")
    print(f"Total Time: {total_time:.2f} s")
    print(f"Successful Requests: {successful_requests}/{args.requests}")
    print(f"Failed Requests: {failed_requests}")
    
    if failed_requests > 0:
        print("Status Code Distribution:")
        for code, count in Counter(status_codes).items():
            if code != 200:
                print(f"  {code}: {count}")

    if successful_requests > 0:
        avg_latency = statistics.mean(latencies)
        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else p50
        p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else p95
        
        rps = successful_requests / total_time
        tokens_per_sec = sum(tokens) / total_time

        print(f"\nLatency:")
        print(f"  Average: {avg_latency:.4f} s")
        print(f"  Median (P50): {p50:.4f} s")
        print(f"  P95: {p95:.4f} s")
        print(f"  P99: {p99:.4f} s")
        
        print(f"\nThroughput:")
        print(f"  Requests/sec: {rps:.2f}")
        print(f"  Tokens/sec: {tokens_per_sec:.2f}")
    else:
        print("\nNo successful requests. Check your server URL and model name.")

if __name__ == "__main__":
    asyncio.run(main())
