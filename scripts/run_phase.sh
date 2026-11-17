#!/usr/bin/env bash
# 跑一個 Phase：開機 → watchdog → clone repo → 執行腳本 → 下載結果 → stop。
# 用法：scripts/run_phase.sh <session> <GPU|CPU> <watchdog分鐘> <scripts/xxx.py> [腳本參數...]
# 適合 ≤ 8 分鐘的前景執行；更長的請照 handoff 3.5 用 nohup + 輪詢（DETACH=1 只啟動不等待）。
set -uo pipefail
S=$1; GPU=$2; WD=$3; SCRIPT=$4; shift 4
C="colab --auth=adc"
BRANCH=${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}
REPO=${REPO:-https://github.com/clarencechien/colabpoc}
LOG=results/raw/${S}.log
mkdir -p results/raw
teardown() { $C stop -s "$S" >>"$LOG" 2>&1; $C sessions; }
{ echo "== usage before =="; $C usage; } 2>&1 | tee "$LOG"
if [ "$GPU" = CPU ]; then $C new -s "$S"; else $C new -s "$S" --gpu "$GPU"; fi 2>&1 | tee -a "$LOG" || { teardown; exit 1; }
trap teardown EXIT
$C exec -s "$S" --env WATCHDOG_MIN="$WD" -f scripts/watchdog_kernel.py 2>&1 | tee -a "$LOG"
printf '%s\n' "!rm -rf /content/colabpoc && git clone -q --depth 1 -b '$BRANCH' '$REPO' /content/colabpoc && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" | $C exec -s "$S" 2>&1 | tee -a "$LOG"
CMD="cd /content/colabpoc && python $SCRIPT $* > /content/phase.log 2>&1"
if [ "${DETACH:-0}" = 1 ]; then
  trap - EXIT
  printf '%s\n' "import subprocess; subprocess.Popen(['bash','-c',r'''nohup bash -c \"$CMD\" &'''])" | $C exec -s "$S"
  echo "detached. 輪詢：echo '!tail -5 /content/phase.log' | $C exec -s $S ；結束後記得 $C stop -s $S"
  exit 0
fi
printf '%s\n' "!$CMD; tail -40 /content/phase.log; cd /content && tar czf out.tgz out phase.log 2>/dev/null" | $C exec -s "$S" 2>&1 | tee -a "$LOG"
$C download -s "$S" /content/out.tgz "results/raw/${S}.out.tgz" 2>&1 | tee -a "$LOG"
{ echo "== usage after =="; $C usage; } 2>&1 | tee -a "$LOG"
