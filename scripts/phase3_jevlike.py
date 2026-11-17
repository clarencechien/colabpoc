"""Phase 3：在 Colab VM 上編 llama.cpp b11371、抓 GGUF、起 llama-server、跑 jevlike 的 bench。

jevlike 的報告、門檻與結果都放在 clarencechien/jevlike（results/28-colab.md、results/colab/）；這支只是 Colab 端的執行器。
用法（在 Colab VM 上）：
  python scripts/phase3_jevlike.py build                       # 編譯並打包 /content/out/phase3/llama-server-b11371.tar.gz
  python scripts/phase3_jevlike.py bench --model e4b [--jevlike-ref <commit>] [--what smoke,accuracy,latency] [--bin-tar PATH]
server 參數跟 jevlike modal_app.start_server() 相同：-ngl 99 -c 16384 -np 4 --jinja --reasoning-budget 0 --metrics，另加 --swa-full。
latency 只跑 L1，且在 accuracy 之前另起一個乾淨的 server 冷跑（README v20：prompt 快取會重播）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

TAG = "b11371"
OUT = "/content/out/phase3"
BUILD = "/content/llama.cpp"
BIN_DIR = "/content/llama-bin"
MODELS = {"26b": ("unsloth/gemma-4-26B-A4B-it-GGUF", "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf"),
          "e4b": ("unsloth/gemma-4-E4B-it-GGUF", "gemma-4-E4B-it-Q8_0.gguf")}
JEVLIKE = "https://github.com/clarencechien/jevlike"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def sh(cmd, **kw):
    print("+", cmd, flush=True)
    return subprocess.run(cmd, shell=True, check=True, **kw)


def gpu_name():
    return subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()


def build():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    sh(f"rm -rf {BUILD} && git clone -q --depth 1 -b {TAG} https://github.com/ggml-org/llama.cpp {BUILD}")
    sh(f'cd {BUILD} && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="{arg('--archs', '75;89')}" -DCMAKE_BUILD_TYPE=Release > /content/cmake.log 2>&1')
    sh(f"cd {BUILD} && cmake --build build -j --target llama-server > /content/build.log 2>&1")
    secs = round(time.time() - t0, 1)
    sh(f"rm -rf {BIN_DIR} && mkdir -p {BIN_DIR} && cp {BUILD}/build/bin/llama-server {BIN_DIR}/ && cp -P {BUILD}/build/bin/*.so* {BIN_DIR}/ 2>/dev/null || true")
    sh(f"tar czf {OUT}/llama-server-{TAG}.tar.gz -C {BIN_DIR} .")
    ver = subprocess.run(f"LD_LIBRARY_PATH={BIN_DIR} {BIN_DIR}/llama-server --version", shell=True, capture_output=True, text=True)
    rep = {"stage": "build", "tag": TAG, "archs": arg("--archs", "75;89"), "nproc": os.cpu_count(), "gpu": gpu_name(), "build_s": secs, "version": (ver.stdout + ver.stderr)[-400:],
           "tar_bytes": os.path.getsize(f"{OUT}/llama-server-{TAG}.tar.gz"), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(rep, open(f"{OUT}/build.json", "w"), indent=2)
    print("RESULT_JSON " + json.dumps(rep))


def start_server(model_path, log):
    cmd = [f"{BIN_DIR}/llama-server", "-m", model_path, "-ngl", "99", "-c", "16384", "-np", "4", "--port", "8080", "--host", "127.0.0.1",
           "--jinja", "--reasoning-budget", "0", "--metrics", "--swa-full"]
    print("starting:", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT, env=dict(os.environ, LD_LIBRARY_PATH=f"{BIN_DIR}:" + os.environ.get("LD_LIBRARY_PATH", "")))
    t0 = time.time()
    for _ in range(900):
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited early with code {proc.returncode}; see {log}")
        try:
            urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=1)
            print(f"server healthy after {time.time() - t0:.1f}s", flush=True)
            return proc, round(time.time() - t0, 1)
        except Exception:  # noqa: BLE001
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("llama-server did not become healthy")


def bench():
    model = arg("--model", "e4b")
    what = arg("--what", "smoke,latency,accuracy").split(",")
    os.makedirs(OUT, exist_ok=True)
    if not os.path.exists(f"{BIN_DIR}/llama-server"):
        tar = arg("--bin-tar", f"/content/llama-server-{TAG}.tar.gz")
        sh(f"mkdir -p {BIN_DIR} && tar xzf {tar} -C {BIN_DIR}")
    if not os.path.exists("/content/jevlike/.git"):
        sh(f"git clone -q {JEVLIKE} /content/jevlike")
    ref = arg("--jevlike-ref")
    if ref:
        sh(f"cd /content/jevlike && git fetch -q origin {ref} && git checkout -q FETCH_HEAD")
    sh(f"{sys.executable} -m pip install -q huggingface_hub numpy requests")
    from huggingface_hub import hf_hub_download
    repo, fname = MODELS[model]
    t0 = time.time()
    path = hf_hub_download(repo, fname, local_dir="/content/models")
    rep = {"stage": "bench", "model": model, "model_file": fname, "gpu": gpu_name(), "download_s": round(time.time() - t0, 1), "runs": [],
           "jevlike_commit": subprocess.run("git -C /content/jevlike rev-parse HEAD", shell=True, capture_output=True, text=True).stdout.strip()}
    res = "results/colab"
    plan = {"smoke": ("smoke", f"{res}/smoke/{model}", ""),
            "latency": ("latency", f"{res}/latency/{model}", "--only L1"),
            "accuracy": ("accuracy", f"{res}/accuracy/{model}/D0", "--control-n 0")}
    for w in what:  # 每個 bench 各起一個乾淨的 server（latency 要冷跑）
        which, out_dir, args = plan[w]
        proc, ready_s = start_server(path, f"{OUT}/server-{model}.log")
        t = time.time()
        try:
            cmd = f"cd /content/jevlike && {sys.executable} bench/run_local.py --which {which} --model {model} --base-url http://127.0.0.1:8080 --out-dir {out_dir}"
            cmd += f' --args "{args}"' if args else ""
            r = subprocess.run(cmd + f" > {OUT}/{w}-{model}.log 2>&1", shell=True)
            vram = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
            rep["runs"].append({"which": w, "rc": r.returncode, "server_ready_s": ready_s, "bench_s": round(time.time() - t, 1), "vram_used_mib_at_end": vram})
        finally:
            proc.terminate()
            proc.wait(timeout=60)
    sh(f"cd /content/jevlike && tar czf {OUT}/jevlike-results-colab-{model}.tar.gz {res}")
    rep["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(rep, open(f"{OUT}/bench-{model}.json", "w"), indent=2)
    print("RESULT_JSON " + json.dumps(rep))


if __name__ == "__main__":
    {"build": build, "bench": bench}[sys.argv[1]]()
