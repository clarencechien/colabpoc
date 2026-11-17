# Colab 可行性驗證：結果主表

> 2026-11-17 由 Claude Code 網頁版雲端 session 透過 `google-colab-cli` v0.8.0（`--auth=adc`）實跑。
> 狀態類型：**已測**＝實際跑過；**沒測**＝我們沒跑；**沒開**＝跑了但沒打開該參數；**它沒有**＝模型或工具本身不提供。
> 所有速度都是單次執行、單張卡的數字，沒有重複取樣；ASR／TTS 一律不下品質結論。

| Phase | 模型 / 工具 | 卡 | 路徑 | 結果 | 峰值 VRAM | 速度 | 實耗 CU | 狀態類型 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Colab CLI v0.8.0 | T4 | `--auth=adc` new → exec → stop | ✅ | — | new 到第一次 exec 完成約 2.5 分鐘 | ≈0.1（推算） | 已測 | watchdog `runtime.unassign()` 在 CLI 建的 runtime 上**有效** |
| 1 | Breeze ASR 25 | T4 | A. transformers fp16 | ✅ | 4,769 MiB（torch 4,194） | RTF 0.28–0.37（暖機後） | 含在 t4a | 已測 | 有時間戳；第一個檔 RTF 1.17 含暖機 |
| 1 | Breeze ASR 25 | T4 | B. faster-whisper fp16 | ✅ | 3,479 MiB | RTF 0.15–0.21（暖機後） | 含在 t4a | 已測 | 用現成**第三方**轉檔 `SoybeanMilk/faster-whisper-Breeze-ASR-25`，沒有自行轉檔；language 沒開（自動偵測為 zh） |
| 2 | ZONOS3-Mini | T4 | B. `Zyphra/ZONOS3-Mini-hf`（transformers 5.22.1） | ⚠️ 部分 | 2,873 MiB（torch 2,600） | RTF 0.60–0.83（中英夾雜／數字句） | 含在 t4a | 已測 | **3 句純華語都只產出 0.27 秒音訊**（見下）；首段音訊時間：它沒有（-hf 版不含 streaming） |
| 2 | ZONOS3-Mini | T4 | A. 原生參考實作 `zonos3.reference` | ✅ | 4,339 MiB | 每句 90–187 秒（含每次重載模型，RTF 不可比） | 含在 t4a | 已測 | `uv sync` 186 秒；聲音／語言參數沒開（只用 README 最小參數）；首段音訊時間：沒測 |
| 2 | ZONOS3-Mini | L4 | B | ❌ 拿不到卡 | — | — | 0 | 沒測 | L4 被後端拒絕，見通道結論 |
| 3 | jevlike E4B | L4 | llama.cpp b11371 | **沒跑完** | — | — | 0 | 沒測 | L4 被拒；主問題（Colab L4 對 Modal L4）無法回答 |
| 3 | jevlike 26B | L4 | llama.cpp b11371 | **沒跑完** | — | — | 0 | 沒測 | 同上 |
| 3 | jevlike E4B（選做） | T4 | llama.cpp b11371 官方預編 cuda-12.8 | smoke ✅；D0 與 Modal L4 差 +0.1 點 | 未記錄 | L1 p50 135.6 ms | ≈0.35（推算） | 已測 | 見 `docs/jevlike-28-colab-prereg.md` 結果段 |
| 4 | Blender 5.3.0 | T4 | OPTIX | ✅ | — | 11.6 秒 | 含在 t4a | 已測 | 1920×1080、128 samples、不降噪；含 kernel 載入，單張冷跑 |
| 4 | Blender 5.3.0 | T4 | CUDA | ✅ | — | 7.6 秒 | 含在 t4a | 已測 | 同上（CUDA 跑在 OPTIX 之後，可能吃到快取：沒驗證） |
| 4 | Blender 5.3.0 | T4 | CPU（2 vCPU） | ✅ | — | 579.8 秒 | 含在 t4a | 已測 | |
| 4 | Blender 5.3.0 | L4 | OPTIX / CUDA / CPU | ❌ 拿不到卡 | — | — | 0 | 沒測 | |
| 4 | `.glb` → Three.js | — | GLTFLoader r170（無頭 Chromium） | ✅ | — | — | 0 | 已測 | 6 個 mesh、PBR metalness/roughness 保留；相機與燈光沒匯出（匯出參數沒開） |

