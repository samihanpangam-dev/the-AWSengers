import asyncio
lock = asyncio.Lock()

async def main():
    async with lock:
        print("Got lock!")

asyncio.run(main())
