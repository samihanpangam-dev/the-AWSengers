import asyncio
from httpx import AsyncClient
from backend.main import app
async def main():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        pass
