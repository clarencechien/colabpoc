"""Phase 1：Breeze ASR 25 可行性（能不能載入、峰值 VRAM、RTF、時間戳）。不做準確度。

用法（在 Colab VM 上）：
  python scripts/phase1_breeze_asr.py [--audio-dir DIR ...] [--paths A,B] [--out /content/out/phase1]
音檔來源依序：repo 的 audio/（使用者自錄）→ /content/out/phase2（ZONOS3 合成，只驗管線）。
A = transformers fp16；B = faster-whisper (CTranslate2)。每條路在子行程跑，父行程用 nvidia-smi 量峰值 VRAM。
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time
import traceback

MODEL = "MediaTek-Research/Breeze-ASR-25"
CT2_PREBUILT = "SoybeanMilk/faster-whisper-Breeze-ASR-25"  # 第三方轉檔（非 MediaTek 官方）
CT2_LOCAL = "/content/breeze-asr-25-ct2"
EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def find_audio():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs = [d for i, d in enumerate(sys.argv[1:], 1) if sys.argv[i - 1] == "--audio-dir"]
    cands = [(d, "指定目錄") for d in dirs] or [(os.path.join(here, "audio"), "使用者自錄 (audio/)"),
                                              ("/content/out/phase2", "ZONOS3-Mini 合成語音（只驗管線，不代表真實準確度）")]
    for d, label in cands:
        files = sorted(f for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                       if f.lower().endswith(EXTS) and not os.path.basename(f).lower().startswith("ref"))
        if files:
            return files, label
    return [], "找不到音檔"


def load16k(path):
    import librosa
    wav, _ = librosa.load(path, sr=16000, mono=True)
    return wav


def worker_a(files):
    import torch
    from transformers import AutomaticSpeechRecognitionPipeline, WhisperForConditionalGeneration, WhisperProcessor
    t0 = time.time()
    proc = WhisperProcessor.from_pretrained(MODEL)
    model = WhisperForConditionalGeneration.from_pretrained(MODEL, torch_dtype=torch.float16).to("cuda").eval()
    pipe = AutomaticSpeechRecognitionPipeline(model=model, tokenizer=proc.tokenizer, feature_extractor=proc.feature_extractor,
                                              chunk_length_s=0, torch_dtype=torch.float16, device="cuda")
    rep = {"load_s": round(time.time() - t0, 1), "dtype": "float16", "files": []}
    for i, f in enumerate(files + files[:1]):  # 最後重跑第一個檔當暖機後的數字
        wav = load16k(f)
        dur = len(wav) / 16000
        t = time.time()
        out = pipe(wav.copy(), return_timestamps=True)
        dt = time.time() - t
        chunks = out.get("chunks") or []
        rep["files"].append({"file": os.path.basename(f), "pass": "warm-repeat" if i >= len(files) else "first", "dur_s": round(dur, 2),
                             "proc_s": round(dt, 2), "rtf": round(dt / dur, 4), "text": out["text"],
                             "has_timestamps": bool(chunks and chunks[0].get("timestamp")), "n_segments": len(chunks),
                             "first_segment": chunks[0] if chunks else None})
    rep["torch_peak_alloc_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
    return rep


def worker_b(files):
    from faster_whisper import WhisperModel
    rep = {"files": []}
    t0 = time.time()
    try:
        model = WhisperModel(CT2_PREBUILT, device="cuda", compute_type="float16")
        rep["ct2_source"] = f"現成轉檔 {CT2_PREBUILT}（第三方）"
    except Exception as e:  # noqa: BLE001
        rep["prebuilt_error"] = repr(e)[:500]
        if not os.path.exists(os.path.join(CT2_LOCAL, "model.bin")):
            cmd = ["ct2-transformers-converter", "--model", MODEL, "--output_dir", CT2_LOCAL, "--quantization", "float16", "--force"]
            r = subprocess.run(cmd + ["--copy_files", "tokenizer.json", "preprocessor_config.json"], capture_output=True, text=True)
            if r.returncode != 0:
                r = subprocess.run(cmd + ["--copy_files", "preprocessor_config.json"], capture_output=True, text=True)
            rep["convert_rc"] = r.returncode
            rep["convert_tail"] = (r.stdout + r.stderr)[-800:]
        model = WhisperModel(CT2_LOCAL, device="cuda", compute_type="float16")
        rep["ct2_source"] = "自行轉檔 (ct2-transformers-converter, float16)"
    rep["load_s"] = round(time.time() - t0, 1)
    for i, f in enumerate(files + files[:1]):
        t = time.time()
        segs, info = model.transcribe(f, beam_size=5, word_timestamps=False)  # language 沒開（自動偵測）
        segs = list(segs)
        dt = time.time() - t
        rep["files"].append({"file": os.path.basename(f), "pass": "warm-repeat" if i >= len(files) else "first", "dur_s": round(info.duration, 2),
                             "proc_s": round(dt, 2), "rtf": round(dt / info.duration, 4), "text": "".join(s.text for s in segs),
                             "detected_language": info.language, "has_timestamps": bool(segs), "n_segments": len(segs),
                             "first_segment": [segs[0].start, segs[0].end, segs[0].text] if segs else None})
    return rep


def run_worker(which, files):
    try:
        rep = {"A": worker_a, "B": worker_b}[which](files)
        rep["ok"] = True
    except Exception as e:  # noqa: BLE001
        rep = {"ok": False, "error": repr(e)[:1000], "traceback": traceback.format_exc()[-3000:]}
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
    if "--worker" in sys.argv:
        return run_worker(arg("--worker"), json.loads(arg("--files")))
    out = arg("--out", "/content/out/phase1")
    os.makedirs(out, exist_ok=True)
    files, source = find_audio()
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    rep = {"phase": 1, "model": MODEL, "gpu": gpu, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "provenance": {"訓練集來源": "ODC Synth（BreezyVoice 合成華語 10,000h）、CommonVoice17-EN 1,738h、NTUML2021 11h（model card）",
                          "測試音檔來源": source,
                          "是否可能重疊": "未使用 NTUML2021；合成語音與 ODC Synth 同屬 TTS 合成但引擎不同（ZONOS3 vs BreezyVoice）" if "ZONOS3" in source else "由使用者確認自錄音檔非 NTUML2021"},
           "paths": {}}
    if not files:
        rep["error"] = "沒有音檔（audio/ 是空的，Phase 2 也還沒產出 wav）"
    else:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper", "librosa"], check=False)
        import importlib.util
        libs = []
        for pkg in ("nvidia.cudnn", "nvidia.cublas"):
            spec = importlib.util.find_spec(pkg)
            if spec and spec.submodule_search_locations:
                libs.append(os.path.join(list(spec.submodule_search_locations)[0], "lib"))
        env = dict(os.environ, LD_LIBRARY_PATH=":".join(libs + [os.environ.get("LD_LIBRARY_PATH", "")]))
        for which in arg("--paths", "A,B").split(","):
            stop, peak = threading.Event(), [0]
            th = threading.Thread(target=vram_poller, args=(stop, peak))
            th.start()
            t0 = time.time()
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker", which, "--files", json.dumps(files)],
                               capture_output=True, text=True, env=env)
            stop.set()
            th.join()
            line = [l for l in r.stdout.splitlines() if l.startswith("WORKER_JSON ")]
            res = json.loads(line[-1][12:]) if line else {"ok": False, "error": f"worker rc={r.returncode}", "stderr_tail": r.stderr[-3000:]}
            res["peak_vram_mib_nvidia_smi"] = peak[0]
            res["wall_s"] = round(time.time() - t0, 1)
            rep["paths"]["A_transformers_fp16" if which == "A" else "B_faster_whisper"] = res
    json.dump(rep, open(os.path.join(out, "phase1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("RESULT_JSON " + json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
