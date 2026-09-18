import asyncio
from backend.agent import agent

enriched = """
User intent: merge these two PDF files.
Files saved to disk:
  • 1.pdf → /tmp/omni_agent/test_id/1.pdf
  • 2.pdf → /tmp/omni_agent/test_id/2.pdf
"""

import os
os.makedirs("/tmp/omni_agent/test_id", exist_ok=True)
import fitz
doc = fitz.Document()
doc.new_page()
doc.save("/tmp/omni_agent/test_id/1.pdf")
doc.save("/tmp/omni_agent/test_id/2.pdf")

result = agent(enriched)
print(result)
