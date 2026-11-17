# colabpoc

Colab 上跑 Breeze ASR 25／ZONOS3-Mini TTS／jevlike（Gemma 4）／Blender 的可行性驗證。任務說明：`docs/handoff.md`；結果：`results/feasibility.md`。

## 備案 B：用 Colab 網頁直接跑（不需要 CLI／ADC）

依序開這三份 notebook，各自選好 GPU 後「全部執行」：

| 順序 | Notebook | GPU | watchdog | 內容 |
|---|---|---|---|---|
| 1 | [t4_all](https://colab.research.google.com/github/clarencechien/colabpoc/blob/claude/keen-turing-d5s729/notebooks/t4_all.ipynb) | T4 | 75 分 | Phase 0 → 2B（TTS）→ 1（ASR，吃 Phase 2 的 wav）→ 4（Blender）→ 2A（原生 TTS） |
| 2 | [l4_misc](https://colab.research.google.com/github/clarencechien/colabpoc/blob/claude/keen-turing-d5s729/notebooks/l4_misc.ipynb) | L4 | 40 分 | Phase 2B 與 Phase 4 的 L4 對照列 |
| 3 | [l4_jevlike](https://colab.research.google.com/github/clarencechien/colabpoc/blob/claude/keen-turing-d5s729/notebooks/l4_jevlike.ipynb) | L4 | 110 分 | Phase 3：編 llama.cpp b11371 → E4B → 26B |

連結打不開（分支名有斜線）時：Colab「檔案 → 開啟筆記本 → GitHub」，輸入 `clarencechien/colabpoc`，分支選 `claude/keen-turing-d5s729`，再選 `notebooks/` 底下的檔案。

想用自己的聲音：先把自錄音檔放進 `audio/`（ASR 測試用，不可用 NTUML2021 課程錄音）；聲音克隆的參考音檔命名為 `audio/ref.wav`。
