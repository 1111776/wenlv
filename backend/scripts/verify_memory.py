import asyncio
from app.memory.engine import retrieve


async def main():
    r = await retrieve("海鲜过敏", top_k=5)
    print("=== 图记忆检索：海鲜过敏 ===")
    for x in r:
        print(str(x["type"]) + ":" + str(x["key"]) + " score=" + str(x["score"]) + " path=" + x["retrieval_path"])


asyncio.run(main())
