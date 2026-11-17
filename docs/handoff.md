# Handoff：Colab 上跑 Breeze ASR 25 / ZONOS3 TTS / jevlike（Gemma 4）/ Blender 可行性驗證

> 版本 v0.4 · 2026-11-17 · 給 Claude Code 網頁版（雲端 session）接手
> 目標：**先確認「跑不跑得動、要什麼卡、燒多少單位」**。唯一例外是 jevlike：要比對 Colab 跟 Modal 的結果是否等價。

---

## 0. 背景與範圍

- 帳號方案：Google AI Pro（Colab 單位約 200/月，**未經官方證實**，以帳號實際顯示為準）。Pro 沒有背景執行。
- 想驗的東西：
  1. Breeze ASR 25（華語＋中英夾雜 ASR，Whisper large-v2 微調）
  2. ZONOS3-Mini（Zyphra 的多語 TTS，2026-11 發佈）
  3. jevlike（讀選項字母 logprob 的 typed decision）在 Gemma 4 E4B 與 26B-A4B 上的基本測試，對照既有的 Modal L4 結果
  4. （延伸）Blender 無頭 Cycles GPU 算圖
- **不做**：Breeze Guard 26、Breeze ASR 26（台語）、ASR／TTS 品質結論、跟商用引擎比、微調。看到「好像比較準」也只記現象，不下結論。

repo：Phase 0、1、2、4 在 `clarencechien/colabpoc`（使用者自己建立；不存在就停下來問）；Phase 3 在 `clarencechien/jevlike`。CC session 要能同時存取這兩個 repo。

---

## 1. 紀律（每個 Phase 都適用）

1. **「我們沒測」「我們沒開」「它沒有」是三件事**。結果表裡的每一格都要標清楚是哪一種，不准把「沒開某參數」寫成「不支援」。
2. **評估任何開源 ASR 前先查訓練資料清單**。Breeze ASR 25 的訓練集含 NTUML2021，測試音檔不能用那門課。本次不做準確度，但結果檔要記下「訓練集來源 / 測試音檔來源 / 是否可能重疊」三欄。
3. **單位保險絲**：整份 handoff 總預算 **25 CU**。每個 Phase 開工前後都跑 `colab --auth=adc usage` 記下餘額，結束一定 `colab stop`（或用會自己清的 `colab run`）。任一 Phase 預估超過預算上限就停下回報，不要自己加碼。
4. **不准讓 VM 空轉**：每段腳本結尾都要有 teardown；能用 `colab run`（跑完自動拆）就不用 `colab new`。
5. 假說被推翻後不要立刻猜第二個解釋，只記現象。
6. 憑證（ADC JSON、HF token）**不准進 repo、不准印進 log、不准 `cat` 出來**。
7. **模型權重不准下載到 CC VM**（磁碟 30 GB、RAM 16 GB），一律在 Colab VM 上抓。

---

## 2. 執行環境：Claude Code 網頁版（雲端 session）

這份 handoff 由 **Claude Code 網頁版的雲端 session** 執行。它的限制直接決定了架構：

| CC web 限制 | 對這份實驗的影響 |
|---|---|
| VM 約 4 vCPU / 16 GB RAM / 30 GB disk，沒有 GPU | **模型權重、Blender 一律只在 Colab VM 上下載**，CC VM 只放腳本與小型結果 JSON |
| 前景指令預設等 2 分鐘、最多 10 分鐘；轉背景後最多再跑約 30 分鐘 | 長任務不能靠一個 `colab run` 撐完全程，要在 Colab 端脫離執行、CC 端短指令輪詢 |
| session 閒置會過期、VM 回收，背景指令不會恢復 | CC 掛了，Colab runtime 可能**還在燒單位** → 必須有 Colab 端自毀保險（見 3.4） |
| 環境變數：用這個環境的人都讀得到 | ADC 憑證只能放在**使用者個人環境**，不可放共享環境 |
| network secret 只能注入固定的 header（Bearer 等） | Google ADC 要用 refresh token 自己換 access token（一小時過期），**network secret 不適用**，只能走環境變數 |

### 2.1 使用者要先在環境設定做的事（開工前確認）

