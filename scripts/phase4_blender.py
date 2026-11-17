"""Phase 4：Blender 無頭 Cycles，OPTIX / CUDA / CPU 單張算圖秒數。
用法（在 Colab VM 上）：python scripts/phase4_blender.py [--devices OPTIX,CUDA,CPU] [--out /content/out/phase4]"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = "https://download.blender.org/release/"
APT = "libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libxkbcommon0 libsm6 libegl1"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def latest():
    vkey = lambda s: tuple(int(x) for x in s.split("."))
    series = sorted(set(re.findall(r"Blender(\d+\.\d+)/", urllib.request.urlopen(BASE).read().decode())), key=vkey)
    for s in reversed(series):
        files = set(re.findall(r"blender-(\d+\.\d+\.\d+)-linux-x64\.tar\.xz", urllib.request.urlopen(f"{BASE}Blender{s}/").read().decode()))
        if files:
            v = sorted(files, key=vkey)[-1]
            return v, f"{BASE}Blender{s}/blender-{v}-linux-x64.tar.xz"
    raise RuntimeError("找不到 linux-x64 版本")


def main():
    out = arg("--out", "/content/out/phase4")
    os.makedirs(out, exist_ok=True)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    tag = re.sub(r"[^A-Za-z0-9]", "", gpu.split(",")[0].replace("NVIDIA", "").replace("Tesla", "")) or "nogpu"
    ver, url = latest()
    rep = {"phase": 4, "gpu": gpu, "blender_version": ver, "url": url, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "renders": {}}
    t = time.time()
    subprocess.run(f"apt-get install -y -qq {APT} > /content/apt.log 2>&1", shell=True)
    subprocess.run(f"mkdir -p /content/blender && curl -sSL {url} | tar xJ -C /content/blender --strip-components 1", shell=True, check=True)
    rep["install_s"] = round(time.time() - t, 1)
    scene = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_scene.py")
    devices = arg("--devices", "OPTIX,CUDA,CPU").split(",")
    for i, dev in enumerate(devices):
        t = time.time()
        r = subprocess.run(["/content/blender/blender", "-b", "-P", scene, "--", "--device", dev, "--out", out, "--tag", tag, "--glb", "1" if i == 0 else "0"],
                           capture_output=True, text=True, timeout=1500)
        line = [l for l in r.stdout.splitlines() if l.startswith("RENDER_JSON ")]
        res = json.loads(line[-1][12:]) if line else {"error": f"rc={r.returncode}", "tail": (r.stdout + r.stderr)[-2500:]}
        res["wall_s"] = round(time.time() - t, 1)
        rep["renders"][dev] = res
        if not line or "error" in res:
            res.setdefault("tail", (r.stdout + r.stderr)[-2500:])
    json.dump(rep, open(os.path.join(out, f"phase4_{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("RESULT_JSON " + json.dumps(rep, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main()
