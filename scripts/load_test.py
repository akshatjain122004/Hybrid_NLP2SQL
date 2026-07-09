import asyncio
import time
import httpx

URL = "http://localhost:8000/query"
QUERIES = [
    "show all customers", "total revenue", "top 5 products by rating",
    "sales by category", "orders where status is shipped",
    "compare revenue this year vs last year", "list all employees",
    "average order value", "customers in India", "products with low stock",
] * 10  # 100 total


async def fire(client, query):
    start = time.perf_counter()
    try:
        resp = await client.post(URL, json={"query": query}, timeout=30)
        return {"ok": resp.status_code == 200, "elapsed_ms": (time.perf_counter() - start) * 1000, "query": query}
    except Exception as e:
        return {"ok": False, "elapsed_ms": (time.perf_counter() - start) * 1000, "query": query, "error": str(e)}


async def main():
    async with httpx.AsyncClient() as client:
        start = time.perf_counter()
        results = await asyncio.gather(*[fire(client, q) for q in QUERIES])
        total_elapsed = time.perf_counter() - start

    ok_count = sum(1 for r in results if r["ok"])
    latencies = sorted(r["elapsed_ms"] for r in results)
    p50, p95 = latencies[len(latencies) // 2], latencies[int(len(latencies) * 0.95)]

    print(f"Total: {len(results)} queries in {total_elapsed:.2f}s")
    print(f"Success: {ok_count}/{len(results)}")
    print(f"Latency p50: {p50:.1f}ms  p95: {p95:.1f}ms  max: {max(latencies):.1f}ms")

    failures = [r for r in results if not r["ok"]]
    if failures:
        print(f"\n{len(failures)} failures, first 3:")
        for f in failures[:3]:
            print(f"  '{f['query']}' -> {f.get('error', 'non-200 status')}")


if __name__ == "__main__":
    asyncio.run(main())