1. **網路存取**改成 **Custom**，勾選「Also include default list of common package managers」，再加上：
   ```
   colab.research.google.com
   *.colab.dev
   ```
   依據（直接 grep CLI v0.8.0 原始碼）：

   | CLI 連的 host | 用途 | 預設 Trusted 有沒有 |
   |---|---|---|
   | `colab.research.google.com` | session 後端（`/tun/m/...`，配 runtime、unassign） | **沒有，要加** |
   | `colab.pa.googleapis.com` | Colab API | 有（`*.googleapis.com`） |
   | `oauth2.googleapis.com`、`www.googleapis.com` | 換 token、tokeninfo | 有 |
   | `accounts.google.com` | OAuth | 有 |
   | runtime proxy（kernel、檔案上下傳） | **網址由後端動態給**（`runtimeProxyInfo.url`），程式碼裡沒有寫死 | 未知 |

   `*.colab.dev` 是**推測**（其他 Colab 遠端工具的 runtime proxy 在這個網域底下），沒有實測過。**Phase 0 的做法**：如果 `colab new` 成功但 `exec` 連不上，用 `colab --logtostderr --auth=adc exec ...` 印出實際的 proxy host，回報給使用者補進清單。真的找不到，可以暫時把網路開成 **Full** 跑一次、記下 host，再改回 Custom。

   **不用加的**：`huggingface.co`、`download.blender.org`、llama.cpp 的 GitHub release 等等。這些都在 **Colab VM** 上下載，不經過 CC 的網路。
2. **環境變數**新增 `COLAB_ADC_JSON=<ADC JSON 整段內容>`。ADC 由使用者在自己的 Crostini 產生（四個 scope 缺一不可，來源：CLI 內建 SKILL.md）：
   ```bash
   gcloud auth application-default login \
     --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory
   ```
   ⚠️ 這份 JSON 含 refresh token，權限涵蓋 `cloud-platform`。實驗結束後請使用者撤銷（`gcloud auth application-default revoke`，或到 Google 帳戶的第三方存取權限頁移除）。
3. （選做）環境變數加 `BASH_DEFAULT_TIMEOUT_MS=600000`，讓前景指令預設等 10 分鐘。

### 2.2 Session 開頭固定動作（建議寫成 SessionStart hook 或 setup script）

```bash
uv tool install google-colab-cli
umask 077
mkdir -p ~/.config/gcloud
printf '%s' "$COLAB_ADC_JSON" > ~/.config/gcloud/application_default_credentials.json
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json
colab skill > /tmp/COLAB_SKILL.md   # 先讀完它再動手
```

---

## 3. Phase 0：通道打通（最可能卡住的一步）

### 3.1 已知事實（實際安裝 v0.8.0 後的 `colab --help` 與內建 SKILL.md）

- **每個指令都要明寫 `--auth=adc`**，而且放在子指令前面：`colab --auth=adc new -s x`。v0.8.0 的 `--help` 顯示預設是 `oauth2`，跟 README／SKILL.md 寫的 `adc` 不一致，不要依賴預設值。
- oauth2 會開瀏覽器授權，CC web 沒有瀏覽器 → **不要用**。
- 驗證身分：`colab --auth=adc sessions`（唯讀）或隱藏指令 `colab --auth=adc whoami`（印出 email、scope、到期時間）。401／403 幾乎都是 scope 或憑證問題。
- 不要把 `colab auth` 當成 CLI 登入：它是把 GCP 憑證注入 **Colab VM 的 kernel**，跟 CLI 驗證無關。
- 單位帳：`colab --auth=adc usage` 會顯示 compute unit 消耗率與餘額 → 每個 Phase 前後都要記。
- GPU 可選值：`T4`、`L4`、`G4`、`H100`、`A100`
- `colab run [--gpu X] script.py` = new + exec + stop，腳本出錯也會自己清；`--keep` 才保留 VM。
- shell 指令：`colab ssh -s NAME -- 'cmd' </dev/null > out.txt`（需要本機 ssh key，沒有就 `ssh-keygen -t ed25519` 產一把）；ssh 不行時改用 `echo '!cmd' | colab exec -s NAME`。
- **代理人不可以互動執行**：`colab repl`、不帶 `-- CMD` 的 `colab ssh`、`colab auth`、`colab drivemount`。

### 3.2 要實測、要記錄的

- [ ] `colab --auth=adc whoami` 成功與否、顯示的 scope
- [ ] `colab --auth=adc usage` 顯示的餘額（這就是本月實際配額，取代「約 200」的傳聞）
- [ ] `colab --auth=adc new -s p0 --gpu T4` → `nvidia-smi` → `colab stop -s p0`
- [ ] 過程中被 CC web 網路擋掉的所有 hostname（錯誤原文照貼）

