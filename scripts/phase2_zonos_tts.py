"""Phase 2：ZONOS3-Mini TTS 可行性（能不能跑、峰值 VRAM、RTF、首段音訊時間）。不做品質結論。

用法（在 Colab VM 上）：
  python scripts/phase2_zonos_tts.py [--paths B,A] [--out /content/out/phase2]
B = Zyphra/ZONOS3-Mini-hf（transformers，trust_remote_code）
A = 原生 runtime 的參考實作（github.com/Zyphra/ZONOS3-Mini，`python -m zonos3.reference`）
    註：handoff 寫的 `pip install git+https://github.com/Zyphra/Zonos.git` 在 2026-11-17 的 model card 上沒有出現，
    model card 指向的是 Zyphra/ZONOS3-Mini repo（uv workspace）與 SGLang-Omni，這裡以 model card 為準。
聲音克隆：只有 repo 的 audio/ref.* 存在才做；否則只跑預設聲音（Meilin，model card 列的華語預設聲音）。
"""
import glob
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import traceback

HF_REPO = "Zyphra/ZONOS3-Mini-hf"
NATIVE_GIT = "https://github.com/Zyphra/ZONOS3-Mini"
VOICE, LANG = "Meilin", "cmn"
SENTENCES = {
    "zh1": "今天下午三點要開產線檢討會議，請大家準時出席。",
    "zh2": "這批板子的錫膏印刷偏移太多，需要重新校正鋼板。",
    "zh3": "颱風快來了，記得把陽台的盆栽收進來。",
    "mix1": "這個 PR 的 CI 一直 fail，你可以幫我 review 一下嗎？",
    "mix2": "我們先把 model deploy 到 staging，再跑一次 benchmark。",
    "mix3": "明天的 meeting 改到下午，agenda 我晚點 update。",
    "num1": "訂單編號 A12345，總金額是新台幣三萬六千八百五十元。",
    "num2": "會議時間是 2026 年 11 月 17 日下午 2 點 30 分。",
    "num3": "良率從 92.5% 提升到 97.3%，UPH 增加了 120 片。",
}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def worker_b(out):
    import soundfile as sf
    import torch
    import transformers
    from transformers import AutoModel
    rep = {"transformers": transformers.__version__, "torch": torch.__version__, "voice": VOICE, "language": LANG,
           "bf16_supported": torch.cuda.is_bf16_supported(including_emulation=False) if hasattr(torch.cuda, "is_bf16_supported") else None,
           "首段音訊時間": "它沒有：-hf 版 model card 明寫不含 streaming decode，只能量整句時間", "attempts": [], "files": []}
    model = None
    for label, kw in (("as-stored(default)", {}), ("bfloat16", {"dtype": torch.bfloat16}), ("float32", {"dtype": torch.float32})):
        t0 = time.time()
        try:
            m = AutoModel.from_pretrained(HF_REPO, trust_remote_code=True, **kw).to("cuda")
            t1 = time.time()
            o = m.generate("測試。", voice=VOICE, language=LANG, seed=0)  # 暖機兼確認這個 dtype 真的能生成
            rep["attempts"].append({"dtype": label, "ok": True, "load_s": round(t1 - t0, 1), "warmup_s": round(time.time() - t1, 1),
                                    "lm_param_dtype": str(next(m.parameters()).dtype)})
            model = m
            rep["dtype_used"] = label
            break
        except Exception as e:  # noqa: BLE001
            rep["attempts"].append({"dtype": label, "ok": False, "error": repr(e)[:1500], "traceback": traceback.format_exc()[-2500:]})
            m = None
            torch.cuda.empty_cache()
    if model is None:
        raise RuntimeError("所有 dtype 都失敗，見 attempts")
    torch.cuda.reset_peak_memory_stats()

    def synth(key, text, **voice_kw):
        t = time.time()
        o = model.generate(text, language=LANG, seed=0, **voice_kw)
        dt = time.time() - t
        wav = o.waveform.detach().float().cpu().numpy()
        dur = len(wav) / o.sampling_rate
        path = os.path.join(out, f"{key}.wav")
        sf.write(path, wav, o.sampling_rate)
        rep["files"].append({"key": key, "text": text, "wav": os.path.basename(path), "audio_s": round(dur, 2), "gen_s": round(dt, 2),
                             "rtf": round(dt / dur, 4) if dur else None, "sampling_rate": o.sampling_rate})

    for key, text in SENTENCES.items():
        synth(key, text, voice=VOICE)
    refs = sorted(glob.glob(os.path.join(repo_root(), "audio", "ref.*")))
    if refs:
        wav, sr = sf.read(refs[0], dtype="float32", always_2d=True)
        emb = model.embed_speaker(wav.T, sr)
        for key in ("zh1", "mix1", "num1"):
            synth(f"clone_{key}", SENTENCES[key], speaker_embedding=emb)
        rep["clone"] = f"已測：使用者參考音檔 {os.path.basename(refs[0])}（speaker embedding 路徑）"
    else:
        rep["clone"] = "沒測：audio/ 沒有 ref.* 參考音檔"
    rep["torch_peak_alloc_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
    return rep


def sh(cmd, timeout, cwd=None, env=None):
    t = time.time()
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return {"cmd": cmd, "rc": r.returncode, "s": round(time.time() - t, 1), "tail": (r.stdout + r.stderr)[-2500:]}
    except subprocess.TimeoutExpired as e:
        return {"cmd": cmd, "rc": "timeout", "s": timeout, "tail": ((e.stdout or b"").decode(errors="replace") + (e.stderr or b"").decode(errors="replace"))[-2500:]}


def worker_a(out):
    import soundfile as sf
    rep = {"entry": f"{NATIVE_GIT} → python -m zonos3.reference", "steps": [], "files": [],
           "首段音訊時間": "沒測：只跑離線參考實作，沒有起 streaming server（servers/sgl 需要 CUDA 12.8 toolkit）",
           "note": "每句都是獨立行程，gen_s 含模型載入，RTF 偏高"}
    src = "/content/ZONOS3-Mini"
    steps = [("pip install -q uv", 300, None), (f"rm -rf {src} && git clone -q --recurse-submodules {NATIVE_GIT} {src}", 600, None),
             ("uv sync --locked --all-packages", 1200, src), ("uv run python -m zonos3.reference --help", 300, src)]
    for cmd, to, cwd in steps:
        s = sh(cmd, to, cwd)
        rep["steps"].append(s)
        if s["rc"] != 0:
            raise RuntimeError(f"step failed: {cmd} (rc={s['rc']})\n{s['tail'][-800:]}")
    for key in ("zh1", "mix1", "num1"):  # 語言 / 聲音參數沒開：reference CLI 的旗標以 --help 輸出為準，這裡只用 README 範例的最小參數
        path = os.path.join(out, f"native_{key}.wav")
        s = sh(f"uv run python -m zonos3.reference --model hf://Zyphra/ZONOS3-Mini/lm/zonos3_mini --text {shlex.quote(SENTENCES[key])} -o {path} --device cuda", 900, src)
        rep["steps"].append(s)
        if s["rc"] != 0:
            raise RuntimeError(f"reference failed (rc={s['rc']})\n{s['tail'][-1500:]}")
        info = sf.info(path)
        rep["files"].append({"key": key, "text": SENTENCES[key], "wav": os.path.basename(path), "audio_s": round(info.duration, 2), "gen_s_incl_load": s["s"],
                             "rtf_incl_load": round(s["s"] / info.duration, 3) if info.duration else None})
    return rep


def run_worker(which, out):
    rep = {}
    try:
        rep = {"A": worker_a, "B": worker_b}[which](out)
        rep["ok"] = True
    except Exception as e:  # noqa: BLE001
        rep.update({"ok": False, "error": repr(e)[:2000], "traceback": traceback.format_exc()[-3000:]})
    print("WORKER_JSON " + json.dumps(rep, ensure_ascii=False), flush=True)


def vram_poller(stop, peak):
    while not stop.is_set():
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True)
        try:
            peak[0] = max(peak[0], int(r.stdout.split()[0]))
        except Exception:  # noqa: BLE001
            pass
        stop.wait(0.5)


