# Colab 可行性驗證：結果主表

> 最後更新 2026-11-17。**目前沒有任何一個 Phase 在 Colab 上實際跑過**（原因見「通道結論」）。
> 下表「沒測」＝我們沒測，不代表跑不動。腳本都只做過語法檢查，沒有在 GPU 上執行過。

| Phase | 模型 / 工具 | 卡 | 路徑 | 結果 | 峰值 VRAM | 速度 | 實耗 CU | 狀態類型 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Colab CLI v0.8.0 | T4 | `--auth=adc` | — | — | — | 0 | 沒測 | CC 環境沒有 `COLAB_ADC_JSON`，CLI 無法驗證身分 |
| 1 | Breeze ASR 25 | T4 | A. transformers fp16 | — | — | — | 0 | 沒測 | `scripts/phase1_breeze_asr.py` |
| 1 | Breeze ASR 25 | T4 | B. faster-whisper | — | — | — | 0 | 沒測 | 有現成 CT2 轉檔（第三方，如 `SoybeanMilk/faster-whisper-Breeze-ASR-25`），載不起來才自行轉檔 |
| 2 | ZONOS3-Mini | T4 / L4 | B. `Zyphra/ZONOS3-Mini-hf`（transformers） | — | — | — | 0 | 沒測 | `scripts/phase2_zonos_tts.py` |
| 2 | ZONOS3-Mini | T4 / L4 | A. 原生參考實作 `zonos3.reference` | — | — | — | 0 | 沒測 | handoff 寫的 `Zyphra/Zonos.git` 套件在 model card 上沒出現，改用 card 指向的 `Zyphra/ZONOS3-Mini` repo |
| 3 | jevlike E4B / 26B | L4 | llama.cpp b11371 | 沒跑完 | — | — | 0 | 沒測 | 另外還缺 `clarencechien/jevlike` 的 push 權限，門檻檔尚未 commit |
| 4 | Blender 5.3.0 | T4 / L4 | OPTIX / CUDA / CPU | — | — | — | 0 | 沒測 | `scripts/phase4_blender.py`；版本號是 2026-11-17 `download.blender.org` 上最新的 linux-x64 |

## 已查到的事實（不需要 GPU）

**Breeze ASR 25（model card）**

| 訓練集來源 | 測試音檔來源 | 是否可能重疊 |
|---|---|---|
| ODC Synth（BreezyVoice 合成華語，10,000 h）、CommonVoice17-EN（1,738 h）、NTUML2021（11 h，中英夾雜） | 尚未決定：`audio/` 目前是空的，預設會用 Phase 2 的 ZONOS3 合成句子 | 不使用 NTUML2021。若用合成語音：只驗管線，不算準確度 |

**ZONOS3-Mini（model card，2026-11-14 版）**

- 華語：**有**（Mandarin Chinese，request code `cmn`；NeMo 文字正規化支援華語）。
- 繁簡之分：**它沒有**（只列一個 Mandarin Chinese）。台灣口音：**它沒有**（華語預設聲音只有 Haoran、Meilin 兩個）。
- 中英夾雜：model card 沒寫；`language` 參數只選文字正規化，不是語言 token。
- `-hf` 版不含 streaming decode → 「第一段音訊時間」在 transformers 路徑上**它沒有**，要量得走原生 server（需要 CUDA 12.8 toolkit，官方只寫在 H100 測過）。
- 權重是 bf16；transformers 4.x 預設載成 float32，要 bf16 得傳 `dtype=torch.bfloat16`。T4 行不行：沒測。
- 不需要 HF token（兩個 repo 都不是 gated）。

## 通道結論

- **CLI 在 CC web 能不能用：還不知道（沒測）。** `google-colab-cli` 裝得起來，但這個 session 的環境（名稱 `CU`）沒有 `COLAB_ADC_JSON`，`~/.config/gcloud` 也沒有 ADC 檔，所以 `whoami` / `usage` / `new` 一個都沒跑。
- 網路：環境目前是 **unrestricted**（不是 handoff 2.1 寫的 Custom），所以這次不會有被擋的 host；被擋 host 清單：無（沒測到那一步）。
- 已確認 CLI v0.8.0 的 `--auth` 預設值是 `oauth2`（`--help`），內建 SKILL.md 寫的是 `adc`，兩者不一致，跟 handoff 的觀察相同。
- `runtime.unassign()` watchdog 是否有效：沒測。

## 單位帳

| Phase | 預算 CU | 實耗 CU |
|---|---|---|
| 0 | （含在總額） | 0 |
| 1 | 3 | 0 |
| 2 | 4 | 0 |
| 3 | 8 | 0 |
| 4 | 5 | 0 |
| 合計 | 25 | 0（帳號餘額未能讀取） |

## 下一步建議

1. **在環境 `CU` 加上環境變數 `COLAB_ADC_JSON` 後開新 session**（`source scripts/cc_setup.sh` 接手）。理由：這是 CLI 路線唯一的阻擋點，其他都備好了。
2. **或直接走備案 B**：用 Colab 打開 `notebooks/phase0_probe.ipynb` 起跑。理由：不需要 ADC，今天就能拿到第一批數字；repo 是公開的，notebook 可以直接 clone。
3. **給 session `clarencechien/jevlike` 的寫入權限**。理由：Phase 3 規定門檻要先 commit 進 jevlike 再跑，目前只有唯讀。