### 3.3 Kill criteria

- 30 分鐘內走不完 3.2 的第三項 → **停止 Phase 0，切備案 B**，並把卡住的原因寫進結果檔。

### 3.4 Colab 端自毀保險（CC session 過期時的防線）

所有在 Colab VM 上跑的長腳本，開頭都要先啟動一個 watchdog thread：超過該 Phase 的牆鐘上限（預設 45 分鐘）就呼叫
```python
from google.colab import runtime
runtime.unassign()
```
主動釋放 runtime。**這個 API 在 CLI 建立的 runtime 上是否有效需要實測**；Phase 0 用 `--keep` 開一台 T4，把上限設成 2 分鐘試一次，確認 `colab sessions` 看不到它才算通過。不通過就回報，之後所有 Phase 只准用不帶 `--keep` 的 `colab run`，而且單次不得超過 25 分鐘。

### 3.5 長任務的跑法

- 單次 ≤ 8 分鐘：直接 `colab --auth=adc run --gpu X scripts/phaseN.py`。
- 更長：`colab new` 之後用 `colab ssh -s NAME -- 'nohup python /content/phaseN.py > /content/phaseN.log 2>&1 &'` 脫離執行，CC 端每隔幾分鐘用短指令 `tail` log、`colab status` 輪詢，跑完 `colab download` 結果，再 `colab stop`。
- 輪詢之間如果 CC session 可能閒置過期，要靠 3.4 的 watchdog 收尾。

### 3.6 備案 B（不走 CLI，也不是 copy-paste）

每個 Phase 都產出一份自足的 `.ipynb` 推到 repo 的 `notebooks/`，使用者用
`https://colab.research.google.com/github/clarencechien/colabpoc/blob/main/notebooks/<名稱>.ipynb`
在手機或 Chromebook 打開，選好 GPU 後按「全部執行」。Notebook 最後一格必須把結果寫成 JSON 並印出，讓使用者貼回來或存到 Drive。

> 不管走 CLI 還是備案 B，**腳本本體都放在 `scripts/` 當 `.py`**，notebook 只是薄殼呼叫它，兩條路共用同一份程式。

---

## 4. Phase 1：Breeze ASR 25（T4）

- 模型：`MediaTek-Research/Breeze-ASR-25`（Whisper large-v2 架構，華語＋中英夾雜；**不測台語版 26**）
- 卡：`T4`
- **訓練資料先查**：Breeze ASR 25 的訓練集含 NTUML2021（台大機器學習 2021 課程），之前在 kikemu 已證實會污染評測。測試音檔**不可以**用這門課的錄音，結果檔要記「測試音檔來源」一欄。
- 測試音檔（依序找，找到就停）：
  1. 使用者放在 `audio/` 的自錄音檔（華語或中英夾雜）
  2. Phase 2 用 ZONOS3-Mini 產的華語／中英夾雜句子（**合成語音，只驗管線，不代表真實準確度**）
- 兩條路都試，各自記錄成敗：
  - A. transformers pipeline，fp16
  - B. faster-whisper（CTranslate2）——Breeze ASR 25 有沒有現成轉檔請自己查；沒有就在 Colab VM 上用 `ct2-transformers-converter` 轉，標「自行轉檔」
- 要量：能不能載入、峰值 VRAM、RTF（處理時間 ÷ 音檔長度）、有沒有時間戳
- 預算：≤ 3 CU

## 5. Phase 2：ZONOS3-Mini TTS（先 T4，不行再 L4）

- 模型：Zyphra 的 ZONOS3-Mini（Apache 2.0，MoE，總參數約 800M、每次啟用約 100M；2026-11 剛發佈，**介面可能還在變，以 model card 當下內容為準**）。兩個入口都試：
  - A. `Zyphra/ZONOS3-Mini` + Zonos 套件（`pip install git+https://github.com/Zyphra/Zonos.git`）
  - B. `Zyphra/ZONOS3-Mini-hf`（`transformers>=4.57`，`trust_remote_code=True`）
