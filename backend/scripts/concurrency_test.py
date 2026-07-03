#!/usr/bin/env python3
import asyncio, time, aiohttp
from collections import defaultdict

BASE_URL = 'http://localhost:8000'
ENDPOINTS = [
    '/api/v5/health',
    '/api/v5/market/multi-index',
    '/api/v5/market/snapshot',
    '/api/v5/market/sentiment/SH000300',
    '/api/v5/sector/sentiment',
    '/api/v5/sector/radar',
    '/api/v5/market/recommendations',
    '/api/v5/sector/position-rating',
    '/api/v5/sector/position-rating/801180',
    '/api/v5/market/sector/801180',
]
CONCURRENCY = 10
N = 100

async def bench(session, path, results):
    t0 = time.time()
    try:
        async with session.get(BASE_URL + path) as r:
            status = r.status
            await r.text()
        dt = time.time() - t0
        results.append((status, dt))
    except Exception as e:
        dt = time.time() - t0
        results.append((0, dt))

async def main():
    print('='*60)
    print(f'V5.0 并发压测 — {CONCURRENCY}并发 × {N}请求/端点')
    print('='*60)
    conn = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=conn) as session:
        for path in ENDPOINTS:
            results = []
            tasks = [bench(session, path, results) for _ in range(N)]
            t0 = time.time()
            await asyncio.gather(*tasks)
            total_t = time.time() - t0
            ok = [r for r in results if r[0]==200]
            fail = [r for r in results if r[0]!=200]
            lats = sorted([r[1]*1000 for r in ok])
            if lats:
                err_rate = len(fail)/len(results)*100
                qps = len(results)/total_t
                p50 = lats[len(lats)//2]
                p95 = lats[int(len(lats)*0.95)]
                st = '✅' if err_rate<5 and p95<3000 else '⚠️'
                print(f'{st} {path}')
                print(f'  OK:{len(ok)} FAIL:{len(fail)} ERR:{err_rate:.1f}% QPS:{qps:.0f}')
                print(f'  avg={sum(lats)/len(lats):.0f}ms p50={p50:.0f}ms p95={p95:.0f}ms max={lats[-1]:.0f}ms')
            else:
                print(f'🔴 {path}: 全失败')
    print('='*60)

asyncio.run(main())
