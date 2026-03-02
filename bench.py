import argparse
import asyncio
import json
import statistics
import time
import base64
from io import BytesIO
from collections import Counter
from typing import List, Tuple, Optional

import httpx
from PIL import Image

# Default configuration
DEFAULT_API_URL = "http://localhost:8000/v1/chat/completions"
DEFAULT_MODEL = "mistral-large"
DEFAULT_REQUESTS = 20
DEFAULT_CONCURRENCY = 10
DEFAULT_IMAGES = 32
DEFAULT_TEXT_LENGTH = 40000


def generate_multimodal_payload(
    model_name: str, num_images: int, text_length: int
) -> dict:
    """Generates a massive payload with N 720p images and a long text prompt."""
    print(
        f"Generating payload: {num_images}x 720p images + ~{text_length} text tokens..."
    )

    # 1. Generate a dummy 720p (1280x720) image in memory
    img = Image.new("RGB", (1280, 720), color=(70, 130, 180))  # Steel blue
    buffered = BytesIO()
    img.save(buffered, format="JPEG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    img_url = f"data:image/jpeg;base64,{img_b64}"

    # 2. Build the massive text block (approx 1 token per word for standard English)
    heavy_text = "Analyze this dataset closely. " * (text_length // 4)

    # 3. Construct the OpenAI-compatible multimodal content array
    content = [{"type": "text", "text": heavy_text}]
    for _ in range(num_images):
        content.append({"type": "image_url", "image_url": {"url": img_url}})

    return {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 128,  # We just want to test prefill, not generate a massive essay
        "temperature": 0.2,
    }


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    semaphore: asyncio.Semaphore,
) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """
    Sends a single request and returns (latency, total_tokens, status_code).
    """
    async with semaphore:
        start_time = time.perf_counter()
        try:
            # CRITICAL FIX: timeout=None. We must wait patiently in the vLLM queue.
            response = await client.post(url, json=payload, timeout=None)
            end_time = time.perf_counter()
            latency = end_time - start_time

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    total_tokens = response_data["usage"]["total_tokens"]
                    return latency, total_tokens, 200
                except (KeyError, json.JSONDecodeError):
                    return latency, 0, 200
            else:
                print(
                    f"Request failed with status {response.status_code}: {response.text[:200]}"
                )
                return None, None, response.status_code

        except httpx.RequestError as e:
            print(f"Connection error: {e}")
            return None, None, 0


async def main():
    parser = argparse.ArgumentParser(
        description="Benchmark massive multimodal workloads on vLLM."
    )
    parser.add_argument("--url", default=DEFAULT_API_URL, help="API endpoint URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help="Total number of requests",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Number of concurrent requests",
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=DEFAULT_IMAGES,
        help="Number of 720p images per prompt",
    )
    parser.add_argument(
        "--text-length",
        type=int,
        default=DEFAULT_TEXT_LENGTH,
        help="Approximate text tokens per prompt",
    )

    args = parser.parse_args()

    print(f"--- Starting Heavy Multimodal Benchmark ---")
    print(f"  URL: {args.url}")
    print(f"  Model: {args.model}")
    print(f"  Requests: {args.requests} (Concurrency: {args.concurrency})")
    print("-" * 40)

    # Prepare massive payload
    payload = generate_multimodal_payload(args.model, args.num_images, args.text_length)

    # High concurrency requires disabled limits & generous timeouts
    limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
    timeout = httpx.Timeout(None)

    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        start_time = time.perf_counter()
        tasks = [
            send_request(client, args.url, payload, semaphore)
            for _ in range(args.requests)
        ]

        print(
            f"Firing {args.requests} massive payloads at the server. Monitoring VRAM is highly recommended..."
        )
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

        rps = successful_requests / total_time
        tokens_per_sec = sum(tokens) / total_time

        print(f"\nLatency:")
        print(f"  Average: {avg_latency:.4f} s")
        print(f"  Median (P50): {p50:.4f} s")
        print(f"  P95: {p95:.4f} s")

        print(f"\nThroughput:")
        print(f"  Requests/sec: {rps:.2f}")
        print(f"  Tokens/sec: {tokens_per_sec:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
