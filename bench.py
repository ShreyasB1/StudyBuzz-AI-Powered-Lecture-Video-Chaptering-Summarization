import asyncio
import time
import httpx
import json

# --- Configuration ---
# Your vLLM server's OpenAI-compatible endpoint
API_URL = "http://localhost:8000/v1/chat/completions"

# Benchmark parameters
NUM_REQUESTS = 500
MAX_CONCURRENT_REQUESTS = 250  # Number of requests to send in parallel

# Request payload
# Use a representative prompt
REQUEST_PAYLOAD = {
    "model": "gpt-oss",  # The model name you passed to vLLM
    "messages": [
        {
            "role": "user",
            "content": "A dead cat is placed into a box along with a nuclear isotope, a vial of poison and a radiation detector. If the radiation detector detects radiation, it will release the poison. The box is opened one day later. What is the probability of the cat being alive?",
        }
    ],
}

# --- Benchmarking Logic ---


async def send_request(client, semaphore):
    """Sends a single request and returns a tuple of (latency, total_tokens)."""
    async with semaphore:
        try:
            start_time = time.perf_counter()
            response = await client.post(API_URL, json=REQUEST_PAYLOAD, timeout=60.0)
            response.raise_for_status()  # Raise an exception for bad status codes
            end_time = time.perf_counter()

            # Parse the JSON response to get the actual token usage
            response_data = response.json()
            total_tokens = response_data["usage"]["total_tokens"]

            latency = end_time - start_time
            return (latency, total_tokens)
        except httpx.RequestError as e:
            print(f"An error occurred during request: {e}")
            return (None, None)
        except (KeyError, json.JSONDecodeError) as e:
            print(f"Error parsing response or finding 'usage' data: {e}")
            return (None, None)


async def main():
    """Runs the benchmark."""
    print(
        f"Starting benchmark with {NUM_REQUESTS} requests and {MAX_CONCURRENT_REQUESTS} concurrent workers..."
    )

    # Semaphore limits the number of concurrent executions
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # Use a single client session for efficiency
    async with httpx.AsyncClient() as client:
        tasks = [send_request(client, semaphore) for _ in range(NUM_REQUESTS)]

        benchmark_start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        benchmark_end_time = time.perf_counter()

    # --- Results Analysis ---
    # Filter out failed requests (where latency is None)
    successful_results = [res for res in results if res[0] is not None]
    num_successful = len(successful_results)

    if num_successful == 0:
        print("No requests were successful.")
        return

    total_time_taken = benchmark_end_time - benchmark_start_time

    # Separate latencies and token counts from the successful results
    latencies = [res[0] for res in successful_results]
    token_counts = [res[1] for res in successful_results]

    avg_latency = sum(latencies) / num_successful
    requests_per_second = num_successful / total_time_taken

    # Calculate total tokens from the sum of tokens in each successful response
    total_tokens_processed = sum(token_counts)
    tokens_per_second = total_tokens_processed / total_time_taken

    print("\n--- Benchmark Results ---")
    print(f"Total time taken: {total_time_taken:.2f} seconds")
    print(f"Successful requests: {num_successful}/{NUM_REQUESTS}")
    print(f"Average latency per request: {avg_latency:.4f} seconds")
    print(f"Requests Per Second (RPS): {requests_per_second:.2f}")
    print(f"Throughput (Tokens/sec): {tokens_per_second:.2f}")
    print("-------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