- 先確認 model card 的 43 種語言裡**有沒有華語**，有沒有分繁簡、台灣口音；沒有就照實記「它沒有」，不要硬測。
- **T4 風險**：骨幹用 Gated DeltaNet，可能依賴只支援較新 GPU 架構的 kernel；T4（sm75）也沒有原生 bf16。T4 失敗時把錯誤原文記下，換 `L4` 重跑，結果表分開兩列。
- 測試句子（自擬，各 3 句）：純華語、中英夾雜（例如「這個 PR 的 CI 一直 fail」）、含數字日期金額
- 要量：能不能跑、峰值 VRAM、RTF、第一段音訊出來的時間；輸出 wav 下載回 `results/tts/`
- 聲音克隆：**只用使用者自己放在 `audio/` 的參考音檔**；沒有就只跑預設聲音。不准用網路上任何人的聲音。
- **銜接 Phase 1**：把產生的 wav 丟給 Breeze ASR 25 轉回文字，貼原句與轉寫對照。只用來確認兩段管線都通，**不算準確度**（合成語音太乾淨）。
- 預算：≤ 4 CU

## 6. Phase 3：jevlike 基本測試，E4B 與 26B-A4B（L4）

### 6.1 這一段在哪個 repo 做

- 工作在 **`clarencechien/jevlike`**，開分支 `colab/2026-11-<日>`；結果放 `results/colab/`，報告寫 `results/28-colab.md`（目前最新是 27）。
- 先讀 jevlike 的 `README.md` §1–§4 與「踩過的坑」、`PLAN.md`、`modal_app.py` 的 `start_server()`、`bench/run_local.py`。**照 jevlike 自己的紀律：門檻先寫進 `results/28-colab.md` 並 commit，再跑。**
- jevlike 的「不要做」清單照樣適用（不改 `decide/prompt.py`、不開 MTP、不訓練 LoRA）。

### 6.2 要回答的問題（只有一個）

**Colab L4 能不能當 jevlike 的第二個後端，跟 Modal L4 跑出等價的結果？** 不是重新評估模型能力。

### 6.3 做法

1. **llama.cpp**：釘 **b11371**（README 指定的版本）。Colab 沒有 Docker，自己編：
   `cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="75;89" && cmake --build build -j --target llama-server`（75 = T4、89 = L4）。記下編譯時間與 CU。
   編好的 `llama-server`（連同需要的 `.so`）打包後 `colab download` 回 CC VM 的 `/tmp`（**不進 git**），之後每次開新 runtime 直接 `colab upload`，不再重編。
2. **模型**：照 `modal_app.py` 的 `MODELS`，在 Colab VM 上 `hf_hub_download`：
   - `e4b`：`unsloth/gemma-4-E4B-it-GGUF` / `gemma-4-E4B-it-Q8_0.gguf`（約 8.2 GB）
   - `26b`：`unsloth/gemma-4-26B-A4B-it-GGUF` / `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`（約 17 GB）
3. **server 參數**：跟 `start_server()` 完全一樣：`-ngl 99 -c 16384 -np 4 --jinja --reasoning-budget 0 --metrics`，accuracy 加 `--swa-full`（README Quickstart 的設定）。用 `nohup` 在 Colab 端背景啟動，等 `/health`。
4. **跑 bench**：jevlike repo 整包 `colab upload` 到 Colab VM（或在 VM 上 `git clone` 同一個 commit），在 VM 上執行：
   ```bash
   python3 bench/run_local.py --which smoke    --model e4b --base-url http://127.0.0.1:8080 --out-dir results/colab/smoke/e4b
   python3 bench/run_local.py --which accuracy --model e4b --base-url http://127.0.0.1:8080 --out-dir results/colab/accuracy/e4b/D0 --args "--control-n 0"
   ```
   E4B 跑完換 26B（`--model 26b`）重跑一次。latency 只跑 L1（單題 p50），參數看 `bench/latency.py` 怎麼收，不要跑全套。
5. **拉回來比**：`colab download` 結果到 CC VM，在 CC VM 上跑 `bench/verify.py --check-lock`，並逐類對照 Modal L4 的既有結果（`results/modal/`）。

### 6.4 預先登記的門檻（跑之前就寫死）

