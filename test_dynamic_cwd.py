from backend.agent import code_interpreter
code = """
import os
print("CWD:", os.getcwd())
"""
print(code_interpreter(code))

code_with_uuid = """
import os
# My files are in /tmp/omni_agent/2a343c15-616c-4957-9f35-06202d1882b1/
print("CWD:", os.getcwd())
"""
print(code_interpreter(code_with_uuid))
