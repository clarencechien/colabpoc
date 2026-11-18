# 28 — Colab L4 當 jevlike 第二後端：預先登記的門檻

> 本檔在 **任何 Colab 執行之前** commit（colabpoc 分支 `claude/keen-turing-d5s729`）。
> 依 jevlike 紀律它應該放在 `clarencechien/jevlike` 的 `results/28-colab.md`；這個 session 沒有 jevlike 的寫入權限，
> 所以先登記在這裡，之後原封不動搬過去（搬的時候註明原始 commit）。jevlike 對照 commit：`62811a4`。

## 問題（只有一個）

Colab L4 能不能當 jevlike 的第二個後端，跑出跟 Modal L4 等價的結果？不重新評估模型能力。

## 設定（跟 `modal_app.start_server()` 相同）

llama.cpp **b11371**，自己編（`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="75;89"`）；
`-ngl 99 -c 16384 -np 4 --jinja --reasoning-budget 0 --metrics --swa-full`。
模型：e4b = `unsloth/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q8_0.gguf`；26b = `unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`。
每個 bench 各起一個乾淨 server；latency 只跑 L1（`--only L1`，預設 n=200、warmup=20），而且排在 accuracy 前面冷跑。

## 門檻

| 項目 | 通過條件 | 對照基準 |
|---|---|---|
| smoke | 第一個 token 是字母、`missing` 為空、明顯題 p > 0.9 | jevlike M1 條件 |
| 26B D0 | `bench/verify.py --check-lock` 0 失敗；十類平均與 Modal L4 差 ≤ 1 點 | 0.955（README §3） |
| E4B D0 | 十類平均與 Modal L4 差 ≤ 1 點 | 0.885（README v13 列） |
| 單題 p50（`L1_single_100tok_2opt`） | 與 Modal L4 差 ≤ 30% | 26B 137 ms（`--swa-full`）、E4B 約 85 ms（v20） |
| 成本 | 只記錄，不設門檻 | Modal L4 約 $0.80/h vs Colab L4 實耗 CU |

結論三選一：**等價**／**不等價**（差在哪一類、哪個數字）／**沒跑完**（卡在哪）。
不等價時先查 `<bos>`、thinking 關閉、`--swa-full`、選項順序；查完仍不等價就停下回報，不改 `decide/`。

## 結果（2026-11-17）

**結論：沒跑完。** 這個帳號的 Colab 餘額是 0.00 CU，`colab new --gpu L4` 被後端拒絕（no quota or entitlement），所以 26B 與 E4B 在 L4 上都沒跑，「Colab L4 跟 Modal L4 是否等價」這個問題沒有答案。

選做（T4，不屬於上表的門檻）：E4B，llama.cpp b11371 官方 `ubuntu-cuda-12.8-x64` 預編版（不是自行編譯），參數同上，port 改 8091（Colab 的 8080 被 Jupyter 佔用）。

| 項目 | Colab T4 | Modal L4 | 備註 |
|---|---|---|---|
| smoke | 第一個 token 全是字母、`missing` 全空、8/10 題 p > 0.9 | — | M1 條件成立 |
| E4B D0 十類平均 | 0.886 | 0.885 | 差 +0.1 點；逐類 −0.5 到 +1.0，8 類相同 |
| L1 p50 | 135.6 ms | 63.4 ms（`latency_swafull.json`）；handoff 寫約 85 ms（v20） | T4 不是 L4，30% 門檻不適用，只記錄 |
| 成本 | 約 0.34 CU（推算，餘額沒有變動） | 約 $0.80/h | |

原始結果暫放 colabpoc `results/jevlike_colab/`。
