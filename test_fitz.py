import fitz
import os

os.makedirs("/tmp/omni_agent/test_uuid", exist_ok=True)
doc = fitz.Document()
doc.new_page()
doc.save("/tmp/omni_agent/test_uuid/test.pdf")

doc1 = fitz.Document("/tmp/omni_agent/test_uuid/test.pdf")
doc2 = fitz.Document("/tmp/omni_agent/test_uuid/test.pdf")
doc1.insert_pdf(doc2)
doc1.save("/tmp/omni_agent/test_uuid/merged.pdf")
