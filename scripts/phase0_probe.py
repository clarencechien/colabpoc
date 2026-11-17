"""Phase 0：確認 GPU 看得到。輸出 /content/out/phase0/probe.json。"""
import json
import os
import subprocess
import time

out = "/content/out/phase0"
os.makedirs(out, exist_ok=True)
smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
q = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], capture_output=True, text=True)
rep = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "nvidia_smi_rc": smi.returncode, "gpu": q.stdout.strip(),
       "disk": subprocess.run(["df", "-h", "/content"], capture_output=True, text=True).stdout,
       "mem": subprocess.run(["free", "-g"], capture_output=True, text=True).stdout}
print(smi.stdout or smi.stderr)
json.dump(rep, open(f"{out}/probe.json", "w"), indent=2)
print("RESULT_JSON " + json.dumps(rep))
