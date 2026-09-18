import re
text = "The output file is saved at the following path: ``` /tmp/omni_agent/4dd32fea-9968-4307-a955-4e19c5a11630/merged.pdf ``` This merged document now includes"
tmp_dir = "/tmp/omni_agent/4dd32fea-9968-4307-a955-4e19c5a11630"
match = re.search(rf"{re.escape(str(tmp_dir))}/([^\s\"'`]+)", text)
if match:
    print("MATCH:", match.group(0))
else:
    print("NO MATCH")
