"""Colab 端自毀保險（handoff 3.4）。在 kernel 裡執行（colab exec），不是用 python 另開行程。
用法：WATCHDOG_MIN=45 經 `colab exec --env WATCHDOG_MIN=45 -f scripts/watchdog_kernel.py` 送進 kernel。
超過牆鐘上限就 runtime.unassign() 釋放 VM。此 API 在 CLI 建立的 runtime 上是否有效：Phase 0 實測。
"""
import os
import threading
import time

_MIN = float(os.environ.get("WATCHDOG_MIN", "45"))


def _bomb():
    time.sleep(_MIN * 60)
    from google.colab import runtime
    print(f"[watchdog] {_MIN} min reached, unassigning runtime", flush=True)
    runtime.unassign()


threading.Thread(target=_bomb, daemon=True, name="cu-watchdog").start()
print(f"[watchdog] armed: runtime.unassign() in {_MIN} min (at {time.strftime('%H:%M:%S', time.gmtime(time.time() + _MIN * 60))} UTC)")