## Phase 1：Breeze ASR 25 細節

| 訓練集來源 | 測試音檔來源 | 是否可能重疊 |
|---|---|---|
| ODC Synth（BreezyVoice 合成華語 10,000 h）、CommonVoice17-EN 1,738 h、NTUML2021 11 h | ZONOS3-Mini（-hf，Meilin 聲音）合成的 6 句中英夾雜／數字句；`audio/` 沒有自錄音檔 | 沒有用 NTUML2021。合成語音只驗管線，**不代表真實準確度** |

管線對照（只確認兩段都通，不算準確度）：

| 原句（送進 TTS） | A. transformers | B. faster-whisper |
|---|---|---|
| 這個 PR 的 CI 一直 fail，你可以幫我 review 一下嗎？ | 這個 PR 的 CI 一直 fail 你可以幫我 review 一下嗎 | 這個 PR 的 CI 一直 fail你可以幫我 review 一下嗎 |
| 我們先把 model deploy 到 staging，再跑一次 benchmark。 | 我們先把 model deploy 到 staging 再跑一次 benchmark | 同左 |
| 明天的 meeting 改到下午，agenda 我晚點 update。 | 明天的 meeting 改到下午 agenda 我晚點 update | 同左 |
| 訂單編號 A12345，總金額是新台幣三萬六千八百五十元。 | Tingtong Han貨 a 12 345總金額是新台幣 36 850 元 | TINGTONG HENHUA 12 345 總金額是新台幣 36 850 元 |
| 會議時間是 2026 年 11 月 17 日下午 2 點 30 分。 | 會議時間是 2026 年 11 月 17 日下午 2.30 分 | 同左 |
| 良率從 92.5% 提升到 97.3%，UPH 增加了 120 片。 | 楊氏從 92.5％ 提升到 97.3％UPH 增加了 120 片 | 同左 |

只記現象：「訂單編號」「良率」兩處轉寫和原句不同。差異出在 TTS 端還是 ASR 端：沒測（沒有人聽過 wav）。
3 句純華語的 wav 只有 0.27 秒，兩條路的轉寫都是空字串、沒有時間戳。

## Phase 2：ZONOS3-Mini 細節

- 語言：華語**有**（`cmn`）；繁簡之分**它沒有**；台灣口音**它沒有**（華語預設聲音只有 Haoran、Meilin）。中英夾雜：model card 沒寫。
- T4 與 bf16：`torch.cuda.is_bf16_supported(including_emulation=False)` 回 `False`，但以 checkpoint 原生的 bf16 載入後可以生成（沒有退到 float32）。實際用什麼路徑算 bf16：沒查。
- **現象**：-hf 路徑、`voice="Meilin"`、`language="cmn"`、`seed=0` 下，3 句純華語（zh1–zh3）的輸出都是 0.27 秒；同設定下中英夾雜與數字句（4.1–7.7 秒）正常。原生參考實作（沒指定聲音與語言）同一句 zh1 產出 4.93 秒。原因：沒查，也沒換 seed／聲音重試。
- 聲音克隆：沒測（`audio/` 沒有 `ref.*`）。
- 輸出：`results/tts/T4/`（-hf 9 句；原生 3 句前綴 `native_`）。

## Phase 3：jevlike（T4 選做）

E4B 在 T4 上，以 llama.cpp b11371 官方 `ubuntu-cuda-12.8-x64` 預編版（**不是**自行編譯）、跟 `start_server()` 相同的參數加 `--swa-full`，port 改成 8091（Colab VM 的 8080 被 Colab 自己的 Jupyter 佔用，llama-server bind 失敗）。jevlike commit `62811a4`。

- smoke：主要三種 prompt 變體下，10 題的第一個 token 全是字母、`missing` 全空、8/10 題最大機率 > 0.9；option mass 最小 0.99995。
- D0（`--control-n 0`）十類平均 **0.886**，Modal L4 是 **0.885**，差 +0.1 點；逐類差 −0.5 到 +1.0 點，8 類完全相同。
- L1 p50 **135.6 ms**（p95 158.8）。Modal L4 E4B `latency_swafull.json` 的 L1 p50 是 **63.4 ms**（handoff 寫的「約 85 ms」出自 v20，兩個基準都列出）；T4 慢 2.1 倍。
- 原始結果：`results/jevlike_colab/`（與 jevlike 的 `results/colab/` 同結構；因為沒有 jevlike 寫入權限，暫放這裡）。`bench/verify.py --check-lock` 只適用 26B，沒跑。

