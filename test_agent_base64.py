import asyncio
from backend.agent import agent

enriched = """
User intent: encode the text "hello world" into base64.
Files saved to disk:
"""

result = agent(enriched)
print(result)
