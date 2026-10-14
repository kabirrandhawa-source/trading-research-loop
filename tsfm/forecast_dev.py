"""Walk-forward TimesFM 3 forecasts for the ETF universe, development period only (ledger hypothesis 6).

For every ETF and every development day t, the model sees the 512 daily log closes ending at t
(nothing after t) and forecasts the log close at t+1. Days on or after backtest.SEALED_START are
never loaded into the model.

Run with the TimesFM environment:  .venv-tsfm/bin/python -m tsfm.forecast_dev
Output: data/tsfm/forecasts_dev.csv  (symbol, timestamp, close, fc, q10, q50, q90; fc/q are log prices)
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import backtest  # noqa: E402  (date split + price loading only)

CONTEXT = 512
BATCH = 256
OUT = ROOT / "data" / "tsfm" / "forecasts_dev.csv"


def jobs():
    syms = [s.strip() for s in (ROOT / "universe.txt").read_text().split() if s.strip()]
    for s in syms:
        dev, _ = backtest.split(backtest.load_prices(ROOT / "data" / f"{s}.csv"))
        lp = np.log(dev["close"].to_numpy(float))
        for t in range(CONTEXT - 1, len(dev)):
            yield s, dev["timestamp"].iloc[t], float(dev["close"].iloc[t]), lp[t - CONTEXT + 1:t + 1]


def main():
    from timesfm3 import ModelConfig, TimesFM3Evaluator
    model = TimesFM3Evaluator(ModelConfig(device="cpu", per_core_batch_size=64))
    todo = list(jobs())
    print(f"{len(todo)} forecasts to make", flush=True)
    rows, t0 = [], time.time()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        outs = model.predict_batch([c[3] for c in chunk], horizon=1, return_quantiles=True, univariate=True)
        for (s, ts, close, _), o in zip(chunk, outs):
            q = o.quantiles[0]
            rows.append((s, ts, close, float(o.forecast[0]), float(q[0]), float(q[4]), float(q[-1])))
        done = i + len(chunk)
        if (i // BATCH) % 10 == 0:
            rate = done / (time.time() - t0)
            print(f"  {done}/{len(todo)}  ({rate:.0f}/s, ~{(len(todo) - done) / rate / 60:.0f} min left)", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["symbol", "timestamp", "close", "fc", "q10", "q50", "q90"]).to_csv(OUT, index=False)
    print(f"wrote {len(rows)} forecasts to {OUT}")


if __name__ == "__main__":
    main()
