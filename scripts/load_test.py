"""基础压力验证脚本（决策 D-07/Q11 范围）。

用法：python scripts/load_test.py [base_url] [并发数] [每人会话数]
前提：目标服务器以 mock provider + 放宽限流启动。
"""
from __future__ import annotations

import asyncio

import httpx
import base64
import io
import math
import statistics
import struct
import sys
import time
import wave as _wave


def make_wav_b64(seconds=1.0):
    buf = io.BytesIO()
    w = _wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000
                   )
    n = int(seconds * 16000)
    frames = bytearray()
    for i in range(n):
        v = int(20000 * math.sin(2 * math.pi * 440 * i / 16000))
        frames += struct.pack("<h", v)
    w.writeframes(bytes(frames))
    w.close()
    return base64.b64encode(buf.getvalue()).decode()


async def one_worker(client, wid, sessions_n, lat,
                     wav_b64):
    for k in range(sessions_n):
        vn = f"{wid}{k}".zfill(3) + "7"
        t0 = time.perf_counter()
        r = await client.post(
            BASE + "/api/patient/consultations",
            json={"visit_number": vn},
        )
        dt = time.perf_counter() - t0
        lat["create"].append(dt)
        if r.status_code != 200:
            lat["errors"].append("create:" + str(r.status_code))
            return
        sid = r.json()["session_id"]
        finished = False
        round_i = 0
        while not finished and round_i < 12:
            round_i += 1
            t0 = time.perf_counter()
            r = await client.post(
                BASE + f"/api/patient/consultations/{sid}/rounds",
                json={"audio_b64": wav_b64})
            dt = time.perf_counter() - t0
            lat["round"].append(dt)
            if r.status_code != 200:
                lat["errors"].append("round:" + str(r.status_code))
                return
            finished = r.json()["finished"]
        lat["done"] += 1


async def main():
    global BASE
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    BASE = base
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    lat = {"create": [], "round": [], "errors": [], "done": 0}
    wav_b64 = make_wav_b64(1.0)
    limits = httpx.Limits(max_connections=concurrency + 10,
                          max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=30) as client:
        sem = asyncio.Semaphore(concurrency)
        async def guarded(wid):
            async with sem:
                await one_worker(client, wid, per, lat,
                                 wav_b64)
        t_start = time.perf_counter()
        await asyncio.gather(*[guarded(i) for i in range(concurrency)])
        wall = time.perf_counter() - t_start

    def pct(lst, p):
        lst = sorted(lst)
        idx = min(int(len(lst) * p), len(lst) - 1)
        return round(lst[idx], 3)

    print("=== 压测结果 ===")
    print("base:", base, "| 并发:", concurrency, "| 每人会话:", per)
    print("完成会话:", lat["done"], "/", concurrency * per)
    print("create 请求数:", len(lat["create"]),
          "p50/p95/max(s):",
          pct(lat["create"], 0.5), pct(lat["create"], 0.95),
          max(lat["create"]))
    print("rounds 请求数:", len(lat["round"]),
          "p50/p95/max(s):",
          pct(lat["round"], 0.5),
          pct(lat["round"], 0.95),
          max(lat["round"]))
    print("错误数:", len(lat["errors"]), lat["errors"][:5])
    print("总耗时:", round(wall, 1), "s")


if __name__ == "__main__":
    asyncio.run(main())
