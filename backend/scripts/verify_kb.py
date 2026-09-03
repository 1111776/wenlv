import asyncio
from app.memory.kb_retrieve import search_kb


async def main():
    r = await search_kb("老人门票免票政策", top_k=3)
    print("=== 查询1：老人门票免票 ===")
    for x in r:
        print("[" + x["category"] + "] " + x["title"] + " score=" + str(x["score"]))
        print("   ", x["chunk_text"][:60])

    r2 = await search_kb("早餐吃什么", top_k=3)
    print("=== 查询2：早餐吃什么 ===")
    for x in r2:
        print("[" + x["category"] + "] " + x["title"] + " score=" + str(x["score"]))
        print("   ", x["chunk_text"][:60])

    r3 = await search_kb("儿童高铁买什么票", top_k=3)
    print("=== 查询3：儿童高铁买什么票 ===")
    for x in r3:
        print("[" + x["category"] + "] " + x["title"] + " score=" + str(x["score"]))
        print("   ", x["chunk_text"][:60])


asyncio.run(main())
