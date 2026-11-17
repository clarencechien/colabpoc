# colabpoc：Colab 可行性驗證

完整任務說明在 `docs/handoff.md`。目前進度與結果在 `results/feasibility.md`。

## 紀律（每個 Phase 都適用）

1. **「我們沒測」「我們沒開」「它沒有」是三件事**。結果表每一格都要標清楚是哪一種，不准把「沒開某參數」寫成「不支援」。
2. **評估任何開源 ASR 前先查訓練資料清單**。Breeze ASR 25 的訓練集含 NTUML2021，測試音檔不能用那門課。結果檔要記「訓練集來源 / 測試音檔來源 / 是否可能重疊」三欄。
3. **單位保險絲**：總預算 25 CU。每個 Phase 開工前後都跑 `colab --auth=adc usage` 記餘額，結束一定 `colab stop`。任一 Phase 預估超過預算上限就停下回報，不要自己加碼。
4. **不准讓 VM 空轉**：每段腳本結尾都要 teardown；能用 `colab run` 就不用 `colab new`。
5. 假說被推翻後不要立刻猜第二個解釋，只記現象。
6. 憑證（ADC JSON、HF token）**不准進 repo、不准印進 log、不准 `cat` 出來**。
7. **模型權重不准下載到 CC VM**，一律在 Colab VM 上抓。

## 操作

- Session 開頭：`source scripts/cc_setup.sh`（需要環境變數 `COLAB_ADC_JSON`）。
- 每個 colab 指令都要明寫 `--auth=adc`，放在子指令前面。
- 跑一個 Phase：`scripts/run_phase.sh <session名> <GPU> <牆鐘上限分鐘> <腳本> [參數...]`（開機 → kernel watchdog → clone repo → 執行 → 下載 `/content/out` → stop）。
- 腳本本體都在 `scripts/*.py`，`notebooks/*.ipynb` 只是薄殼（備案 B）。
- 不做：Breeze Guard 26、Breeze ASR 26（台語）、品質結論、跟商用引擎比、微調。
