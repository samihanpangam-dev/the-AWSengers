import asyncio
from httpx import AsyncClient
from backend.main import app

async def test():
    async with AsyncClient(app=app, base_url="http://test") as client:
        res = await client.post("/process", data={"prompt": "merge"})
        print(res.json())

asyncio.run(test())
