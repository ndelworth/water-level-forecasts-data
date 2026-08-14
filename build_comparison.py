"""
build_comparison.py
--------------------
The other view, complementary to eval_wlf_accuracy.py's lead-time MAE
rollup: what does each forecast actually predict, right now, laid over
recent observed water level? Takes the single most recent wlf snapshot run
and the single most recent own-model snapshot run (not the whole
accumulated history -- that would be a tangle of overlapping forecast
issues) plus a trailing window of observed wlo, and writes docs/comparison.json
for the chart on docs/index.html.

Output: docs/comparison.json
  {
    "generated_at": ...,
    "wlf_poll_time": ... | null,   -- which forecast run is shown, so a stale
    "own_poll_time": ... | null,      run is visible rather than silently misleading
    "wlo":       [{"time": iso, "value": float|null}, ...],
    "wlf":       [{"time": iso, "value": float|null}, ...],
    "our_model": [{"time": iso, "value": float|null}, ...],
  }
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

WLO_PATH = "data/wlo_actuals.csv"
WLF_PATH = "data/wlf_snapshots.csv"
OWN_PATH = "data/own_forecast_snapshots.csv"
OUT_JSON = "docs/comparison.json"
TRAILING_HOURS = 96  # ~4 days of observed history for context around "now"


def series_records(df, time_col, value_col):
    return [
        {"time": t.isoformat(), "value": None if pd.isna(v) else round(float(v), 3)}
        for t, v in zip(df[time_col], df[value_col])
    ]


def latest_run(df, value_col):
    """Given a lead-tagged snapshot df, return just the single most recent
    poll_time's rows (i.e. one forecast run), sorted by valid_time."""
    if df.empty:
        return None, df
    latest_poll = df["poll_time"].max()
    run = df[df["poll_time"] == latest_poll].sort_values("valid_time")
    return latest_poll, run


def main():
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wlf_poll_time": None,
        "own_poll_time": None,
        "wlo": [], "wlf": [], "our_model": [],
    }

    if os.path.exists(WLO_PATH):
        wlo = pd.read_csv(WLO_PATH, parse_dates=["time"])
        if not wlo.empty:
            cutoff = wlo["time"].max() - pd.Timedelta(hours=TRAILING_HOURS)
            wlo = wlo[wlo["time"] >= cutoff]
            payload["wlo"] = series_records(wlo, "time", "wlo")
        print(f"wlo: {len(wlo)} trailing points")
    else:
        print(f"{WLO_PATH} not found yet -- comparison chart will have no observed line.")

    if os.path.exists(WLF_PATH):
        wlf = pd.read_csv(WLF_PATH, parse_dates=["poll_time", "valid_time"])
        poll_time, run = latest_run(wlf, "wlf")
        if poll_time is not None:
            payload["wlf_poll_time"] = poll_time.isoformat()
            payload["wlf"] = series_records(run, "valid_time", "wlf")
        print(f"wlf: latest run at {poll_time}, {len(run)} points")
    else:
        print(f"{WLF_PATH} not found yet -- comparison chart will have no wlf line.")

    if os.path.exists(OWN_PATH):
        own = pd.read_csv(OWN_PATH, parse_dates=["poll_time", "valid_time"])
        poll_time, run = latest_run(own, "our_pred")
        if poll_time is not None:
            payload["own_poll_time"] = poll_time.isoformat()
            payload["our_model"] = series_records(run, "valid_time", "our_pred")
        print(f"our model: latest run at {poll_time}, {len(run)} points")
    else:
        print(f"{OWN_PATH} not found yet (pdu-tide-forecast not live) -- comparison chart will have no model line.")

    os.makedirs("docs", exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {OUT_JSON}")


if __name__ == "__main__":
    main()
