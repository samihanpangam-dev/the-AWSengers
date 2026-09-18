from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.post("/test")
def test() -> dict[str, str]:
    return {"response": "test", "download_url": None}

client = TestClient(app)
print(client.post("/test").status_code)