## 通道結論

- **CLI 在 CC web 可以用**。ADC（四個 scope）放在環境變數 `COLAB_ADC_JSON`、每個指令加 `--auth=adc`，`whoami`、`usage`、`new`、`exec`、`download`、`stop` 全部可用。
- 網路：環境是 unrestricted，**沒有任何 host 被擋**。CLI 連的是 `colab.research.google.com`（`/tun/m/...`）與 `oauth2.googleapis.com`；runtime proxy 的 host 沒記錄（unrestricted 下不需要）。
- `exec` 的 websocket 偶爾斷線（`RuntimeError: Connection was lost.` 或逾時，本次發生數次），VM 本身沒事，重試即可。長任務用 `subprocess.Popen(..., start_new_session=True)` 在 VM 上脫離執行，CC 端每幾分鐘輪詢 log。
- 沒有 `ssh-keygen`，`colab ssh` 沒測；全程用 `exec` 的 `!` 指令。
- watchdog：Phase 0 用 2 分鐘上限實測，`runtime.unassign()` 在到點後約 20 秒內讓 VM 消失（`usage` 的 active assignments 變 0、`colab sessions` 看不到）。
- `colab stop` 之後，`colab sessions`（server 端 `/tun/m/assignments` 回 `[]`）立刻看不到 VM，但 `usage` 的 `Active assignments` 與 `Usage rate` 仍顯示 1 / 1.15/hr 至少數分鐘。用 watchdog 釋放的那次則很快歸零。只記現象。
- **帳號狀態**：`usage` 從頭到尾顯示 `Current balance: 0.00 compute units`。T4 可以配到（使用時 `Usage rate: 1.15/hr`），**L4 被拒**：`Backend rejected accelerator 'L4'. You may not have quota or entitlement for this accelerator on your account.` handoff 推測的「Google AI Pro 約 200 CU/月」在這個帳號上沒有出現。
- **原因（使用者 2026-11-17 截圖確認）**：帳號的 Google AI Pro（5 TB）是 **6 個月試用**（NT$0/月，之後 NT$650/月）。Colab FAQ 寫明 Google One 方案的免費試用期間不含 Colab 權益；Colab「Settings → Subscription」頁也沒有任何生效中的方案。台灣在 Colab 付費服務的國家名單內，不是地區問題。

## 單位帳

`usage` 的餘額全程是 0.00，沒有看到扣點；下表的「推算」是用使用中的 `Usage rate 1.15/hr` 乘上 VM 存活時間。

| Phase | 預算 CU | VM | 存活時間 | 推算 CU |
|---|---|---|---|---|
| 0 | — | p0（T4） | 13:18:47–13:23:40 | 0.09 |
| 1 + 2 + 4 | 3 + 4 + 5 | t4a（T4） | 13:25:02–13:56:31 | 0.60 |
| 3 | 8 | t4b（T4） | 13:58:58–14:16:42 | 0.34 |
| L4 各項 | — | 沒配到 | — | 0 |
| 合計 | 25 | | 約 55 分鐘 T4 | **約 1.0** |

## 下一步建議

1. **要跑 L4 就得有付費運算單元**（Colab 隨用隨付或 Colab Pro；AI Pro 試用期間不會有）。理由：Phase 3 的主問題和所有 L4 列都卡在這裡，不是技術問題。
2. **ZONOS3 純華語 0.27 秒的現象，用固定設定換 seed／換 Haoran 聲音各跑一次**。理由：目前只有單一 seed、單一聲音的觀察，還不能說是 -hf 版的問題。
3. **給 session jevlike 的寫入權限，把 `docs/jevlike-28-colab-prereg.md` 與 `results/jevlike_colab/` 搬過去**。理由：照 jevlike 的紀律，門檻與結果應該在 jevlike 自己的 repo 裡。
