"""检索延迟红线验证（容器内跑，正确口径 = retrieve() 函数本身）。"""
import asyncio
import time

from app.memory import engine


async def main():
    await engine.retrieve("海鲜过敏")  # 预热，写缓存

    lats = []
    for _ in range(100):
        t = time.perf_counter()
        await engine.retrieve("海鲜过敏")
        lats.append((time.perf_counter() - t) * 1000)
    lats.sort()

    avg = sum(lats) / len(lats)
    print(f"采样 100 次")
    print(f"平均 = {avg:.1f} ms")
    print(f"P50  = {lats[50]:.1f} ms")
    print(f"P95  = {lats[95]:.1f} ms")
    print(f"红线 < 150ms: {'✅ 达标' if lats[95] < 150 else '❌ 未达标'}")


asyncio.run(main())