| 項目 | 通過條件 | 對照基準 |
|---|---|---|
| smoke | 第一個 token 是字母、`missing` 為空、明顯題 p > 0.9 | jevlike M1 條件 |
| 26B D0 | `--check-lock` 0 失敗；十類平均與 Modal L4 差 ≤ 1 點 | 0.955（README §3） |
| E4B D0 | 十類平均與 Modal L4 差 ≤ 1 點 | 0.885（README v13 列） |
| 單題 p50 | 與 Modal L4 差 ≤ 30% | 26B 137 ms（`--swa-full`）、E4B 約 85 ms（v20） |
| 成本 | 只記錄，不設門檻 | Modal L4 約 $0.80/h vs Colab L4 實耗 CU |

結論三選一：**等價**（可以當第二後端）／**不等價**（寫出差在哪一類、哪個數字）／**沒跑完**（寫卡在哪）。

### 6.5 注意

- `<bos>`、thinking 關閉、`--swa-full`、選項順序固定，這些坑 README 都寫了；不等價時**先查這幾個**，不要先懷疑卡。
- 量速度要冷跑（README v20：prompt 快取會重播）。
- 選做：E4B 在 **T4** 上也跑一次 smoke + L1，記錄能不能跑、多慢（T4 比 L4 便宜，若可用就是最便宜的 E4B 後端）。
- 預算：≤ 8 CU（含編譯）

## 7. Phase 4（延伸）：Blender 無頭 Cycles

- 從 `download.blender.org/release/` 抓最新的 Linux x64 版本（記下版本號）；缺的 X11 / GL 系統函式庫用 apt 補（例如 libxi6、libxxf86vm1、libxfixes3、libxrender1、libgl1、libxkbcommon0、libsm6，以實際報錯為準）。
- 不需要 .blend 檔：用 `bpy` 腳本程序化建一個場景（地面 + 幾個 PBR 球 + HDRI 或日光），1920×1080、128 samples。
- 在 Python 端設 GPU：

  ```python
  prefs = bpy.context.preferences.addons["cycles"].preferences
  prefs.compute_device_type = "OPTIX"   # 失敗再試 "CUDA"
  prefs.get_devices()
  for d in prefs.devices:
      d.use = True
  bpy.context.scene.cycles.device = "GPU"
  ```

- 要量：同一場景在 `T4` 與 `L4` 上，OPTIX / CUDA / CPU 的單張算圖秒數；結果 PNG 下載回 `results/blender/`。
- 再選做一件：把場景 export 成 `.glb`（glTF），確認 Three.js 讀得進去。
- 預算：≤ 5 CU

---

## 8. 交付物

```
colabpoc/
├── scripts/            # 每個 Phase 一支 .py，可單獨跑
├── notebooks/          # 備案 B 的薄殼 .ipynb
├── results/
│   ├── feasibility.md  # 主表（下方格式）
│   ├── raw/*.json      # 每次執行的原始數字
│   ├── tts/*.wav
│   └── blender/*.png
└── CLAUDE.md           # 把第 1 節紀律抄進來

jevlike/（分支 colab/2026-11-<日>）
├── results/colab/      # smoke、accuracy、latency 原始結果（同 Modal 的目錄結構）
└── results/28-colab.md # 門檻（先 commit）＋結論三選一
```

`llama-server` 編好的 binary 與 GGUF **都不進 git**。

`results/feasibility.md` 主表格式：

| Phase | 模型 / 工具 | 卡 | 路徑 | 結果 | 峰值 VRAM | 速度 | 實耗 CU | 狀態類型 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Breeze ASR 25 | T4 | transformers fp16 | ✅ / ❌ | | RTF | | 已測 / 沒測 / 沒開 / 不支援 | |
| 2 | ZONOS3-Mini | T4 / L4 | Zonos 套件 / transformers | ✅ / ❌ | | RTF | | | |
| 3 | jevlike 26B | L4 | llama.cpp b11371 | 等價 / 不等價 / 沒跑完 | | p50 ms | | | 見 jevlike `results/28-colab.md` |

最後附三段：
1. **通道結論**：CLI 在 CC web 能不能用、卡在哪、被擋的 host 清單
2. **單位帳**：每 Phase 預算與實耗
3. **下一步建議**：最多三條，每條附一句理由

## 9. 停下來問使用者的時機

- Phase 0 卡關、決定要不要切備案 B
- 任何模型需要 HF 授權或 token
- jevlike 結果「不等價」：先查 README 的坑，查完仍不等價就停下回報，不要自己改 `decide/` 去湊數字
- 任一 Phase 預估會超出預算上限
- `colab stop` 失敗或 `colab sessions` 看到不認得的 session