def main():
    out = arg("--out", "/content/out/phase2")
    os.makedirs(out, exist_ok=True)
    if "--worker" in sys.argv:
        return run_worker(arg("--worker"), out)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    rep = {"phase": 2, "model": "ZONOS3-Mini", "gpu": gpu, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "language_check": {"華語": "有（model card：Mandarin Chinese，request code `cmn`）",
                              "繁簡之分": "它沒有：model card 只列一個 Mandarin Chinese，沒有分繁簡",
                              "台灣口音": "它沒有：預設華語聲音只有 Haoran / Meilin（energetic），model card 沒提台灣口音",
                              "中英夾雜": "model card 沒寫是否支援；`language` 只選文字正規化，不是語言 token"},
           "paths": {}}
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "transformers>=4.57", "soundfile", "zyphra-textnorm"], check=False)
    for which in arg("--paths", "B,A").split(","):
        stop, peak = threading.Event(), [0]
        th = threading.Thread(target=vram_poller, args=(stop, peak))
        th.start()
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker", which, "--out", out], capture_output=True, text=True)
        stop.set()
        th.join()
        line = [l for l in r.stdout.splitlines() if l.startswith("WORKER_JSON ")]
        res = json.loads(line[-1][12:]) if line else {"ok": False, "error": f"worker rc={r.returncode}", "stderr_tail": r.stderr[-3000:]}
        res["peak_vram_mib_nvidia_smi"] = peak[0]
        res["wall_s"] = round(time.time() - t0, 1)
        rep["paths"]["B_transformers_hf" if which == "B" else "A_native_reference"] = res
    json.dump(rep, open(os.path.join(out, "phase2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("RESULT_JSON " + json.dumps(rep, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main()
